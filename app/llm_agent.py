from app.db import run_query
from app.llm import ask_ollama,clean_sql_response
from app.agent import load_examples,find_best_example

def build_sql_prompt(user_question):#builds the full prompt that we send to the local model
    prompt=f"""
You are a cricket analytics sql agent
your job is to convert the user's cricket analytics question into sql server query

database schema:
table:matches
columns:
-match_id
-season
-start_date
-eveny
-venue
-city
-toss_winner
-toss_decision
-player_of_match
-winner
-winner_runs
-winner_wickets

Table:deliveries
columns:
-delivery_id
-match_id
-season
-start_date
-venue
-innings
-ball
-batting_team
-bowling_team
-striker
-non_striker
-bowler
-runs_off_bat
-extras
-wides
-noballs
-byes
-legbyes
-penalty
-wicket_type
-player_dismissed
-other_wicket_type
-other_player_dismissed

Important cricket definitions:
-total batter runs=SUM(runs_off_bat)
-total team runs=sum(runs_off_bat+extras)
-legal ball=wides IS NULL and noballs IS NULL
-batter strike rate= runs_off_bat*100/legal balls faced
-bowler economy rate= runs conceded * 6 / legal balls bowled
-powerplay overs= FLOOR(ball) BETWEEN 0 and 5
-death overs= FLOOR(ball) BETWEEN 15 and 19
-Bowling wickets should exlude run out,retired hurt,retired out,and obstructing the field
-batting_team and bowling_team are columns in the deliveries table, not in the matches table
-for chasing questions, use deliveries where innings=2 and join with matches using match_id
- for team chasing wins, compare d.batting_team with m.winner
- for average first innings score by venue, first calculate total score per match and venue where innings=1, then average those totals grouped by venue.
- the ball column stores over.ball values such as 0.1,5.3 and 19.6. it does not mean total balls faced or total balls bowled.
-never use ball>=300 to mean at least 300 balls faced or bowled
-balls faced should be calculated using legal deliveries: sum(case when wides IS NULL and noballs IS NULL then 1 else 0 END)
-strike rate= sum(runs_off_bat)*100.0/legal balls faced
-economy rate should include all deliveries bowled, not only wicket deliveries
-do not filter wicket_type when calculating economy rate
-economy rate= sum(runs_off_bat+extras)*6.0/legal balls bowled
- A duck means a batter was dismissed for 0 runs in a match innings. Do not count dot balls as ducks.
- For ducks, first group by match_id, innings, and striker, then check SUM(runs_off_bat) = 0 and the batter was dismissed.
- A bowling spell means one bowler's bowling figures in one match innings. Group by match_id, innings, and bowler.
- For "single season" records, group by season and player.
- Orange Cap means the highest run scorer in each season.
- Purple Cap means the highest wicket taker in each season.
- A successful chase means innings = 2, batting_team = winner, and the innings total is the chase score.
- For "against a team", use bowling_team. For example, runs against Chennai Super Kings means bowling_team = 'Chennai Super Kings'.
- For "for a team", use batting_team.
- CSK means Chennai Super Kings.
- RCB means Royal Challengers Bangalore.
- MI means Mumbai Indians.
- KKR means Kolkata Knight Riders.
- SRH means Sunrisers Hyderabad.
- DC means Delhi Capitals.
- DD means Delhi Daredevils.
- RR means Rajasthan Royals.
- PBKS means Punjab Kings.
- KXIP means Kings XI Punjab.
- GT means Gujarat Titans.
- LSG means Lucknow Super Giants.
- Chepauk means MA Chidambaram Stadium in Chennai. Use venue LIKE '%Chidambaram%' or venue LIKE '%Chepauk%'.
- For highest sixes in a match, include match_id, season, start_date, venue, and both teams if possible.
- The current matches table does not contain a clear playoff stage column, so playoff-specific questions may require adding match_number or stage metadata first.
- PBKS and KXIP refer to the same franchise history. For Punjab franchise questions, use: IN ('Punjab Kings', 'Kings XI Punjab').
- Punjab Kings and Kings XI Punjab should be treated as the same team when calculating franchise-level totals.
- DD and Delhi Capitals refer to the same franchise history. For Delhi franchise questions, use: IN ('Delhi Capitals', 'Delhi Daredevils').
- Delhi Capitals and Delhi Daredevils should be treated as the same team when calculating franchise-level totals.
- DC is ambiguous because it can mean Delhi Capitals or Deccan Chargers.
- If the user only says "DC" without specifying Delhi Capitals or Deccan Chargers, ask the user to clarify instead of generating SQL.
- If the user says "Deccan Chargers", use 'Deccan Chargers' only.
- If the user says "Delhi Capitals" or "Delhi Daredevils", treat them as the same Delhi franchise using IN ('Delhi Capitals', 'Delhi Daredevils').
- For team match wins, use the matches table only. Do not join deliveries unless the question needs ball-by-ball data.
- For Punjab franchise wins, count matches where winner IN ('Punjab Kings', 'Kings XI Punjab').
- For Delhi franchise wins, count matches where winner IN ('Delhi Capitals', 'Delhi Daredevils').
- KT and KTK mean Kochi Tuskers Kerala.
- RPS means Rising Pune Supergiant or Rising Pune Supergiants. Use IN ('Rising Pune Supergiant', 'Rising Pune Supergiants').
- Chinnaswamy means M Chinnaswamy Stadium or M.Chinnaswamy Stadium.
- Narendra Modi Stadium may also appear as Sardar Patel Stadium or Motera in older data. Use venue LIKE '%Narendra Modi%' OR venue LIKE '%Sardar Patel%' OR venue LIKE '%Motera%'.
- Highest score for a team means highest individual score in one match innings for that team. Group by match_id, innings, striker, batting_team, and bowling_team.
- Do not answer highest score for a team by summing the player's career runs for that team.
- Most expensive spell means one bowler in one match innings. Group by match_id, innings, and bowler.
- Do not answer most expensive spell using career total runs conceded.
- Single season records must group by season and player.
- Highest sixes in a single season means season + batter, not career sixes.
- Successful chase means an innings 2 team won the match. The chase score is the innings total for that match, not the number of rows/deliveries.
- Highest successful chase should group by match_id, innings, batting_team, and bowling_team.
- Highest or lowest team score means one team's score in one match innings. Group by match_id, innings, batting_team, and bowling_team.
- Do not group only by match_id for team scores, because that combines both teams' scores.
- For lowest team score, prefer completed/all-out innings by counting wickets. Use wickets >= 10 when asking for all-time lowest completed team score.
- For wickets in a phase, count only actual wickets. Use wicket_type IS NOT NULL and exclude run out, retired hurt, retired out, and obstructing the field.
- Do not count every ball in the phase as a wicket.
- For runs against a team, use bowling_team.
- For runs for a team, use batting_team.
- For single-innings fours or sixes records, group by match_id, innings, striker, batting_team, and bowling_team.
- Include useful context such as season, start_date, venue, batting_team, bowling_team, and runs_in_innings when possible.
- Fastest fifty or fastest hundred means the fewest legal balls faced to reach 50 or 100 in one innings.
- Use cumulative batter runs and cumulative legal balls within match_id, innings, and striker.
- For batting balls faced and fastest 50/100 milestone counting, count deliveries where wides IS NULL. Do not exclude no-balls from batter milestone ball count.
Venue and city alias rules:
- If the user asks about a venue nickname or city, map it to the actual venue names in the database.
- For venue/city questions, prefer joining deliveries d with matches m using match_id, then filter using m.venue, d.venue, or m.city.
- Use LIKE filters for venue aliases because the same stadium may appear with slightly different names.

Venue aliases:
- Ekana or Lucknow means venue LIKE '%Ekana%' OR venue LIKE '%Lucknow%'.
- DY Patil means venue LIKE '%DY Patil%'.
- Vizag or Visakhapatnam means venue LIKE '%Visakhapatnam%' OR venue LIKE '%ACA-VDCA%'.
- Chinnaswamy, Bengaluru, or Bangalore means venue LIKE '%Chinnaswamy%' OR city IN ('Bengaluru', 'Bangalore').
- Chepauk or Chennai means venue LIKE '%Chidambaram%' OR venue LIKE '%Chepauk%' OR city = 'Chennai'.
- Mullanpur or New Chandigarh means venue LIKE '%Mullanpur%' OR venue LIKE '%New Chandigarh%'.
- Mohali or Chandigarh means venue LIKE '%Mohali%' OR venue LIKE '%Chandigarh%'.
- Uppal or Hyderabad means venue LIKE '%Uppal%' OR venue LIKE '%Hyderabad%' OR city = 'Hyderabad'.
- Motera, Ahmedabad, Narendra Modi Stadium, or Sardar Patel Stadium means venue LIKE '%Narendra Modi%' OR venue LIKE '%Sardar Patel%' OR venue LIKE '%Motera%' OR city = 'Ahmedabad'.
- Wankhede or Mumbai means venue LIKE '%Wankhede%' OR city = 'Mumbai'.
- Eden Gardens or Kolkata means venue LIKE '%Eden Gardens%' OR city = 'Kolkata'.
- Jaipur means venue LIKE '%Sawai Mansingh%' OR city = 'Jaipur'.
- Dharamsala means venue LIKE '%Himachal Pradesh%' OR city = 'Dharamsala'.
- Pune means venue LIKE '%Maharashtra Cricket Association%' OR venue LIKE '%Subrata Roy%' OR city = 'Pune'.
- Raipur means venue LIKE '%Raipur%' OR city = 'Raipur'.
- Guwahati means venue LIKE '%Guwahati%' OR venue LIKE '%Barsapara%'.
- Delhi means venue LIKE '%Arun Jaitley%' OR venue LIKE '%Feroz Shah Kotla%' OR city = 'Delhi'.
- Rajkot means venue LIKE '%Saurashtra%' OR city = 'Rajkot'.
- Abu Dhabi means venue LIKE '%Zayed%' OR city = 'Abu Dhabi'.
- Dubai means venue LIKE '%Dubai%'.
- Sharjah means venue LIKE '%Sharjah%'.
- Wanderers means venue LIKE '%Wanderers%'.

sql rules:
-use sql server syntax only
-use select top 10 instead of limit
-only write select queries
-do not write insert,update,delete,drop,alter,create,truncate,exec or merge
-return only the sql query
-do not use markdown code fences
-do not explain anything
- When using a subquery, make sure the inner SELECT has a complete FROM clause before closing the subquery.
- Do not close the subquery until after GROUP BY inside the subquery.
-for average first innings score by venue,first calculate total score per match and venue where innings=1, then average those totals grouped by venue
-when using a subquery, make sure the inner select has its from clause before closing the subquery
-do not close subquery until after the inner group by its complete.
- for single innings batting records, group by match_id,innings, and striker. do not group only by striker
-"single innings" means one batter's runs in one match innings, not total runs across all matches.

Examples:

Question: Who are the top 10 run scorers?
SQL:
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
GROUP BY striker
ORDER BY total_runs DESC;

Question: Who are the top 10 wicket takers?
SQL:
SELECT TOP 10
    bowler,
    COUNT(*) AS wickets
FROM deliveries
WHERE wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY bowler
ORDER BY wickets DESC;

Question: Who scored the most runs in death overs?
SQL:
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS death_overs_runs
FROM deliveries
WHERE FLOOR(ball) BETWEEN 15 AND 19
GROUP BY striker
ORDER BY death_overs_runs DESC;

Question: Which teams have the most wins while chasing?
SQL:
select top 10
    d.batting_team as chasing_team,
    count(distinct d.match_id) as chasing_wins
from deliveries d
join matches m
    on d.match_id=m.match_id
where d.innings=2
    and d.batting_team=m.winner
group by d.batting_team
order by chasing_wins desc;

Question: Which venues have the highest average first innings score?
SQL:
SELECT TOP 10
    venue,
    ROUND(AVG(total_score * 1.0), 2) AS average_first_innings_score,
    COUNT(*) AS innings_count
FROM (
    SELECT
        match_id,
        venue,
        SUM(runs_off_bat + extras) AS total_score
    FROM deliveries
    WHERE innings = 1
    GROUP BY match_id, venue
) AS first_innings_scores
GROUP BY venue
HAVING COUNT(*) >= 10
ORDER BY average_first_innings_score DESC;

Question: Which batters have the best strike rate with at least 300 balls faced?
SQL:
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS runs,
    SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    ROUND(
        SUM(runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries
GROUP BY striker
HAVING SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) >= 300
ORDER BY strike_rate DESC;

Question: Which bowlers have the best economy rate with at least 300 legal balls bowled?
SQL:
SELECT TOP 10
    bowler,
    SUM(runs_off_bat + extras) AS runs_conceded,
    SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    ROUND(
        SUM(runs_off_bat + extras) * 6.0 /
        NULLIF(SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy_rate
FROM deliveries
GROUP BY bowler
HAVING SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) >= 300
ORDER BY economy_rate ASC;

Question: Which batters have hit the most runs in a single innings?
SQL:
SELECT TOP 10
    d.striker AS batter,
    d.match_id,
    d.innings,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, d.innings, d.striker, m.start_date, m.venue
ORDER BY runs_in_innings DESC;

Question: Which players have the most ducks?
SQL:
SELECT TOP 10
    striker AS batter,
    COUNT(*) AS ducks
FROM (
    SELECT
        match_id,
        innings,
        striker,
        SUM(runs_off_bat) AS runs_in_innings,
        MAX(CASE 
                WHEN player_dismissed = striker 
                     AND wicket_type NOT IN ('retired hurt', 'retired out')
                THEN 1 
                ELSE 0 
            END) AS was_dismissed
    FROM deliveries
    GROUP BY match_id, innings, striker
) AS batter_innings
WHERE runs_in_innings = 0
  AND was_dismissed = 1
GROUP BY striker
ORDER BY ducks DESC;

Question: What is the most expensive spell by a bowler?
SQL:
SELECT TOP 10
    d.bowler,
    d.match_id,
    d.innings,
    m.start_date,
    m.venue,
    d.bowling_team,
    d.batting_team,
    SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
    SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, d.innings, d.bowler, m.start_date, m.venue, d.bowling_team, d.batting_team
HAVING SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) >= 6
ORDER BY runs_conceded DESC;

Question: Who has the highest number of sixes in a single season?
SQL:
SELECT TOP 10
    season,
    striker AS batter,
    COUNT(*) AS sixes
FROM deliveries
WHERE runs_off_bat = 6
GROUP BY season, striker
ORDER BY sixes DESC;

Question: What are the top 5 highest successful chases?
SQL:
SELECT TOP 5
    d.match_id,
    m.season,
    m.start_date,
    m.venue,
    d.batting_team AS chasing_team,
    d.bowling_team AS defending_team,
    SUM(d.runs_off_bat + d.extras) AS chase_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings = 2
  AND d.batting_team = m.winner
GROUP BY d.match_id, m.season, m.start_date, m.venue, d.batting_team, d.bowling_team
ORDER BY chase_score DESC;

Question: What game had the highest number of sixes in it?
SQL:
SELECT TOP 1
    d.match_id,
    m.season,
    m.start_date,
    m.venue,
    MIN(d.batting_team) AS team_1,
    MAX(d.batting_team) AS team_2,
    SUM(CASE WHEN d.runs_off_bat = 6 THEN 1 ELSE 0 END) AS total_sixes
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, m.season, m.start_date, m.venue
ORDER BY total_sixes DESC;

Question: Which players have the most hundreds?
SQL:
SELECT TOP 5
    batter,
    COUNT(*) AS hundreds
FROM (
    SELECT
        match_id,
        innings,
        striker AS batter,
        SUM(runs_off_bat) AS runs_in_innings
    FROM deliveries
    GROUP BY match_id, innings, striker
) AS batter_innings
WHERE runs_in_innings >= 100
GROUP BY batter
ORDER BY hundreds DESC;

Question: Which player has scored the most runs against Chennai Super Kings?
SQL:
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
WHERE bowling_team = 'Chennai Super Kings'
GROUP BY striker
ORDER BY total_runs DESC;

Question: Who won the Orange Cap in each season?
SQL:
WITH season_runs AS (
    SELECT
        season,
        striker AS batter,
        SUM(runs_off_bat) AS total_runs
    FROM deliveries
    GROUP BY season, striker
),
ranked_runs AS (
    SELECT
        season,
        batter,
        total_runs,
        RANK() OVER (PARTITION BY season ORDER BY total_runs DESC) AS run_rank
    FROM season_runs
)
SELECT
    season,
    batter,
    total_runs
FROM ranked_runs
WHERE run_rank = 1
ORDER BY season;

Question: Who won the Purple Cap in each season?
SQL:
WITH season_wickets AS (
    SELECT
        season,
        bowler,
        COUNT(*) AS wickets
    FROM deliveries
    WHERE wicket_type IS NOT NULL
      AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
    GROUP BY season, bowler
),
ranked_wickets AS (
    SELECT
        season,
        bowler,
        wickets,
        RANK() OVER (PARTITION BY season ORDER BY wickets DESC) AS wicket_rank
    FROM season_wickets
)
SELECT
    season,
    bowler,
    wickets
FROM ranked_wickets
WHERE wicket_rank = 1
ORDER BY season;

Question: How many matches has PBKS won?
SQL:
SELECT
    COUNT(*) AS punjab_franchise_wins
FROM matches
WHERE winner IN ('Punjab Kings', 'Kings XI Punjab');

Question: Which player has the highest score for MI?
SQL:
SELECT TOP 1
    d.striker AS batter,
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.batting_team = 'Mumbai Indians'
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY runs_in_innings DESC;

Question: What is the most expensive spell by a bowler?
SQL:
SELECT TOP 10
    d.bowler,
    d.bowling_team,
    d.batting_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
    SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, d.innings, d.bowler, d.bowling_team, d.batting_team, m.season, m.start_date, m.venue
HAVING SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) >= 6
ORDER BY runs_conceded DESC;

Question: What are the top 5 highest successful chases?
SQL:
SELECT TOP 5
    d.batting_team AS chasing_team,
    d.bowling_team AS defending_team,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS chase_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings = 2
  AND d.batting_team = m.winner
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY chase_score DESC;

Question: Who has the most death over wickets for CSK?
SQL:
SELECT TOP 10
    d.bowler,
    COUNT(*) AS death_over_wickets
FROM deliveries d
WHERE d.bowling_team = 'Chennai Super Kings'
  AND FLOOR(d.ball) BETWEEN 15 AND 19
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowler
ORDER BY death_over_wickets DESC;

Question: What is the lowest team score?
SQL:
SELECT TOP 10
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS team_score,
    COUNT(d.player_dismissed) AS wickets_lost
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings IN (1, 2)
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
HAVING COUNT(d.player_dismissed) >= 10
ORDER BY team_score ASC;

Question: What is the highest team score?
SQL:
SELECT TOP 10
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS team_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings IN (1, 2)
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY team_score DESC;

Question: Who has the most runs at Narendra Modi Stadium?
SQL:
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE d.venue LIKE '%Narendra Modi%'
   OR d.venue LIKE '%Sardar Patel%'
   OR d.venue LIKE '%Motera%'
GROUP BY d.striker
ORDER BY total_runs DESC;

Question: Which player hit the most fours in a single innings?
SQL:
SELECT TOP 10
    d.striker AS batter,
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings,
    SUM(CASE WHEN d.runs_off_bat = 4 THEN 1 ELSE 0 END) AS fours_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY fours_in_innings DESC;

Question: Which player hit the most sixes in a single innings?
SQL:
SELECT TOP 10
    d.striker AS batter,
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings,
    SUM(CASE WHEN d.runs_off_bat = 6 THEN 1 ELSE 0 END) AS sixes_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY sixes_in_innings DESC;

Question: Which player hit the fastest fifty and in how many balls?
SQL:
WITH batter_ball_progress AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.batting_team,
        d.bowling_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        d.ball,
        SUM(d.runs_off_bat) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
            ORDER BY d.ball
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_runs,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
            ORDER BY d.ball
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
),
fifties AS (
    SELECT
        batter,
        batting_team,
        opponent,
        season,
        start_date,
        venue,
        MIN(running_balls) AS balls_to_hundred
    FROM batter_ball_progress
    WHERE running_runs >= 50
    GROUP BY match_id, innings, batter, batting_team, opponent, season, start_date, venue
)
SELECT TOP 10
    batter,
    batting_team,
    opponent,
    season,
    start_date,
    venue,
    balls_to_fifty
FROM fifties
ORDER BY balls_to_fifty ASC;

Question: Which player hit the fastest hundred and in how many balls?
SQL:
WITH batter_ball_progress AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.batting_team,
        d.bowling_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        d.ball,
        SUM(d.runs_off_bat) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
            ORDER BY d.ball
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_runs,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
            ORDER BY d.ball
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
),
fifties AS (
    SELECT
        batter,
        batting_team,
        opponent,
        season,
        start_date,
        venue,
        MIN(running_balls) AS balls_to_hundred
    FROM batter_ball_progress
    WHERE running_runs >= 100
    GROUP BY match_id, innings, batter, batting_team, opponent, season, start_date, venue
)
SELECT TOP 10
    batter,
    batting_team,
    opponent,
    season,
    start_date,
    venue,
    balls_to_hundred
FROM fifties
ORDER BY balls_to_hundred ASC;

Question: Who has the most runs at Lucknow?
SQL:
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE m.venue LIKE '%Ekana%'
   OR m.venue LIKE '%Lucknow%'
   OR m.city = 'Lucknow'
GROUP BY d.striker
ORDER BY total_runs DESC;


Question: Who has the most wickets at Chepauk?
SQL:
SELECT TOP 10
    d.bowler,
    COUNT(*) AS wickets
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE (
        m.venue LIKE '%Chidambaram%'
        OR m.venue LIKE '%Chepauk%'
        OR m.city = 'Chennai'
      )
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowler
ORDER BY wickets DESC;

Question: Who has the most runs at Chinnaswamy?
SQL:
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE m.venue LIKE '%Chinnaswamy%'
   OR m.city IN ('Bengaluru', 'Bangalore')
GROUP BY d.striker
ORDER BY total_runs DESC;



User question:
{user_question}
"""
    return prompt

def is_safe_select_query(sql_query):
    cleaned_query = sql_query.strip()
    cleaned_lower = cleaned_query.lower()
    # Allow normal SELECT queries and WITH CTE queries
    if not (cleaned_lower.startswith("select") or cleaned_lower.startswith("with")):
        return False
    # Remove one final semicolon if it exists
    query_without_trailing_semicolon = cleaned_lower.rstrip(";").strip()
    # Reject multiple SQL statements
    if ";" in query_without_trailing_semicolon:
        return False
    forbidden_words = [
        "insert ",
        "update ",
        "delete ",
        "drop ",
        "alter ",
        "create ",
        "truncate ",
        "exec ",
        "execute ",
        "merge "
    ]
    for word in forbidden_words:
        if word in cleaned_lower:
            return False
    return True

def answer_question_with_llm(user_question):#generates sql using ollama and runs it on sql server
    prompt=build_sql_prompt(user_question)#builds the model prompt
    raw_response=ask_ollama(prompt)#sends the prompt to the local ollama model
    sql_query=clean_sql_response(raw_response)#cleans code fences from the model response
    if not is_safe_select_query(sql_query):#checks that the generated sql is safe
        raise ValueError("Model generated an unsafe or invalid query")
    result=run_query(sql_query)
    return sql_query,result 

def needs_team_clarification(user_question):
    question_lower = user_question.lower()

    words = question_lower.replace("?", " ").replace(".", " ").replace(",", " ").split()

    if "dc" in words:
        if "delhi" not in question_lower and "deccan" not in question_lower:
            return True

    return False

def get_team_condition_from_question(user_question, column_name):
    question_lower = user_question.lower()

    words = question_lower.replace("?", " ").replace(".", " ").replace(",", " ").split()

    if "csk" in words or "chennai" in question_lower:
        return f"{column_name} = 'Chennai Super Kings'"

    if "mi" in words or "mumbai" in question_lower:
        return f"{column_name} = 'Mumbai Indians'"

    if "rcb" in words or "bangalore" in question_lower or "bengaluru" in question_lower:
        return f"{column_name} = 'Royal Challengers Bangalore'"

    if "kkr" in words or "kolkata" in question_lower:
        return f"{column_name} = 'Kolkata Knight Riders'"

    if "srh" in words or "sunrisers" in question_lower or "hyderabad" in question_lower:
        return f"{column_name} = 'Sunrisers Hyderabad'"

    if "rr" in words or "rajasthan" in question_lower:
        return f"{column_name} = 'Rajasthan Royals'"

    if "pbks" in words or "kxip" in words or "punjab" in question_lower:
        return f"{column_name} IN ('Punjab Kings', 'Kings XI Punjab')"

    if "gt" in words or "gujarat" in question_lower:
        return f"{column_name} = 'Gujarat Titans'"

    if "lsg" in words or "lucknow" in question_lower:
        return f"{column_name} = 'Lucknow Super Giants'"

    if "rps" in words or "pune supergiant" in question_lower:
        return f"{column_name} IN ('Rising Pune Supergiant', 'Rising Pune Supergiants')"

    if "kt" in words or "ktk" in words or "kochi" in question_lower:
        return f"{column_name} = 'Kochi Tuskers Kerala'"

    return None

def build_fastest_milestone_sql(milestone_runs, milestone_name):
    return f"""
WITH batter_ball_progress AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.batting_team,
        d.bowling_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        d.delivery_id,
        d.ball,
        SUM(d.runs_off_bat) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
            ORDER BY d.ball, d.delivery_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_runs,
        SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
            ORDER BY d.ball, d.delivery_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
),
batter_innings AS (
    SELECT
        match_id,
        innings,
        batter,
        batting_team,
        opponent,
        season,
        start_date,
        venue,
        MAX(running_runs) AS final_score
    FROM batter_ball_progress
    GROUP BY match_id, innings, batter, batting_team, opponent, season, start_date, venue
),
milestones AS (
    SELECT
        match_id,
        innings,
        batter,
        MIN(running_balls) AS balls_to_{milestone_name}
    FROM batter_ball_progress
    WHERE running_runs >= {milestone_runs}
    GROUP BY match_id, innings, batter
)
SELECT TOP 10
    b.batter,
    b.batting_team,
    b.opponent,
    b.season,
    b.start_date,
    b.venue,
    b.final_score,
    m.balls_to_{milestone_name}
FROM milestones m
JOIN batter_innings b
    ON m.match_id = b.match_id
    AND m.innings = b.innings
    AND m.batter = b.batter
ORDER BY m.balls_to_{milestone_name} ASC, b.final_score DESC;
""".strip()

def build_curated_sql(user_question):
    question_lower = user_question.lower()

    if "ducks" in question_lower or "duck" in question_lower:
        return """
SELECT TOP 10
    striker AS batter,
    COUNT(*) AS ducks
FROM (
    SELECT
        match_id,
        innings,
        striker,
        SUM(runs_off_bat) AS runs_in_innings,
        MAX(CASE
                WHEN player_dismissed = striker
                     AND wicket_type NOT IN ('retired hurt', 'retired out')
                THEN 1
                ELSE 0
            END) AS was_dismissed
    FROM deliveries
    GROUP BY match_id, innings, striker
) AS batter_innings
WHERE runs_in_innings = 0
  AND was_dismissed = 1
GROUP BY striker
ORDER BY ducks DESC;
""".strip()

    if "highest score" in question_lower and (" for " in question_lower or " csk" in question_lower or " mi" in question_lower):
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {team_condition}
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY runs_in_innings DESC;
""".strip()

    if "highest team score" in question_lower or "highest total" in question_lower:
        return """
SELECT TOP 10
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS team_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings IN (1, 2)
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY team_score DESC;
""".strip()

    if "lowest team score" in question_lower or "lowest total" in question_lower:
        return """
SELECT TOP 10
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS team_score,
    COUNT(d.player_dismissed) AS wickets_lost
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings IN (1, 2)
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
HAVING COUNT(d.player_dismissed) >= 10
ORDER BY team_score ASC;
""".strip()

    if "most expensive spell" in question_lower or "expensive spell" in question_lower:
        return """
SELECT TOP 10
    d.bowler,
    d.bowling_team,
    d.batting_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
    SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, d.innings, d.bowler, d.bowling_team, d.batting_team, m.season, m.start_date, m.venue
HAVING SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) >= 6
ORDER BY runs_conceded DESC;
""".strip()

    if "successful chase" in question_lower or "successful chases" in question_lower or "highest chase" in question_lower:
        return """
SELECT TOP 5
    d.batting_team AS chasing_team,
    d.bowling_team AS defending_team,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS chase_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings = 2
  AND d.batting_team = m.winner
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY chase_score DESC;
""".strip()

    if "sixes" in question_lower and "single season" in question_lower:
        return """
SELECT TOP 10
    season,
    striker AS batter,
    COUNT(*) AS sixes
FROM deliveries
WHERE runs_off_bat = 6
GROUP BY season, striker
ORDER BY sixes DESC;
""".strip()

    if "fours" in question_lower and "single innings" in question_lower:
        return """
SELECT TOP 10
    d.striker AS batter,
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings,
    SUM(CASE WHEN d.runs_off_bat = 4 THEN 1 ELSE 0 END) AS fours_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY fours_in_innings DESC;
""".strip()

    if "sixes" in question_lower and "single innings" in question_lower:
        return """
SELECT TOP 10
    d.striker AS batter,
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings,
    SUM(CASE WHEN d.runs_off_bat = 6 THEN 1 ELSE 0 END) AS sixes_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY sixes_in_innings DESC;
""".strip()

    if "runs against" in question_lower or "most runs against" in question_lower:
        team_condition = get_team_condition_from_question(user_question, "d.bowling_team")

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE {team_condition}
GROUP BY d.striker
ORDER BY total_runs DESC;
""".strip()
        
    if "fastest fifty" in question_lower or "fastest 50" in question_lower:
        return build_fastest_milestone_sql(50, "fifty")

    if "fastest hundred" in question_lower or "fastest 100" in question_lower or "fastest century" in question_lower:
        return build_fastest_milestone_sql(100, "hundred")
    
    if "top 10 run scorers" in question_lower:
        return """
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
GROUP BY striker
ORDER BY total_runs DESC;
""".strip()

    if "top 10 wicket takers" in question_lower:
        return """
SELECT TOP 10
    bowler,
    COUNT(*) AS wickets
FROM deliveries
WHERE wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY bowler
ORDER BY wickets DESC;
""".strip()

    if "most runs in death overs" in question_lower:
        return """
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS death_overs_runs
FROM deliveries
WHERE FLOOR(ball) BETWEEN 15 AND 19
GROUP BY striker
ORDER BY death_overs_runs DESC;
""".strip()

    if "most runs in powerplay" in question_lower or "most runs in powerplay overs" in question_lower:
        return """
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS powerplay_runs
FROM deliveries
WHERE FLOOR(ball) BETWEEN 0 AND 5
GROUP BY striker
ORDER BY powerplay_runs DESC;
""".strip()

    if "most wickets in the powerplay" in question_lower or "most powerplay wickets" in question_lower:
        return """
SELECT TOP 10
    bowler,
    COUNT(*) AS powerplay_wickets
FROM deliveries
WHERE FLOOR(ball) BETWEEN 0 AND 5
  AND wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY bowler
ORDER BY powerplay_wickets DESC;
""".strip()

    if "bowlers took the most wickets in death overs" in question_lower or "most wickets in death overs" in question_lower:
        return """
SELECT TOP 10
    bowler,
    COUNT(*) AS death_overs_wickets
FROM deliveries
WHERE FLOOR(ball) BETWEEN 15 AND 19
  AND wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY bowler
ORDER BY death_overs_wickets DESC;
""".strip()

    if "most wins while chasing" in question_lower:
        return """
SELECT TOP 10
    d.batting_team AS chasing_team,
    COUNT(DISTINCT d.match_id) AS chasing_wins
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings = 2
  AND d.batting_team = m.winner
GROUP BY d.batting_team
ORDER BY chasing_wins DESC;
""".strip()

    if "best economy rate" in question_lower:
        return """
SELECT TOP 10
    bowler,
    SUM(runs_off_bat + extras) AS runs_conceded,
    SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    ROUND(
        SUM(runs_off_bat + extras) * 6.0 /
        NULLIF(SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy_rate
FROM deliveries
GROUP BY bowler
HAVING SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) >= 300
ORDER BY economy_rate ASC;
""".strip()

    if "venues hosted the most" in question_lower or "venue hosted the most" in question_lower:
        return """
SELECT TOP 10
    venue,
    COUNT(*) AS match_count
FROM matches
GROUP BY venue
ORDER BY match_count DESC;
""".strip()

    if "matches were played in each season" in question_lower:
        return """
SELECT
    season,
    COUNT(*) AS match_count
FROM matches
GROUP BY season
ORDER BY season;
""".strip()

    if "teams have won the most matches" in question_lower or "team has won the most matches" in question_lower:
        return """
SELECT TOP 10
    winner AS team,
    COUNT(*) AS wins
FROM matches
WHERE winner IS NOT NULL
GROUP BY winner
ORDER BY wins DESC;
""".strip()

    if "bowlers have conceded the most runs" in question_lower or "bowler conceded the most runs" in question_lower:
        return """
SELECT TOP 10
    bowler,
    SUM(runs_off_bat + extras) AS total_runs_conceded
FROM deliveries
GROUP BY bowler
ORDER BY total_runs_conceded DESC;
""".strip()
    if "how many matches" in question_lower and "won" in question_lower:
        team_condition = get_team_condition_from_question(user_question, "winner")

        if team_condition is not None:
            return f"""
SELECT
    COUNT(*) AS wins
FROM matches
WHERE {team_condition};
""".strip()
    return None

def answer_question_with_fallback(user_question):
    if needs_team_clarification(user_question):
        return {
            "method": "clarification_needed",
            "matched_question": None,
            "sql_query": None,
            "result": None,
            "error": "DC is ambiguous. Please specify whether you mean Delhi Capitals or Deccan Chargers."
        }

    curated_sql = build_curated_sql(user_question)

    if curated_sql is not None:
        result = run_query(curated_sql)

        return {
            "method": "curated_template",
            "matched_question": None,
            "sql_query": curated_sql,
            "result": result,
            "error": None
        }

    try:
        sql_query, result = answer_question_with_llm(user_question)

        return {
            "method": "llm",
            "matched_question": None,
            "sql_query": sql_query,
            "result": result,
            "error": None
        }

    except Exception as error:
        examples = load_examples()

        best_example, score = find_best_example(user_question, examples)

        if best_example is None or score == 0:
            return {
                "method": "failed",
                "matched_question": None,
                "sql_query": None,
                "result": None,
                "error": str(error)
            }

        sql_query = best_example["sql"]

        result = run_query(sql_query)

        return {
            "method": "fallback_question_bank",
            "matched_question": best_example["question"],
            "sql_query": sql_query,
            "result": result,
            "error": str(error)
        }