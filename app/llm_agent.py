import re
import pandas as pd
from app.db import run_query
from app.llm import ask_ollama,clean_sql_response
from app.agent import load_examples,find_best_example
from functools import lru_cache
from app.analysis import (
    analyze_player_dismissals,
    analyze_team_title_chances,
    analyze_bowler_matchups,
    analyze_player_profile,
    analyze_team_profile,
    analyze_player_shots,
    analyze_bowler_strategy,
    analyze_match_summaries,
    analyze_batter_bowling_plan,
    analyze_bowler_vs_batter_decision,
    analyze_team_bowler_recommendation,
    analyze_batter_plan_against_bowler,
)
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
-event
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

Table: match_stages
Columns:
- match_id
- season
- season_year
- start_date
- team_1
- team_2
- winner
- venue
- city
- match_stage
- is_playoff
- is_final

Use match_stages when the user asks about playoffs, finals, semi finals, qualifiers, eliminators, third place playoff, champions, titles, or clutch matches.
Join match_stages to matches or deliveries using match_id.
For finals only, filter is_final = 1.
For all playoff matches, filter is_playoff = 1.

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
- GL means Gujarat Lions.
- PWI means Pune Warriors.
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
- Purple Cap means the highest wicket taker in a season.
- A five-wicket haul, five wicket haul, 5-wicket haul, or fifer means a bowler took at least 5 wickets in one match innings.
- For batting average, allow the user to specify a custom minimum runs threshold. For example, min 1000 runs means HAVING SUM(runs_off_bat) >= 1000.
- For strike rate, allow the user to specify a custom minimum balls threshold. For example, min 800 balls faced means HAVING balls_faced >= 800.
- Highest aggregate in a match means add both teams' innings totals in the same match.
- Most sixes in a match means count all sixes hit by both teams in that match.
- Largest victory by runs uses matches.winner_runs.
- Largest victory by wickets uses matches.winner_wickets.
- Victory by balls remaining must be calculated from the number of legal balls used by the chasing team in innings 2.
- Fours are deliveries where runs_off_bat = 4.
- Sixes are deliveries where runs_off_bat = 6.
- For player fours/sixes, filter striker as the player.
- For player fours/sixes against a team, use bowling_team as the opponent.
- For player fours/sixes for a team, use batting_team as the player's team.
- The current processed deliveries table does not include fielder names, so catches, wicketkeeper stumpings, and fielder run outs cannot be credited to fielders yet.
- The current data can only count dismissal events using wicket_type and player_dismissed.
- For player runs at a venue, filter striker as the player and use venue/city alias rules.
- For player fours/sixes at a venue, filter striker as the player, runs_off_bat = 4 or 6, and use venue/city alias rules.
- For player wickets at a venue, filter bowler as the player and use venue/city alias rules.
- For team runs at a venue, use batting_team.
- For team wickets at a venue, use bowling_team.
- Hundreds mean one batter scored at least 100 runs in one match innings.
- Fifties mean one batter scored between 50 and 99 runs in one match innings.
- For hundreds/fifties by season, group by season, match_id, innings, and striker first.
- For hundreds/fifties at a venue, join matches and filter using venue/city aliases.
- Best bowling figures means wickets taken by a bowler in one match innings.
- For best bowling figures, group by match_id, innings, and bowler.
- For best bowling figures, order by wickets descending, then economy rate ascending, then runs conceded ascending.
- Team highest score means one team's total score in one match innings, not an individual score.
- CSK's highest score means Chennai Super Kings' highest team innings total.
- Team lowest score means one team's lowest innings total.
- If the user asks how many runs a player scored in a season, filter striker as the player and season as the year.
- If the user asks how many wickets a player took in a season, filter bowler as the player and season as the year.
- If the user asks who hit the most sixes or fours in a season, filter runs_off_bat = 6 or 4 and group by striker.
- For player boundaries in a season, count deliveries where striker is the player and runs_off_bat is 4 or 6.
- If the user asks how many fifties/hundreds a player scored in a season, group by match_id, innings, striker, and season first, then count innings with 50-99 or 100+.
- If the user asks who hit the most fifties/hundreds in a season, return the top batters for that season.
- If the user asks who hit the most runs in a season, group by striker and season.
- If the user asks who took the most wickets in a season, group by bowler and season.
- Slowest fifty means the most balls taken by a batter to reach 50 in an innings.
- Slowest hundred means the most balls taken by a batter to reach 100 in an innings.
- Slowest milestone queries should use running batter runs and running balls faced.
- For slowest milestone queries, order by balls_to_milestone descending.
- Slowest milestone queries can be filtered by batting_team, bowling_team, venue, and season if mentioned.

Venue and city alias rules:
- If the user asks about a venue nickname or city, map it to the actual venue names in the database.
- For venue/city questions, prefer joining deliveries d with matches m using match_id, then filter using m.venue, d.venue, or m.city.
- Use LIKE filters for venue aliases because the same stadium may appear with slightly different names.
- Users may refer to players by surname or nickname.
- Thala, MSD, and Dhoni mean MS Dhoni.
- King Kohli and Kohli mean V Kohli.
- Hitman and Rohit mean RG Sharma.
- ABD and de Villiers mean AB de Villiers.
- Universe Boss and Gayle mean CH Gayle.
- SKY means SA Yadav
- For "player runs against a team", filter striker as the player and bowling_team as the opponent.
- For example, Dhoni against MI means striker = 'MS Dhoni' and bowling_team = 'Mumbai Indians'.

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

def get_season_from_question(user_question):
    match = re.search(r"\b(20\d{2}|19\d{2})\b", user_question)

    if match is not None:
        return match.group(1)

    return None

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

@lru_cache(maxsize=1)
def get_known_player_names():
    sql_query = """
SELECT DISTINCT player_name
FROM (
    SELECT striker AS player_name FROM deliveries
    UNION
    SELECT non_striker AS player_name FROM deliveries
    UNION
    SELECT bowler AS player_name FROM deliveries
    UNION
    SELECT player_dismissed AS player_name FROM deliveries WHERE player_dismissed IS NOT NULL
) AS all_players
WHERE player_name IS NOT NULL
ORDER BY player_name;
""".strip()

    result = run_query(sql_query)

    return [str(name) for name in result["player_name"].dropna().tolist()]

def get_stage_condition_from_question(user_question, table_alias="ms"):
    question_lower = clean_text_for_matching(user_question)

    if "final" in question_lower or "finals" in question_lower:
        return f"{table_alias}.is_final = 1"

    if "playoff" in question_lower or "playoffs" in question_lower or "knockout" in question_lower or "clutch" in question_lower:
        return f"{table_alias}.is_playoff = 1"

    if "qualifier 1" in question_lower or "q1" in question_lower:
        return f"{table_alias}.match_stage = 'Qualifier 1'"

    if "qualifier 2" in question_lower or "q2" in question_lower:
        return f"{table_alias}.match_stage = 'Qualifier 2'"

    if "eliminator" in question_lower:
        return f"{table_alias}.match_stage = 'Eliminator'"

    if "semi final" in question_lower or "semi-final" in question_lower or "semifinal" in question_lower:
        return f"{table_alias}.match_stage IN ('Semi Final 1', 'Semi Final 2')"

    if "third place" in question_lower:
        return f"{table_alias}.match_stage = 'Third Place Playoff'"

    return None

def clean_text_for_matching(text):
    text = text.lower()
    text = text.replace("?", " ")
    text = text.replace(".", " ")
    text = text.replace(",", " ")
    text = text.replace("'", " ")
    text = text.replace("-", " ")

    return text


def sql_escape(value):
    return value.replace("'", "''")


def get_player_condition_from_question(user_question, column_name):
    question_lower = clean_text_for_matching(user_question)

    manual_aliases = {
        "dhoni": "MS Dhoni",
        "thala": "MS Dhoni",
        "msd": "MS Dhoni",

        "kohli": "V Kohli",
        "king kohli": "V Kohli",

        "rohit": "RG Sharma",
        "hitman": "RG Sharma",
        "rohit sharma": "RG Sharma",
        
        "bravo": "DJ Bravo",
        "dwayne bravo": "DJ Bravo",
        "dj bravo": "DJ Bravo",

        "gayle": "CH Gayle",
        "universe boss": "CH Gayle",
        "universe_boss": "CH Gayle",

        "abd": "AB de Villiers",
        "ab de villiers": "AB de Villiers",
        "de villiers": "AB de Villiers",

        "raina": "SK Raina",
        "warner": "DA Warner",
        "dhawan": "S Dhawan",
        "gabbar": "S Dhawan",
        "rahul": "KL Rahul",
        "kl rahul": "KL Rahul",
        "pollard": "KA Pollard",
        "jadeja": "RA Jadeja",
        "jaddu": "RA Jadeja",
        "bumrah": "JJ Bumrah",
        "rabada": "K Rabada",
        "kagiso rabada": "K Rabada",
        "yuzi chahal": "YS Chahal",
        "chahal": "YS Chahal",
        "malinga": "SL Malinga",
        "rashid": "Rashid Khan",
        "pooran": "N Pooran",
        "nicholas pooran": "N Pooran",
        "dube": "S Dube",
        "shivam dube": "S Dube",
        "dre russ": "AD Russell",
        "russell": "AD Russell",
        "maxwell": "GJ Maxwell",
        "livingstone": "LS Livingstone",
        "klassen": "H Klaasen",
        "klaasen": "H Klaasen",
        "hetmyer": "SO Hetmyer",

        "pant": "RR Pant",
        "rishabh pant": "RR Pant",

        "bhuvneshwar": "B Kumar",
        "bhuvneshwar kumar": "B Kumar",
        "bhuvi": "B Kumar",

        "suryakumar": "SA Yadav",
        "suryakumar yadav": "SA Yadav",
        "surya": "SA Yadav",
        "sky": "SA Yadav",

        "suryavanshi": "LIKE:%Suryavanshi%",
        "sooryavanshi": "LIKE:%Suryavanshi%",
        "vaibhav sooryavanshi": "LIKE:%Suryavanshi%",

        "deepak chahar": "DL Chahar",
        "rahul chahar": "RD Chahar",
    }

    # First check manual nicknames and common full names
    for alias, player_name in manual_aliases.items():
        if re.search(rf"\b{re.escape(alias)}\b", question_lower):
            if player_name.startswith("LIKE:"):
                like_pattern = player_name.replace("LIKE:", "")
                return f"{column_name} LIKE '{sql_escape(like_pattern)}'"

            return f"{column_name} = '{sql_escape(player_name)}'"

    known_players = get_known_player_names()

    # Check exact database names, e.g. "v kohli", "ms dhoni", "b kumar"
    for player_name in known_players:
        clean_player_name = clean_text_for_matching(player_name)

        if re.search(rf"\b{re.escape(clean_player_name)}\b", question_lower):
            return f"{column_name} = '{sql_escape(player_name)}'"

    ignored_words = {
        "who", "has", "have", "had", "how", "many", "much", "runs", "run",
        "wickets", "wicket", "does", "did", "for", "against", "in", "the",
        "a", "an", "of", "ever", "most", "best", "highest", "lowest",
        "strike", "rate", "average", "score", "scored", "taken", "take",
        "balls", "ball", "bowled", "faced", "with", "min", "minimum",
    }

    question_words = [
        word
        for word in question_lower.split()
        if word not in ignored_words
    ]

    question_word_set = set(question_words)

    candidate_players = []

    for player_name in known_players:
        clean_player_name = clean_text_for_matching(player_name)
        player_parts = clean_player_name.split()

        if len(player_parts) == 0:
            continue

        surname = player_parts[-1]

        if surname not in question_word_set:
            continue

        name_before_surname = player_parts[:-1]

        # Example:
        # database: B Kumar
        # user: bhuvneshwar kumar
        # b from B matches bhuvneshwar
        for name_part in name_before_surname:
            if len(name_part) <= 3:
                initial_letter = name_part[0]

                for question_word in question_words:
                    if question_word != surname and question_word.startswith(initial_letter):
                        candidate_players.append(player_name)

        # Example:
        # database: KS Williamson
        # user: kane williamson
        # k from KS matches kane

    unique_candidates = sorted(set(candidate_players))

    if len(unique_candidates) == 1:
        return f"{column_name} = '{sql_escape(unique_candidates[0])}'"

    # Final fallback: surname-only matching, but only if unique
    surname_candidates = []

    for player_name in known_players:
        clean_player_name = clean_text_for_matching(player_name)
        player_parts = clean_player_name.split()

        if len(player_parts) == 0:
            continue

        surname = player_parts[-1]

        if surname in question_word_set and surname not in ignored_words:
            surname_candidates.append(player_name)

    unique_surname_candidates = sorted(set(surname_candidates))

    if len(unique_surname_candidates) == 1:
        return f"{column_name} = '{sql_escape(unique_surname_candidates[0])}'"

    return None

def get_team_condition_from_question(user_question, column_name):
    question_lower = clean_text_for_matching(user_question)
    words = question_lower.split()

    # Defunct / special teams first
    if "deccan" in question_lower or "deccan chargers" in question_lower:
        return f"{column_name} = 'Deccan Chargers'"

    if "gujarat lions" in question_lower or "gl" in words:
        return f"{column_name} = 'Gujarat Lions'"

    if "pune warriors" in question_lower or "pune warriors india" in question_lower or "pwi" in words:
        return f"{column_name} = 'Pune Warriors'"

    if "kochi" in question_lower or "kt" in words or "ktk" in words:
        return f"{column_name} = 'Kochi Tuskers Kerala'"

    if "rps" in words or "pune supergiant" in question_lower or "rising pune" in question_lower:
        return f"{column_name} IN ('Rising Pune Supergiant', 'Rising Pune Supergiants')"

    # Delhi franchise ambiguity handling
    if (
        "delhi capitals" in question_lower
        or "delhi daredevils" in question_lower
        or "dd" in words
        or ("delhi" in words and ("against" in words or "for" in words or "won" in question_lower or "win" in question_lower))
    ):
        return f"{column_name} IN ('Delhi Capitals', 'Delhi Daredevils')"

    # Punjab franchise name change
    if "pbks" in words or "kxip" in words or "punjab" in question_lower:
        return f"{column_name} IN ('Punjab Kings', 'Kings XI Punjab')"

    # Current / regular IPL teams
    if "csk" in words or "chennai super kings" in question_lower:
        return f"{column_name} = 'Chennai Super Kings'"

    if "mi" in words or "mumbai indians" in question_lower:
        return f"{column_name} = 'Mumbai Indians'"

    if "rcb" in words or "royal challengers" in question_lower or "bangalore" in question_lower or "bengaluru" in question_lower:
        return f"{column_name} IN ('Royal Challengers Bangalore', 'Royal Challengers Bengaluru')"

    if "kkr" in words or "kolkata knight riders" in question_lower:
        return f"{column_name} = 'Kolkata Knight Riders'"

    if "srh" in words or "sunrisers" in question_lower:
        return f"{column_name} = 'Sunrisers Hyderabad'"

    if "rr" in words or "rajasthan royals" in question_lower:
        return f"{column_name} = 'Rajasthan Royals'"

    if "gt" in words or "gujarat titans" in question_lower:
        return f"{column_name} = 'Gujarat Titans'"

    if "lsg" in words or "lucknow super giants" in question_lower:
        return f"{column_name} = 'Lucknow Super Giants'"

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
def has_player_reference(user_question):
    return get_player_condition_from_question(user_question,"dummy_column") is not None

def get_minimum_runs_from_question(user_question, default_value):
    question_lower = user_question.lower()

    match = re.search(r"(?:min|minimum|at least)\s*\(?\s*(\d+)", question_lower)

    if match is not None:
        return int(match.group(1))

    match = re.search(r"(\d+)\s*runs", question_lower)

    if match is not None:
        return int(match.group(1))

    return default_value


def get_minimum_balls_from_question(user_question, default_value):
    question_lower = user_question.lower()

    match = re.search(r"(?:min|minimum|at least)\s*\(?\s*(\d+)", question_lower)

    if match is not None:
        return int(match.group(1))

    match = re.search(r"(\d+)\s*balls", question_lower)

    if match is not None:
        return int(match.group(1))

    return default_value

def get_boundary_type_from_question(user_question):
    question_lower = clean_text_for_matching(user_question)
    words = question_lower.split()

    if "sixes" in words or "six" in words or "6s" in words or "maximums" in words:
        return 6, "sixes"

    if "fours" in words or "four" in words or "4s" in words:
        return 4, "fours"

    return None, None

def has_venue_context(user_question):
    question_clean = " " + clean_text_for_matching(user_question) + " "

    return (
        " at " in question_clean
        or " in " in question_clean
        or "venue" in question_clean
        or "stadium" in question_clean
        or "ground" in question_clean
    )


def get_venue_condition_from_question(user_question):
    question_lower = clean_text_for_matching(user_question)
    words = question_lower.split()

    if "ekana" in question_lower or "lucknow" in words:
        return "(m.venue LIKE '%Ekana%' OR m.venue LIKE '%Lucknow%' OR m.city = 'Lucknow')"

    if "dy patil" in question_lower:
        return "(m.venue LIKE '%DY Patil%')"

    if "vizag" in words or "visakhapatnam" in words:
        return "(m.venue LIKE '%Visakhapatnam%' OR m.venue LIKE '%ACA-VDCA%' OR m.city = 'Visakhapatnam')"

    if "chinnaswamy" in question_lower or "bengaluru" in words or "bangalore" in words:
        return "(m.venue LIKE '%Chinnaswamy%' OR m.city IN ('Bengaluru', 'Bangalore'))"

    if "chepauk" in words or "chennai" in words:
        return "(m.venue LIKE '%Chidambaram%' OR m.venue LIKE '%Chepauk%' OR m.city = 'Chennai')"

    if "mullanpur" in words or "new chandigarh" in question_lower:
        return "(m.venue LIKE '%Mullanpur%' OR m.venue LIKE '%New Chandigarh%')"

    if "mohali" in words or "chandigarh" in words:
        return "(m.venue LIKE '%Mohali%' OR m.venue LIKE '%Chandigarh%' OR m.city = 'Chandigarh')"

    if "uppal" in words or "hyderabad" in words:
        return "(m.venue LIKE '%Uppal%' OR m.venue LIKE '%Hyderabad%' OR m.city = 'Hyderabad')"

    if "motera" in words or "ahmedabad" in words or "narendra modi" in question_lower or "sardar patel" in question_lower:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Sardar Patel%' OR m.venue LIKE '%Motera%' OR m.city = 'Ahmedabad')"

    if "wankhede" in words or "mumbai" in words:
        return "(m.venue LIKE '%Wankhede%' OR m.city = 'Mumbai')"

    if "eden gardens" in question_lower or "kolkata" in words:
        return "(m.venue LIKE '%Eden Gardens%' OR m.city = 'Kolkata')"

    if "jaipur" in words:
        return "(m.venue LIKE '%Sawai Mansingh%' OR m.city = 'Jaipur')"

    if "dharamsala" in words:
        return "(m.venue LIKE '%Himachal Pradesh%' OR m.city = 'Dharamsala')"

    if "pune" in words:
        return "(m.venue LIKE '%Maharashtra Cricket Association%' OR m.venue LIKE '%Subrata Roy%' OR m.city = 'Pune')"

    if "raipur" in words:
        return "(m.venue LIKE '%Raipur%' OR m.city = 'Raipur')"

    if "guwahati" in words or "barsapara" in words:
        return "(m.venue LIKE '%Guwahati%' OR m.venue LIKE '%Barsapara%' OR m.city = 'Guwahati')"

    if "delhi" in words or "kotla" in words or "arun jaitley" in question_lower:
        return "(m.venue LIKE '%Arun Jaitley%' OR m.venue LIKE '%Feroz Shah Kotla%' OR m.city = 'Delhi')"

    if "rajkot" in words:
        return "(m.venue LIKE '%Saurashtra%' OR m.city = 'Rajkot')"

    if "abu dhabi" in question_lower or "zayed" in words:
        return "(m.venue LIKE '%Zayed%' OR m.city = 'Abu Dhabi')"

    if "dubai" in words:
        return "(m.venue LIKE '%Dubai%' OR m.city = 'Dubai')"

    if "sharjah" in words:
        return "(m.venue LIKE '%Sharjah%' OR m.city = 'Sharjah')"

    if "wanderers" in words:
        return "(m.venue LIKE '%Wanderers%')"

    return None

def get_team_label_from_question(user_question):
    question_lower = clean_text_for_matching(user_question)
    words = question_lower.split()

    # Defunct / special teams first
    if "deccan" in question_lower or "deccan chargers" in question_lower:
        return "Deccan Chargers"

    if "gujarat lions" in question_lower or "gl" in words:
        return "Gujarat Lions"

    if "pune warriors" in question_lower or "pune warriors india" in question_lower or "pwi" in words:
        return "Pune Warriors"

    if "kochi" in question_lower or "kt" in words or "ktk" in words:
        return "Kochi Tuskers Kerala"

    if "rps" in words or "pune supergiant" in question_lower or "rising pune" in question_lower:
        return "Rising Pune Supergiant"

    # Franchise name changes
    if (
        "delhi capitals" in question_lower
        or "delhi daredevils" in question_lower
        or "dd" in words
        or "delhi" in words
    ):
        return "Delhi franchise"

    if "pbks" in words or "kxip" in words or "punjab" in question_lower:
        return "Punjab franchise"

    # Current / regular teams
    if "csk" in words or "chennai super kings" in question_lower:
        return "Chennai Super Kings"

    if "mi" in words or "mumbai indians" in question_lower:
        return "Mumbai Indians"

    if "rcb" in words or "royal challengers" in question_lower or "bangalore" in question_lower or "bengaluru" in question_lower:
        return "Royal Challengers Bangalore/Bengaluru"

    if "kkr" in words or "kolkata knight riders" in question_lower:
        return "Kolkata Knight Riders"

    if "srh" in words or "sunrisers" in question_lower:
        return "Sunrisers Hyderabad"

    if "rr" in words or "rajasthan royals" in question_lower:
        return "Rajasthan Royals"

    if "gt" in words or "gujarat titans" in question_lower:
        return "Gujarat Titans"

    if "lsg" in words or "lucknow super giants" in question_lower:
        return "Lucknow Super Giants"

    return "Selected team"

def get_question_fragment_after_keyword(user_question, keyword):
    question_clean = clean_text_for_matching(user_question)

    match = re.search(rf"\b{re.escape(keyword)}\b\s+(.+)", question_clean)

    if match is None:
        return None

    fragment = match.group(1)

    stop_phrases = [
        " against ",
        " at ",
        " in ",
        " during ",
        " season ",
        " ever ",
        " overall ",
        " with ",
    ]

    for stop_phrase in stop_phrases:
        index = fragment.find(stop_phrase)

        if index != -1:
            fragment = fragment[:index]

    fragment = fragment.strip()

    if fragment == "":
        return None

    return fragment


def get_team_condition_after_keyword(user_question, keyword, column_name):
    fragment = get_question_fragment_after_keyword(user_question, keyword)

    if fragment is None:
        return None

    return get_team_condition_from_question(fragment, column_name)


def get_team_label_after_keyword(user_question, keyword):
    fragment = get_question_fragment_after_keyword(user_question, keyword)

    if fragment is None:
        return "Selected team"

    return get_team_label_from_question(fragment)

def build_fastest_milestone_sql_with_filters(milestone_runs, milestone_name, user_question):
    question_lower = user_question.lower()

    where_clauses = []

    if "for" in question_lower:
        team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
        if team_condition is not None:
            where_clauses.append(team_condition)

    if "against" in question_lower:
        opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
        if opponent_condition is not None:
            where_clauses.append(opponent_condition)

    venue_condition = get_venue_condition_from_question(user_question)
    venue_context = venue_condition is not None and has_venue_context(user_question)

    if venue_context:
        where_clauses.append(venue_condition)

    where_sql = ""

    if len(where_clauses) > 0:
        where_sql = "WHERE " + " AND ".join(where_clauses)

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
    {where_sql}
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
        MIN(running_balls) AS balls_to_milestone
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
    m.balls_to_milestone AS balls_to_{milestone_name}
FROM milestones m
JOIN batter_innings b
    ON m.match_id = b.match_id
    AND m.innings = b.innings
    AND m.batter = b.batter
ORDER BY m.balls_to_milestone ASC, b.final_score DESC;
""".strip()
def get_question_fragment_before_keyword(user_question, keyword):
    question_clean = clean_text_for_matching(user_question)
    index = question_clean.find(keyword)

    if index == -1:
        return None

    fragment = question_clean[:index].strip()

    if fragment == "":
        return None

    return fragment


def get_team_condition_before_keyword(user_question, keyword, column_name):
    fragment = get_question_fragment_before_keyword(user_question, keyword)

    if fragment is None:
        return None

    return get_team_condition_from_question(fragment, column_name)


def get_team_label_before_keyword(user_question, keyword):
    fragment = get_question_fragment_before_keyword(user_question, keyword)

    if fragment is None:
        return "Selected team"

    return get_team_label_from_question(fragment)


def get_wicket_number_from_question(user_question):
    question_lower = clean_text_for_matching(user_question)

    ordinal_words = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }

    for word, number in ordinal_words.items():
        if f"{word} wicket" in question_lower:
            return number

    match = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+wicket\b", question_lower)

    if match is not None:
        return int(match.group(1))

    return None
def get_top_n_from_question(user_question, default_value=10):
    question_lower = clean_text_for_matching(user_question)

    patterns = [
        r"\btop\s+(\d+)\b",
        r"\blist\s+the\s+(\d+)\b",
        r"\blist\s+(\d+)\b",
        r"\b(\d+)\s+highest\b",
        r"\b(\d+)\s+best\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, question_lower)

        if match is not None:
            value = int(match.group(1))
            return max(1, min(value, 50))

    return default_value

def build_slowest_milestone_sql_with_filters(milestone_runs, milestone_name, user_question):
    question_lower = user_question.lower()

    where_clauses = []

    if "for" in question_lower:
        team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
        if team_condition is not None:
            where_clauses.append(team_condition)

    if "against" in question_lower:
        opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
        if opponent_condition is not None:
            where_clauses.append(opponent_condition)

    venue_condition = get_venue_condition_from_question(user_question)
    venue_context = venue_condition is not None and has_venue_context(user_question)

    if venue_context:
        where_clauses.append(venue_condition)

    where_sql = ""

    if len(where_clauses) > 0:
        where_sql = "WHERE " + " AND ".join(where_clauses)

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
    {where_sql}
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
        MIN(running_balls) AS balls_to_milestone
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
    m.balls_to_milestone AS balls_to_{milestone_name}
FROM milestones m
JOIN batter_innings b
    ON m.match_id = b.match_id
    AND m.innings = b.innings
    AND m.batter = b.batter
ORDER BY m.balls_to_milestone DESC, b.final_score ASC;
""".strip()

def get_phase_condition_from_question(user_question, table_alias="d"):
    question_lower = clean_text_for_matching(user_question)

    if "powerplay" in question_lower or "power play" in question_lower:
        return f"FLOOR({table_alias}.ball) BETWEEN 0 AND 5", "powerplay"

    if "middle over" in question_lower or "middle overs" in question_lower:
        return f"FLOOR({table_alias}.ball) BETWEEN 6 AND 14", "middle_overs"

    if "death over" in question_lower or "death overs" in question_lower:
        return f"FLOOR({table_alias}.ball) BETWEEN 15 AND 19", "death_overs"

    if "final over" in question_lower or "last over" in question_lower:
        return f"FLOOR({table_alias}.ball) = 19", "final_over"

    if "last 5 overs" in question_lower or "last five overs" in question_lower:
        return f"FLOOR({table_alias}.ball) BETWEEN 15 AND 19", "last_5_overs"

    return None, None

def get_numeric_threshold_from_question(user_question, default_value):
    question_lower = user_question.lower()

    match = re.search(r"\b(\d+)\s*(?:runs?|wickets?)\b", question_lower)
    if match is not None:
        return int(match.group(1))

    match = re.search(r"\bto\s+(\d+)\b", question_lower)
    if match is not None:
        return int(match.group(1))

    return default_value


def get_group_mode_from_question(user_question):
    question_lower = clean_text_for_matching(user_question)

    if (
        "per team" in question_lower
        or "by team" in question_lower
        or "each team" in question_lower
        or "for each team" in question_lower
    ):
        return "team"

    if (
        "per venue" in question_lower
        or "by venue" in question_lower
        or "each venue" in question_lower
        or "for each venue" in question_lower
    ):
        return "venue"

    return "overall"


def build_fastest_runs_milestone_sql(user_question):
    run_threshold = get_numeric_threshold_from_question(user_question, 1000)
    group_mode = get_group_mode_from_question(user_question)

    where_clauses = []

    if group_mode != "team" and "for" in user_question.lower():
        team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
        if team_condition is not None:
            where_clauses.append(team_condition)

    venue_condition = get_venue_condition_from_question(user_question)
    if group_mode != "venue" and venue_condition is not None and has_venue_context(user_question):
        where_clauses.append(venue_condition)

    where_sql = ""
    if len(where_clauses) > 0:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    if group_mode == "team":
        group_expr = "d.batting_team"
        final_filter = "WHERE group_rank = 1"
        top_limit = 50
    elif group_mode == "venue":
        group_expr = "m.venue"
        final_filter = "WHERE group_rank = 1"
        top_limit = 50
    else:
        group_expr = "'Overall'"
        final_filter = ""
        top_limit = 10

    return f"""
WITH filtered_deliveries AS (
    SELECT
        d.match_id,
        d.innings,
        d.delivery_id,
        d.ball,
        d.striker,
        d.batting_team,
        d.bowling_team,
        d.runs_off_bat,
        d.wides,
        d.noballs,
        m.start_date,
        YEAR(CAST(m.start_date AS date)) AS season_year,
        m.venue,
        {group_expr} AS group_name
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    {where_sql}
),
batter_innings AS (
    SELECT
        group_name,
        striker,
        match_id,
        innings,
        MIN(start_date) AS innings_date,
        MIN(delivery_id) AS first_delivery_id,
        ROW_NUMBER() OVER (
            PARTITION BY group_name, striker
            ORDER BY MIN(start_date), match_id, innings
        ) AS innings_number
    FROM filtered_deliveries
    GROUP BY group_name, striker, match_id, innings
),
ball_progress AS (
    SELECT
        fd.group_name,
        fd.striker AS batter,
        fd.batting_team,
        fd.bowling_team AS opponent,
        fd.match_id,
        fd.innings,
        fd.season_year,
        fd.start_date,
        fd.venue,
        fd.ball,
        fd.delivery_id,
        bi.innings_number,
        SUM(fd.runs_off_bat) OVER (
            PARTITION BY fd.group_name, fd.striker
            ORDER BY fd.start_date, fd.match_id, fd.innings, fd.ball, fd.delivery_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_runs,
        SUM(CASE WHEN fd.wides IS NULL AND fd.noballs IS NULL THEN 1 ELSE 0 END) OVER (
            PARTITION BY fd.group_name, fd.striker
            ORDER BY fd.start_date, fd.match_id, fd.innings, fd.ball, fd.delivery_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS balls_faced_to_milestone
    FROM filtered_deliveries fd
    JOIN batter_innings bi
        ON fd.group_name = bi.group_name
        AND fd.striker = bi.striker
        AND fd.match_id = bi.match_id
        AND fd.innings = bi.innings
),
milestone_rows AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY group_name, batter
            ORDER BY start_date, match_id, innings, ball, delivery_id
        ) AS milestone_rank
    FROM ball_progress
    WHERE cumulative_runs >= {run_threshold}
),
first_milestones AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY group_name
            ORDER BY innings_number ASC, balls_faced_to_milestone ASC, start_date ASC
        ) AS group_rank
    FROM milestone_rows
    WHERE milestone_rank = 1
)
SELECT TOP {top_limit}
    group_name AS milestone_scope,
    batter,
    batting_team AS team_at_milestone,
    opponent,
    season_year,
    start_date,
    venue,
    innings_number AS innings_to_{run_threshold}_runs,
    balls_faced_to_milestone AS balls_faced_to_{run_threshold}_runs,
    cumulative_runs AS runs_at_milestone
FROM first_milestones
{final_filter}
ORDER BY innings_to_{run_threshold}_runs ASC, balls_faced_to_{run_threshold}_runs ASC;
""".strip()


def build_fastest_wickets_milestone_sql(user_question):
    wicket_threshold = get_numeric_threshold_from_question(user_question, 50)
    group_mode = get_group_mode_from_question(user_question)

    where_clauses = []

    if group_mode != "team" and "for" in user_question.lower():
        team_condition = get_team_condition_after_keyword(user_question, "for", "d.bowling_team")
        if team_condition is not None:
            where_clauses.append(team_condition)

    venue_condition = get_venue_condition_from_question(user_question)
    if group_mode != "venue" and venue_condition is not None and has_venue_context(user_question):
        where_clauses.append(venue_condition)

    where_sql = ""
    if len(where_clauses) > 0:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    if group_mode == "team":
        group_expr = "d.bowling_team"
        final_filter = "WHERE group_rank = 1"
        top_limit = 50
    elif group_mode == "venue":
        group_expr = "m.venue"
        final_filter = "WHERE group_rank = 1"
        top_limit = 50
    else:
        group_expr = "'Overall'"
        final_filter = ""
        top_limit = 10

    return f"""
WITH filtered_deliveries AS (
    SELECT
        d.match_id,
        d.innings,
        d.delivery_id,
        d.ball,
        d.bowler,
        d.bowling_team,
        d.batting_team AS opponent,
        d.runs_off_bat,
        d.wides,
        d.noballs,
        d.wicket_type,
        m.start_date,
        YEAR(CAST(m.start_date AS date)) AS season_year,
        m.venue,
        {group_expr} AS group_name
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    {where_sql}
),
bowler_innings AS (
    SELECT
        group_name,
        bowler,
        match_id,
        innings,
        MIN(start_date) AS innings_date,
        MIN(delivery_id) AS first_delivery_id,
        ROW_NUMBER() OVER (
            PARTITION BY group_name, bowler
            ORDER BY MIN(start_date), match_id, innings
        ) AS innings_number
    FROM filtered_deliveries
    GROUP BY group_name, bowler, match_id, innings
),
ball_progress AS (
    SELECT
        fd.group_name,
        fd.bowler,
        fd.bowling_team AS team_at_milestone,
        fd.opponent,
        fd.match_id,
        fd.innings,
        fd.season_year,
        fd.start_date,
        fd.venue,
        fd.ball,
        fd.delivery_id,
        bi.innings_number,
        SUM(CASE
            WHEN fd.wicket_type IS NOT NULL
                 AND fd.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
            ELSE 0
        END) OVER (
            PARTITION BY fd.group_name, fd.bowler
            ORDER BY fd.start_date, fd.match_id, fd.innings, fd.ball, fd.delivery_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_wickets,
        SUM(CASE WHEN fd.wides IS NULL AND fd.noballs IS NULL THEN 1 ELSE 0 END) OVER (
            PARTITION BY fd.group_name, fd.bowler
            ORDER BY fd.start_date, fd.match_id, fd.innings, fd.ball, fd.delivery_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS legal_balls_to_milestone
    FROM filtered_deliveries fd
    JOIN bowler_innings bi
        ON fd.group_name = bi.group_name
        AND fd.bowler = bi.bowler
        AND fd.match_id = bi.match_id
        AND fd.innings = bi.innings
),
milestone_rows AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY group_name, bowler
            ORDER BY start_date, match_id, innings, ball, delivery_id
        ) AS milestone_rank
    FROM ball_progress
    WHERE cumulative_wickets >= {wicket_threshold}
),
first_milestones AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY group_name
            ORDER BY innings_number ASC, legal_balls_to_milestone ASC, start_date ASC
        ) AS group_rank
    FROM milestone_rows
    WHERE milestone_rank = 1
)
SELECT TOP {top_limit}
    group_name AS milestone_scope,
    bowler,
    team_at_milestone,
    opponent,
    season_year,
    start_date,
    venue,
    innings_number AS innings_to_{wicket_threshold}_wickets,
    legal_balls_to_milestone AS balls_bowled_to_{wicket_threshold}_wickets,
    cumulative_wickets AS wickets_at_milestone
FROM first_milestones
{final_filter}
ORDER BY innings_to_{wicket_threshold}_wickets ASC, balls_bowled_to_{wicket_threshold}_wickets ASC;
""".strip()

def build_curated_sql(user_question):
    question_lower = user_question.lower()

    venue_condition = get_venue_condition_from_question(user_question)
    venue_context = venue_condition is not None and has_venue_context(user_question)

    boundary_runs, boundary_name = get_boundary_type_from_question(user_question)
    # Fastest batting milestone, e.g. fastest to 1000 runs
    if (
        "fastest" in question_lower
        and ("run" in question_lower or "runs" in question_lower)
        and (
            "to" in question_lower
            or "reach" in question_lower
            or "milestone" in question_lower
        )
    ):
        return build_fastest_runs_milestone_sql(user_question)

    # Fastest bowling milestone, e.g. fastest to 50 wickets / 100 wickets
    if (
        "fastest" in question_lower
        and ("wicket" in question_lower or "wickets" in question_lower)
        and (
            "to" in question_lower
            or "reach" in question_lower
            or "milestone" in question_lower
        )
    ):
        return build_fastest_wickets_milestone_sql(user_question)
    
    # Highest individual score overall, by team, against team, or at venue
    if (
        "highest individual score" in question_lower
        or "highest score by a player" in question_lower
        or "highest player score" in question_lower
        or (
            "highest score" in question_lower
            and "team score" not in question_lower
            and "team total" not in question_lower
            and "total" not in question_lower
        )
    ):
        where_clauses = []

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
            if team_condition is not None:
                where_clauses.append(team_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        season = get_season_from_question(user_question)
        if season is not None:
            where_clauses.append(f"YEAR(CAST(m.start_date AS date)) = {season}")

        where_sql = ""

        if len(where_clauses) > 0:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        top_n = get_top_n_from_question(user_question, 10)

        return f"""
SELECT TOP {top_n}
    d.striker AS batter,
    d.batting_team,
    d.bowling_team AS opponent,
    YEAR(CAST(m.start_date AS date)) AS season_year,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
{where_sql}
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, YEAR(CAST(m.start_date AS date)), m.start_date, m.venue
ORDER BY runs DESC, balls_faced ASC;
""".strip()
    
    # Teams with most playoff appearances, including pre-2011 semi-finals
    if (
        "playoffs most times" in question_lower
        or "most playoff appearances" in question_lower
        or "reached the playoffs most" in question_lower
        or "qualified for playoffs most" in question_lower
        or "playoff appearances" in question_lower
    ):
        return """
WITH playoff_teams AS (
    SELECT
        match_id,
        season_year,
        team_1 AS team
    FROM match_stages
    WHERE is_playoff = 1

    UNION ALL

    SELECT
        match_id,
        season_year,
        team_2 AS team
    FROM match_stages
    WHERE is_playoff = 1
),
team_years AS (
    SELECT DISTINCT
        team,
        season_year
    FROM playoff_teams
)
SELECT
    team,
    COUNT(*) AS playoff_seasons,
    STRING_AGG(CAST(season_year AS VARCHAR(10)), ', ') AS years
FROM team_years
GROUP BY team
ORDER BY playoff_seasons DESC, team;
""".strip()
    
    # Teams with most final appearances
    if (
        "most final appearances" in question_lower
        or "final appearances" in question_lower
        or "appeared in the finals most" in question_lower
        or "appeared in the finals the most" in question_lower
        or "appeared in finals most" in question_lower
        or "appeared in finals the most" in question_lower
        or "played the most finals" in question_lower
        or "most finals" in question_lower
        or "most times in the final" in question_lower
        or "most times in finals" in question_lower
    ):
        return """
WITH final_teams AS (
    SELECT
        match_id,
        season_year,
        team_1 AS team
    FROM match_stages
    WHERE is_final = 1

    UNION ALL

    SELECT
        match_id,
        season_year,
        team_2 AS team
    FROM match_stages
    WHERE is_final = 1
),
team_years AS (
    SELECT DISTINCT
        team,
        season_year
    FROM final_teams
)
SELECT
    team,
    COUNT(*) AS final_appearances,
    STRING_AGG(CAST(season_year AS VARCHAR(10)), ', ') AS years
FROM team_years
GROUP BY team
ORDER BY final_appearances DESC, team;
""".strip()
    
    # Most times out in the nineties
    if (
        "out in the nineties" in question_lower
        or "out in nineties" in question_lower
        or "dismissed in the nineties" in question_lower
        or "dismissed in nineties" in question_lower
        or "most nineties" in question_lower
    ):
        return """
WITH batter_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.batting_team,
        YEAR(CAST(m.start_date AS date)) AS season_year,
        SUM(d.runs_off_bat) AS runs,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
                 AND d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('retired hurt', 'retired out')
            THEN 1
            ELSE 0
        END) AS dismissed
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    GROUP BY d.match_id, d.innings, d.striker, d.batting_team, YEAR(CAST(m.start_date AS date))
)
SELECT TOP 10
    batter,
    COUNT(*) AS times_out_in_nineties
FROM batter_innings
WHERE runs BETWEEN 90 AND 99
  AND dismissed = 1
GROUP BY batter
ORDER BY times_out_in_nineties DESC, batter;
""".strip()
    
    # Most runs in a phase: powerplay, middle overs, death overs
    # Default meaning = in a single match/innings.
    # Use "overall", "all time", "aggregate", or "total" for cumulative totals.
    phase_condition, phase_label = get_phase_condition_from_question(user_question, "d")

    if (
        phase_condition is not None
        and "runs" in question_lower
        and (
            "most" in question_lower
            or "highest" in question_lower
            or "maximum" in question_lower
        )
        and "to win" not in question_lower
    ):
        top_n = get_top_n_from_question(user_question, 10)

        wants_overall = (
            "overall" in question_lower
            or "all time" in question_lower
            or "all-time" in question_lower
            or "aggregate" in question_lower
            or "total" in question_lower
        )

        if "team" in question_lower or "teams" in question_lower:
            if wants_overall:
                return f"""
SELECT TOP {top_n}
    d.batting_team,
    SUM(d.runs_off_bat + d.extras) AS total_runs_in_{phase_label}
FROM deliveries d
WHERE {phase_condition}
GROUP BY d.batting_team
ORDER BY total_runs_in_{phase_label} DESC;
""".strip()

            return f"""
SELECT TOP {top_n}
    d.batting_team,
    d.bowling_team AS opponent,
    YEAR(CAST(m.start_date AS date)) AS season_year,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS runs_in_{phase_label}
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {phase_condition}
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, YEAR(CAST(m.start_date AS date)), m.start_date, m.venue
ORDER BY runs_in_{phase_label} DESC;
""".strip()

        if (
            "player" in question_lower
            or "batter" in question_lower
            or "batsman" in question_lower
            or "who" in question_lower
        ):
            if wants_overall:
                return f"""
SELECT TOP {top_n}
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs_in_{phase_label}
FROM deliveries d
WHERE {phase_condition}
GROUP BY d.striker
ORDER BY total_runs_in_{phase_label} DESC;
""".strip()

            return f"""
SELECT TOP {top_n}
    d.striker AS batter,
    d.batting_team,
    d.bowling_team AS opponent,
    YEAR(CAST(m.start_date AS date)) AS season_year,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_{phase_label}
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {phase_condition}
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, YEAR(CAST(m.start_date AS date)), m.start_date, m.venue
ORDER BY runs_in_{phase_label} DESC;
""".strip()
        
    # Most runs in final over / last 5 overs to win a game
    phase_condition, phase_label = get_phase_condition_from_question(user_question, "d")

    if (
        phase_condition is not None
        and "to win" in question_lower
        and ("runs" in question_lower or "scored" in question_lower)
    ):
        return f"""
WITH chase_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.batting_team AS chasing_team,
        d.bowling_team AS defending_team,
        SUM(d.runs_off_bat + d.extras) AS chase_total
    FROM deliveries d
    GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team
),
phase_runs AS (
    SELECT
        d.match_id,
        d.innings,
        d.batting_team AS chasing_team,
        d.bowling_team AS defending_team,
        SUM(d.runs_off_bat + d.extras) AS runs_scored_in_{phase_label}
    FROM deliveries d
    WHERE {phase_condition}
    GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team
),
before_phase_runs AS (
    SELECT
        d.match_id,
        d.innings,
        d.batting_team AS chasing_team,
        SUM(d.runs_off_bat + d.extras) AS runs_before_{phase_label}
    FROM deliveries d
    WHERE NOT ({phase_condition})
      AND d.innings = 2
    GROUP BY d.match_id, d.innings, d.batting_team
),
target_scores AS (
    SELECT
        d.match_id,
        SUM(d.runs_off_bat + d.extras) + 1 AS target
    FROM deliveries d
    WHERE d.innings = 1
    GROUP BY d.match_id
)
SELECT TOP 10
    pr.chasing_team,
    pr.defending_team,
    YEAR(CAST(m.start_date AS date)) AS season_year,
    m.start_date,
    m.venue,
    ts.target,
    COALESCE(bpr.runs_before_{phase_label}, 0) AS runs_before_{phase_label},
    ts.target - COALESCE(bpr.runs_before_{phase_label}, 0) AS runs_required_at_start_of_{phase_label},
    pr.runs_scored_in_{phase_label},
    m.winner,
    CASE
        WHEN m.winner_runs IS NOT NULL THEN CONCAT('won by ', CAST(CAST(m.winner_runs AS INT) AS VARCHAR(20)), ' runs')
        WHEN m.winner_wickets IS NOT NULL THEN CONCAT('won by ', CAST(CAST(m.winner_wickets AS INT) AS VARCHAR(20)), ' wickets')
        ELSE 'result recorded'
    END AS result_margin
FROM phase_runs pr
JOIN matches m
    ON pr.match_id = m.match_id
JOIN target_scores ts
    ON pr.match_id = ts.match_id
LEFT JOIN before_phase_runs bpr
    ON pr.match_id = bpr.match_id
    AND pr.innings = bpr.innings
    AND pr.chasing_team = bpr.chasing_team
WHERE pr.innings = 2
  AND pr.chasing_team = m.winner
ORDER BY pr.runs_scored_in_{phase_label} DESC;
""".strip()
    

    # Last season a batter crossed a run threshold, e.g. Rohit's last 500-run season
    if (
        ("last" in question_lower or "when was" in question_lower or "when did" in question_lower)
        and "season" in question_lower
        and ("run" in question_lower or "runs" in question_lower)
    ):
        player_condition = get_player_condition_from_question(user_question, "d.striker")

        if player_condition is not None:
            run_threshold_match = re.search(r"\b(\d+)\s*runs?\b", question_lower)

            if run_threshold_match is not None:
                run_threshold = int(run_threshold_match.group(1))
            else:
                run_threshold = 500

            return f"""
SELECT TOP 1
    d.striker AS batter,
    YEAR(CAST(m.start_date AS date)) AS season_year,
    SUM(d.runs_off_bat) AS runs
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {player_condition}
GROUP BY d.striker, YEAR(CAST(m.start_date AS date))
HAVING SUM(d.runs_off_bat) >= {run_threshold}
ORDER BY season_year DESC;
""".strip()
        
    # Last season a bowler crossed a wicket threshold, e.g. Bumrah's last 20-wicket season
    if (
        ("last" in question_lower or "when was" in question_lower or "when did" in question_lower)
        and "season" in question_lower
        and ("wicket" in question_lower or "wickets" in question_lower)
    ):
        bowler_condition = get_player_condition_from_question(user_question, "d.bowler")

        # Handles informal possessive spellings like "bumrahs"
        if bowler_condition is None:
            cleaned_question = user_question.lower()
            cleaned_question = cleaned_question.replace("bumrahs", "bumrah")
            cleaned_question = cleaned_question.replace("chahals", "chahal")
            cleaned_question = cleaned_question.replace("bravos", "bravo")
            cleaned_question = cleaned_question.replace("rashids", "rashid")
            cleaned_question = cleaned_question.replace("malingas", "malinga")
            bowler_condition = get_player_condition_from_question(cleaned_question, "d.bowler")

        if bowler_condition is not None:
            wicket_threshold_match = re.search(r"\b(\d+)\s*wickets?\b", question_lower)

            if wicket_threshold_match is not None:
                wicket_threshold = int(wicket_threshold_match.group(1))
            else:
                wicket_threshold = 20

            return f"""
SELECT TOP 1
    d.bowler,
    YEAR(CAST(m.start_date AS date)) AS season_year,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS wickets
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {bowler_condition}
GROUP BY d.bowler, YEAR(CAST(m.start_date AS date))
HAVING COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) >= {wicket_threshold}
ORDER BY season_year DESC;
""".strip()


    # IPL champions / titles
    if (
        "champion" in question_lower
        or "champions" in question_lower
        or "title" in question_lower
        or "titles" in question_lower
        or "trophy" in question_lower
    ):
        season = get_season_from_question(user_question)

        if season is not None:
            return f"""
SELECT
    ms.season_year,
    ms.team_1,
    ms.team_2,
    ms.winner AS champion,
    ms.venue,
    ms.start_date
FROM match_stages ms
WHERE ms.is_final = 1
  AND ms.season_year = {season};
""".strip()

        return """
SELECT
    winner AS team,
    COUNT(*) AS titles
FROM match_stages
WHERE is_final = 1
GROUP BY winner
ORDER BY titles DESC;
""".strip()
    # Most runs in playoffs/finals/stage matches
    if "runs" in question_lower:
        stage_condition = get_stage_condition_from_question(user_question, "ms")

        if stage_condition is not None and ("most" in question_lower or "who" in question_lower):
            return f"""
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
JOIN match_stages ms
    ON d.match_id = ms.match_id
WHERE {stage_condition}
GROUP BY d.striker
ORDER BY total_runs DESC;
""".strip()
    # Most wickets in playoffs/finals/stage matches
    if "wickets" in question_lower or "wicket" in question_lower:
        stage_condition = get_stage_condition_from_question(user_question, "ms")

        if stage_condition is not None and ("most" in question_lower or "who" in question_lower):
            return f"""
SELECT TOP 10
    d.bowler,
    COUNT(*) AS wickets
FROM deliveries d
JOIN match_stages ms
    ON d.match_id = ms.match_id
WHERE {stage_condition}
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowler
ORDER BY wickets DESC;
""".strip()
        
    # Highest individual score in playoffs/finals/stage matches
    if "highest score" in question_lower or "highest individual score" in question_lower or "best score" in question_lower:
        stage_condition = get_stage_condition_from_question(user_question, "ms")

        if stage_condition is not None and ("individual" in question_lower or "player" in question_lower or "who" in question_lower):
            return f"""
SELECT TOP 10
    d.striker AS batter,
    d.batting_team,
    d.bowling_team AS opponent,
    ms.season_year,
    ms.match_stage,
    ms.venue,
    SUM(d.runs_off_bat) AS runs_in_innings
FROM deliveries d
JOIN match_stages ms
    ON d.match_id = ms.match_id
WHERE {stage_condition}
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, ms.season_year, ms.match_stage, ms.venue
ORDER BY runs_in_innings DESC;
""".strip()
        
    # Best bowling figures in playoffs/finals/stage matches
    if "best bowling figures" in question_lower or "best figures" in question_lower:
        stage_condition = get_stage_condition_from_question(user_question, "ms")

        if stage_condition is not None:
            return f"""
SELECT TOP 10
    bowler,
    bowling_team,
    batting_team AS opponent,
    season_year,
    match_stage,
    venue,
    wickets,
    runs_conceded,
    legal_balls,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy_rate
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        d.bowling_team,
        d.batting_team,
        ms.season_year,
        ms.match_stage,
        ms.venue,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
    FROM deliveries d
    JOIN match_stages ms
        ON d.match_id = ms.match_id
    WHERE {stage_condition}
    GROUP BY d.match_id, d.innings, d.bowler, d.bowling_team, d.batting_team, ms.season_year, ms.match_stage, ms.venue
) AS bowling_figures
WHERE wickets > 0
ORDER BY wickets DESC, economy_rate ASC, runs_conceded ASC;
""".strip()


    # Slowest fifty/hundred overall, for team, against team, at venue, or combined filters
    if (
        "slowest fifty" in question_lower
        or "slowest 50" in question_lower
        or "slowest half century" in question_lower
        or "slowest half-century" in question_lower
        or "slowest hundred" in question_lower
        or "slowest 100" in question_lower
        or "slowest century" in question_lower
    ):
        if (
            "slowest fifty" in question_lower
            or "slowest 50" in question_lower
            or "slowest half century" in question_lower
            or "slowest half-century" in question_lower
        ):
            return build_slowest_milestone_sql_with_filters(50, "fifty", user_question)

        if (
            "slowest hundred" in question_lower
            or "slowest 100" in question_lower
            or "slowest century" in question_lower
        ):
            return build_slowest_milestone_sql_with_filters(100, "hundred", user_question)
    # List hat-tricks ever, by team, or at venue
    if (
        "hattrick" in question_lower
        or "hattricks" in question_lower
        or "hat trick" in question_lower
        or "hat tricks" in question_lower
        or "hat-trick" in question_lower
        or "hat-tricks" in question_lower
    ):
        where_clauses = [
            "d.wides IS NULL",
            "d.noballs IS NULL"
        ]

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.bowling_team")
            if team_condition is not None:
                where_clauses.append(team_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.batting_team")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        where_sql = " AND ".join(where_clauses)

        return f"""
WITH legal_bowler_balls AS (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        d.bowling_team,
        d.batting_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        d.ball,
        d.delivery_id,
        d.player_dismissed,
        CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
            ELSE 0
        END AS credited_wicket,
        ROW_NUMBER() OVER (
            PARTITION BY d.match_id, d.innings, d.bowler
            ORDER BY d.ball, d.delivery_id
        ) AS bowler_ball_number
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
),
hattricks AS (
    SELECT
        b1.bowler,
        b1.bowling_team,
        b1.opponent,
        b1.season,
        b1.start_date,
        b1.venue,
        b1.ball AS first_wicket_ball,
        b1.player_dismissed AS wicket_1,
        b2.player_dismissed AS wicket_2,
        b3.player_dismissed AS wicket_3
    FROM legal_bowler_balls b1
    JOIN legal_bowler_balls b2
        ON b1.match_id = b2.match_id
        AND b1.innings = b2.innings
        AND b1.bowler = b2.bowler
        AND b2.bowler_ball_number = b1.bowler_ball_number + 1
    JOIN legal_bowler_balls b3
        ON b1.match_id = b3.match_id
        AND b1.innings = b3.innings
        AND b1.bowler = b3.bowler
        AND b3.bowler_ball_number = b1.bowler_ball_number + 2
    WHERE b1.credited_wicket = 1
      AND b2.credited_wicket = 1
      AND b3.credited_wicket = 1
),
final_results AS (
    SELECT
        CAST(NULL AS VARCHAR(200)) AS message,
        bowler,
        bowling_team,
        opponent,
        season,
        start_date,
        venue,
        first_wicket_ball,
        wicket_1,
        wicket_2,
        wicket_3
    FROM hattricks

    UNION ALL

    SELECT
        'No hat-tricks found for this filter.' AS message,
        NULL AS bowler,
        NULL AS bowling_team,
        NULL AS opponent,
        NULL AS season,
        NULL AS start_date,
        NULL AS venue,
        NULL AS first_wicket_ball,
        NULL AS wicket_1,
        NULL AS wicket_2,
        NULL AS wicket_3
    WHERE NOT EXISTS (
        SELECT 1
        FROM hattricks
    )
)
SELECT *
FROM final_results
ORDER BY
    CASE WHEN message IS NULL THEN 0 ELSE 1 END,
    season,
    start_date;
""".strip()

    # Most wides / no-balls / extras bowled, overall or for a team
    if (
        "wides" in question_lower
        or "wide balls" in question_lower
        or "no balls" in question_lower
        or "noballs" in question_lower
        or "no-balls" in question_lower
        or "extras" in question_lower
    ):
        metric_name = None
        metric_expression = None

        if "wides" in question_lower or "wide balls" in question_lower:
            metric_name = "wides"
            metric_expression = "COALESCE(d.wides, 0)"

        elif "no balls" in question_lower or "noballs" in question_lower or "no-balls" in question_lower:
            metric_name = "no_balls"
            metric_expression = "COALESCE(d.noballs, 0)"

        elif "extras" in question_lower:
            metric_name = "extras"
            metric_expression = "COALESCE(d.extras, 0)"

        if metric_name is not None:
            team_condition = None
            team_label = None

            if "for" in question_lower:
                team_condition = get_team_condition_after_keyword(user_question, "for", "d.bowling_team")
                team_label = get_team_label_after_keyword(user_question, "for")

            # Team leaderboard: which team bowled/conceded the most wides/no-balls/extras
            if (
                "which team" in question_lower
                or "team has" in question_lower
                or "teams have" in question_lower
                or "by team" in question_lower
                or "per team" in question_lower
            ):
                return f"""
SELECT TOP 10
    d.bowling_team AS team,
    SUM({metric_expression}) AS total_{metric_name}
FROM deliveries d
GROUP BY d.bowling_team
ORDER BY total_{metric_name} DESC;
""".strip()

            # Bowler leaderboard for a selected team
            if team_condition is not None:
                return f"""
SELECT TOP 10
    d.bowler,
    '{team_label}' AS team_group,
    SUM({metric_expression}) AS total_{metric_name}
FROM deliveries d
WHERE {team_condition}
GROUP BY d.bowler
ORDER BY total_{metric_name} DESC;
""".strip()

            # Overall bowler leaderboard
            return f"""
SELECT TOP 10
    d.bowler,
    SUM({metric_expression}) AS total_{metric_name}
FROM deliveries d
GROUP BY d.bowler
ORDER BY total_{metric_name} DESC;
""".strip()
    # Biggest win by runs, overall or filtered by winner/opponent/venue
    if (
        ("biggest win" in question_lower or "largest win" in question_lower or "biggest victory" in question_lower or "largest victory" in question_lower)
        and "runs" in question_lower
    ):
        where_clauses = ["wm.winner_runs IS NOT NULL", "wm.winner_runs > 0"]

        if "for" in question_lower:
            winner_condition = get_team_condition_after_keyword(user_question, "for", "wm.winner")
            if winner_condition is not None:
                where_clauses.append(winner_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "wm.opponent")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition.replace("m.", "wm."))

        where_sql = " AND ".join(where_clauses)

        return f"""
WITH match_teams AS (
    SELECT DISTINCT
        match_id,
        batting_team AS team
    FROM deliveries
),
winner_matches AS (
    SELECT
        m.match_id,
        m.winner,
        mt.team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        m.city,
        m.winner_runs
    FROM matches m
    JOIN match_teams mt
        ON m.match_id = mt.match_id
    WHERE mt.team <> m.winner
)
SELECT TOP 10
    wm.winner,
    wm.opponent,
    wm.season,
    wm.start_date,
    wm.venue,
    wm.winner_runs AS victory_margin_runs
FROM winner_matches wm
WHERE {where_sql}
ORDER BY wm.winner_runs DESC;
""".strip()

    # Biggest win by balls remaining, overall or filtered by winner/opponent/venue
    if (
        ("biggest win" in question_lower or "largest win" in question_lower or "biggest victory" in question_lower or "largest victory" in question_lower)
        and ("balls" in question_lower or "balls left" in question_lower or "balls remaining" in question_lower)
    ):
        where_clauses = ["120 - legal_balls_used >= 0"]

        if "for" in question_lower:
            winner_condition = get_team_condition_after_keyword(user_question, "for", "winner")
            if winner_condition is not None:
                where_clauses.append(winner_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "opponent")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition.replace("m.", ""))

        where_sql = " AND ".join(where_clauses)

        return f"""
WITH chase_balls AS (
    SELECT
        d.match_id,
        m.winner,
        d.bowling_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        m.city,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls_used
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE d.innings = 2
      AND d.batting_team = m.winner
    GROUP BY d.match_id, m.winner, d.bowling_team, m.season, m.start_date, m.venue, m.city
)
SELECT TOP 10
    winner,
    opponent,
    season,
    start_date,
    venue,
    120 - legal_balls_used AS balls_remaining
FROM chase_balls
WHERE {where_sql}
ORDER BY balls_remaining DESC;
""".strip()
    # Biggest win by runs, overall or filtered by winner/opponent/venue
    if (
        ("biggest win" in question_lower or "largest win" in question_lower or "biggest victory" in question_lower or "largest victory" in question_lower)
        and "runs" in question_lower
    ):
        where_clauses = ["wm.winner_runs IS NOT NULL", "wm.winner_runs > 0"]

        if "for" in question_lower:
            winner_condition = get_team_condition_after_keyword(user_question, "for", "wm.winner")
            if winner_condition is not None:
                where_clauses.append(winner_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "wm.opponent")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition.replace("m.", "wm."))

        where_sql = " AND ".join(where_clauses)

        return f"""
WITH match_teams AS (
    SELECT DISTINCT
        match_id,
        batting_team AS team
    FROM deliveries
),
winner_matches AS (
    SELECT
        m.match_id,
        m.winner,
        mt.team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        m.city,
        m.winner_runs
    FROM matches m
    JOIN match_teams mt
        ON m.match_id = mt.match_id
    WHERE mt.team <> m.winner
)
SELECT TOP 10
    wm.winner,
    wm.opponent,
    wm.season,
    wm.start_date,
    wm.venue,
    wm.winner_runs AS victory_margin_runs
FROM winner_matches wm
WHERE {where_sql}
ORDER BY wm.winner_runs DESC;
""".strip()

    # Biggest win by balls remaining, overall or filtered by winner/opponent/venue
    if (
        ("biggest win" in question_lower or "largest win" in question_lower or "biggest victory" in question_lower or "largest victory" in question_lower)
        and ("balls" in question_lower or "balls left" in question_lower or "balls remaining" in question_lower)
    ):
        where_clauses = ["120 - legal_balls_used >= 0"]

        if "for" in question_lower:
            winner_condition = get_team_condition_after_keyword(user_question, "for", "winner")
            if winner_condition is not None:
                where_clauses.append(winner_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "opponent")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition.replace("m.", ""))

        where_sql = " AND ".join(where_clauses)

        return f"""
WITH chase_balls AS (
    SELECT
        d.match_id,
        m.winner,
        d.bowling_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        m.city,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls_used
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE d.innings = 2
      AND d.batting_team = m.winner
    GROUP BY d.match_id, m.winner, d.bowling_team, m.season, m.start_date, m.venue, m.city
)
SELECT TOP 10
    winner,
    opponent,
    season,
    start_date,
    venue,
    120 - legal_balls_used AS balls_remaining
FROM chase_balls
WHERE {where_sql}
ORDER BY balls_remaining DESC;
""".strip()

    # Biggest win by runs, overall or filtered by winner/opponent/venue
    if (
        ("biggest win" in question_lower or "largest win" in question_lower or "biggest victory" in question_lower or "largest victory" in question_lower)
        and "runs" in question_lower
    ):
        where_clauses = ["wm.winner_runs IS NOT NULL", "wm.winner_runs > 0"]

        if "for" in question_lower:
            winner_condition = get_team_condition_after_keyword(user_question, "for", "wm.winner")
            if winner_condition is not None:
                where_clauses.append(winner_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "wm.opponent")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition.replace("m.", "wm."))

        where_sql = " AND ".join(where_clauses)

        return f"""
WITH match_teams AS (
    SELECT DISTINCT
        match_id,
        batting_team AS team
    FROM deliveries
),
winner_matches AS (
    SELECT
        m.match_id,
        m.winner,
        mt.team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        m.city,
        m.winner_runs
    FROM matches m
    JOIN match_teams mt
        ON m.match_id = mt.match_id
    WHERE mt.team <> m.winner
)
SELECT TOP 10
    wm.winner,
    wm.opponent,
    wm.season,
    wm.start_date,
    wm.venue,
    wm.winner_runs AS victory_margin_runs
FROM winner_matches wm
WHERE {where_sql}
ORDER BY wm.winner_runs DESC;
""".strip()

    # Biggest win by balls remaining, overall or filtered by winner/opponent/venue
    if (
        ("biggest win" in question_lower or "largest win" in question_lower or "biggest victory" in question_lower or "largest victory" in question_lower)
        and ("balls" in question_lower or "balls left" in question_lower or "balls remaining" in question_lower)
    ):
        where_clauses = ["120 - legal_balls_used >= 0"]

        if "for" in question_lower:
            winner_condition = get_team_condition_after_keyword(user_question, "for", "winner")
            if winner_condition is not None:
                where_clauses.append(winner_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "opponent")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition.replace("m.", ""))

        where_sql = " AND ".join(where_clauses)

        return f"""
WITH chase_balls AS (
    SELECT
        d.match_id,
        m.winner,
        d.bowling_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        m.city,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls_used
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE d.innings = 2
      AND d.batting_team = m.winner
    GROUP BY d.match_id, m.winner, d.bowling_team, m.season, m.start_date, m.venue, m.city
)
SELECT TOP 10
    winner,
    opponent,
    season,
    start_date,
    venue,
    120 - legal_balls_used AS balls_remaining
FROM chase_balls
WHERE {where_sql}
ORDER BY balls_remaining DESC;
""".strip()

    # Worst bowling figures / most runs conceded in one innings spell
    if (
        "worst bowling figures" in question_lower
        or "worst figures" in question_lower
        or "most runs conceded in a spell" in question_lower
        or "most expensive figures" in question_lower
    ):
        where_clauses = []

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.bowling_team")
            if team_condition is not None:
                where_clauses.append(team_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.batting_team")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        where_sql = ""

        if len(where_clauses) > 0:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        return f"""
SELECT TOP 10
    bowler,
    bowling_team,
    batting_team AS opponent,
    season,
    start_date,
    venue,
    wickets,
    runs_conceded,
    legal_balls,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy_rate
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        d.bowling_team,
        d.batting_team,
        m.season,
        m.start_date,
        m.venue,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    {where_sql}
    GROUP BY d.match_id, d.innings, d.bowler, d.bowling_team, d.batting_team, m.season, m.start_date, m.venue
) AS bowling_figures
WHERE legal_balls >= 6
ORDER BY runs_conceded DESC, wickets ASC, economy_rate DESC;
""".strip()

    # Most matches appeared in delivery data, overall or for a team
    if (
        "most matches played" in question_lower
        or "most appearances" in question_lower
        or "played the most matches" in question_lower
    ):
        team_filter = ""
        team_select = ""

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "team")
            team_label = get_team_label_after_keyword(user_question, "for")

            if team_condition is not None:
                team_filter = f"WHERE {team_condition}"
                team_select = f", '{team_label}' AS team_group"

        return f"""
WITH player_match_appearances AS (
    SELECT DISTINCT
        match_id,
        striker AS player,
        batting_team AS team
    FROM deliveries

    UNION

    SELECT DISTINCT
        match_id,
        non_striker AS player,
        batting_team AS team
    FROM deliveries

    UNION

    SELECT DISTINCT
        match_id,
        bowler AS player,
        bowling_team AS team
    FROM deliveries
),
filtered_appearances AS (
    SELECT *
    FROM player_match_appearances
    {team_filter}
)
SELECT TOP 10
    player
    {team_select},
    COUNT(DISTINCT match_id) AS matches_appeared_in_data
FROM filtered_appearances
GROUP BY player
ORDER BY matches_appeared_in_data DESC;
""".strip()

    # Most consecutive wins or defeats in a season
    if (
        "most consecutive wins" in question_lower
        or "longest winning streak" in question_lower
        or "most consecutive defeats" in question_lower
        or "longest losing streak" in question_lower
    ):
        result_filter = "W"

        if "defeats" in question_lower or "losing" in question_lower or "losses" in question_lower:
            result_filter = "L"

        team_filter = ""

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "team")
            if team_condition is not None:
                team_filter = f"WHERE {team_condition}"

        return f"""
WITH team_matches AS (
    SELECT DISTINCT
        d.match_id,
        m.season,
        m.start_date,
        d.batting_team AS team,
        m.winner
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE d.innings IN (1, 2)
),
filtered_team_matches AS (
    SELECT *
    FROM team_matches
    {team_filter}
),
team_results AS (
    SELECT
        match_id,
        season,
        start_date,
        team,
        CASE
            WHEN winner = team THEN 'W'
            ELSE 'L'
        END AS result
    FROM filtered_team_matches
    WHERE winner IS NOT NULL
),
numbered_results AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY team, season
            ORDER BY start_date, match_id
        ) AS rn_all,
        ROW_NUMBER() OVER (
            PARTITION BY team, season, result
            ORDER BY start_date, match_id
        ) AS rn_result
    FROM team_results
),
streaks AS (
    SELECT
        team,
        season,
        result,
        rn_all - rn_result AS streak_group,
        COUNT(*) AS streak_length,
        MIN(start_date) AS streak_start,
        MAX(start_date) AS streak_end
    FROM numbered_results
    GROUP BY team, season, result, rn_all - rn_result
)
SELECT TOP 10
    team,
    season,
    result,
    streak_length,
    streak_start,
    streak_end
FROM streaks
WHERE result = '{result_filter}'
ORDER BY streak_length DESC, season;
""".strip()
    # Highest partnerships, overall, for team, and/or specific wicket
    if "partnership" in question_lower or "partnerships" in question_lower:
        wicket_number = get_wicket_number_from_question(user_question)

        where_clauses = ["d.innings IN (1, 2)"]

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
            if team_condition is not None:
                where_clauses.append(team_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        where_sql = " AND ".join(where_clauses)

        wicket_filter = ""

        if wicket_number is not None:
            wicket_filter = f"WHERE ps.wicket_number = {wicket_number}"

        return f"""
WITH innings_balls AS (
    SELECT
        d.match_id,
        d.innings,
        d.delivery_id,
        d.ball,
        d.batting_team,
        d.bowling_team,
        d.striker,
        d.non_striker,
        m.season,
        m.start_date,
        m.venue,
        d.runs_off_bat + d.extras AS total_runs_on_ball,
        SUM(CASE
                WHEN d.player_dismissed IS NOT NULL
                     AND d.wicket_type NOT IN ('retired hurt', 'retired out')
                THEN 1
                ELSE 0
            END) OVER (
                PARTITION BY d.match_id, d.innings
                ORDER BY d.ball, d.delivery_id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS wickets_before_ball
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
),
partnership_balls AS (
    SELECT
        *,
        COALESCE(wickets_before_ball, 0) + 1 AS wicket_number
    FROM innings_balls
),
partnership_scores AS (
    SELECT
        match_id,
        innings,
        wicket_number,
        batting_team,
        bowling_team AS opponent,
        season,
        start_date,
        venue,
        SUM(total_runs_on_ball) AS partnership_runs
    FROM partnership_balls
    GROUP BY match_id, innings, wicket_number, batting_team, bowling_team, season, start_date, venue
),
partnership_players_raw AS (
    SELECT DISTINCT
        match_id,
        innings,
        wicket_number,
        striker AS player
    FROM partnership_balls

    UNION

    SELECT DISTINCT
        match_id,
        innings,
        wicket_number,
        non_striker AS player
    FROM partnership_balls
),
partnership_players AS (
    SELECT
        match_id,
        innings,
        wicket_number,
        MIN(player) AS player_1,
        MAX(player) AS player_2
    FROM partnership_players_raw
    GROUP BY match_id, innings, wicket_number
)
SELECT TOP 10
    pp.player_1,
    pp.player_2,
    ps.batting_team,
    ps.opponent,
    ps.wicket_number,
    ps.season,
    ps.start_date,
    ps.venue,
    ps.partnership_runs
FROM partnership_scores ps
JOIN partnership_players pp
    ON ps.match_id = pp.match_id
    AND ps.innings = pp.innings
    AND ps.wicket_number = pp.wicket_number
{wicket_filter}
ORDER BY ps.partnership_runs DESC;
""".strip()

    # Team win percentage against another team
    if "win percentage" in question_lower and "against" in question_lower:
        team_condition = get_team_condition_before_keyword(user_question, "win percentage", "team")
        team_winner_condition = get_team_condition_before_keyword(user_question, "win percentage", "winner")
        team_label = get_team_label_before_keyword(user_question, "win percentage")

        opponent_condition = get_team_condition_after_keyword(user_question, "against", "team")
        opponent_winner_condition = get_team_condition_after_keyword(user_question, "against", "winner")
        opponent_label = get_team_label_after_keyword(user_question, "against")

        if team_condition is not None and opponent_condition is not None:
            return f"""
WITH match_teams AS (
    SELECT DISTINCT
        d.match_id,
        d.batting_team AS team
    FROM deliveries d
),
head_to_head_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.winner
    FROM matches m
    WHERE EXISTS (
        SELECT 1
        FROM match_teams t
        WHERE t.match_id = m.match_id
          AND {team_condition}
    )
    AND EXISTS (
        SELECT 1
        FROM match_teams t
        WHERE t.match_id = m.match_id
          AND {opponent_condition}
    )
)
SELECT
    '{team_label}' AS team,
    '{opponent_label}' AS opponent,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN {team_winner_condition} THEN 1 ELSE 0 END) AS matches_won,
    SUM(CASE WHEN {opponent_winner_condition} THEN 1 ELSE 0 END) AS matches_lost,
    ROUND(
        SUM(CASE WHEN {team_winner_condition} THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS win_percentage
FROM head_to_head_matches;
""".strip()
    # Head-to-head record of two teams
    if "head to head" in question_lower or "head-to-head" in question_lower:
        question_clean = clean_text_for_matching(user_question)

        if " and " in question_clean:
            left_fragment, right_fragment = question_clean.split(" and ", 1)

            team_1_condition = get_team_condition_from_question(left_fragment, "team")
            team_2_condition = get_team_condition_from_question(right_fragment, "team")

            team_1_winner_condition = get_team_condition_from_question(left_fragment, "winner")
            team_2_winner_condition = get_team_condition_from_question(right_fragment, "winner")

            team_1_label = get_team_label_from_question(left_fragment)
            team_2_label = get_team_label_from_question(right_fragment)

            if team_1_condition is not None and team_2_condition is not None:
                return f"""
WITH match_teams AS (
    SELECT DISTINCT
        d.match_id,
        d.batting_team AS team
    FROM deliveries d
),
head_to_head_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.winner
    FROM matches m
    WHERE EXISTS (
        SELECT 1
        FROM match_teams t
        WHERE t.match_id = m.match_id
          AND {team_1_condition}
    )
    AND EXISTS (
        SELECT 1
        FROM match_teams t
        WHERE t.match_id = m.match_id
          AND {team_2_condition}
    )
)
SELECT
    '{team_1_label}' AS team_1,
    '{team_2_label}' AS team_2,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN {team_1_winner_condition} THEN 1 ELSE 0 END) AS team_1_wins,
    SUM(CASE WHEN {team_2_winner_condition} THEN 1 ELSE 0 END) AS team_2_wins,
    COUNT(*)
        - SUM(CASE WHEN {team_1_winner_condition} THEN 1 ELSE 0 END)
        - SUM(CASE WHEN {team_2_winner_condition} THEN 1 ELSE 0 END) AS no_result_or_other
FROM head_to_head_matches;
""".strip()
    # Player runs in a specific season
    if "runs" in question_lower:
        season = get_season_from_question(user_question)
        player_condition = get_player_condition_from_question(user_question, "pd.batter")
        if season is not None and player_condition is not None:
            extra_filters = ""

            if "for" in question_lower:
                team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
                if team_condition is not None:
                    extra_filters += f"\n  AND {team_condition}"

            if "against" in question_lower:
                opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
                if opponent_condition is not None:
                    extra_filters += f"\n  AND {opponent_condition}"

            if venue_context:
                extra_filters += f"\n  AND {venue_condition}"

            return f"""
SELECT
    d.striker AS batter,
    d.season,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE {player_condition}
  AND d.season = '{season}'
  {extra_filters}
GROUP BY d.striker, d.season;
""".strip()


    # Best batting season ever by total runs, overall or for a team
    if (
        get_season_from_question(user_question) is None
        and "runs" in question_lower
        and (
            "best season" in question_lower
            or "highest ever runs in a season" in question_lower
            or "highest runs in a season" in question_lower
            or "most runs in a season" in question_lower
            or "most runs in single season" in question_lower
            or "most runs in a single season" in question_lower
        )
    ):
        team_condition = None
        team_label = None

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
            team_label = get_team_label_after_keyword(user_question, "for")

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.season,
    d.striker AS batter,
    '{team_label}' AS team_group,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE {team_condition}
GROUP BY d.season, d.striker
ORDER BY total_runs DESC;
""".strip()

        return """
SELECT TOP 10
    d.season,
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
GROUP BY d.season, d.striker
ORDER BY total_runs DESC;
""".strip()

    # Best bowling season ever by total wickets, overall or for a team
    if (
        get_season_from_question(user_question) is None
        and ("wickets" in question_lower or "wicket" in question_lower)
        and (
            "best season" in question_lower
            or "highest ever wickets in a season" in question_lower
            or "highest wickets in a season" in question_lower
            or "most wickets in a season" in question_lower
            or "most wickets in single season" in question_lower
            or "most wickets in a single season" in question_lower
        )
    ):
        team_condition = None
        team_label = None

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.bowling_team")
            team_label = get_team_label_after_keyword(user_question, "for")

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.season,
    d.bowler,
    '{team_label}' AS team_group,
    COUNT(*) AS wickets
FROM deliveries d
WHERE {team_condition}
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.season, d.bowler
ORDER BY wickets DESC;
""".strip()

        return """
SELECT TOP 10
    d.season,
    d.bowler,
    COUNT(*) AS wickets
FROM deliveries d
WHERE d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.season, d.bowler
ORDER BY wickets DESC;
""".strip()
    # Player fifties/hundreds in a specific season
    if (
        ("fifties" in question_lower or "hundreds" in question_lower or "centuries" in question_lower)
        and get_season_from_question(user_question) is not None
    ):
        season = get_season_from_question(user_question)
        player_condition = get_player_condition_from_question(user_question, "pd.batter")

        milestone_name = "hundreds"
        milestone_filter = "runs_in_innings >= 100"

        if "fifties" in question_lower:
            milestone_name = "fifties"
            milestone_filter = "runs_in_innings BETWEEN 50 AND 99"

        if player_condition is not None:
            return f"""
SELECT
    batter,
    season,
    COUNT(*) AS {milestone_name}
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.season,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    WHERE {player_condition}
      AND d.season = '{season}'
    GROUP BY d.match_id, d.innings, d.striker, d.season
) AS batter_innings
WHERE {milestone_filter}
GROUP BY batter, season;
""".strip()

        if "most" in question_lower or "who" in question_lower:
            return f"""
SELECT TOP 10
    batter,
    season,
    COUNT(*) AS {milestone_name}
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.season,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    WHERE d.season = '{season}'
    GROUP BY d.match_id, d.innings, d.striker, d.season
) AS batter_innings
WHERE {milestone_filter}
GROUP BY batter, season
ORDER BY {milestone_name} DESC;
""".strip()
    # Most runs in a specific season
    if (
        "most runs" in question_lower
        and get_season_from_question(user_question) is not None
        and "single season" not in question_lower
    ):
        season = get_season_from_question(user_question)

        return f"""
SELECT TOP 10
    d.striker AS batter,
    d.season,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE d.season = '{season}'
GROUP BY d.striker, d.season
ORDER BY total_runs DESC;
""".strip()

    # Most wickets in a specific season
    if (
        "most wickets" in question_lower
        and get_season_from_question(user_question) is not None
        and "single season" not in question_lower
    ):
        season = get_season_from_question(user_question)

        return f"""
SELECT TOP 10
    d.bowler,
    d.season,
    COUNT(*) AS wickets
FROM deliveries d
WHERE d.season = '{season}'
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowler, d.season
ORDER BY wickets DESC;
""".strip()
    # Player wickets in a specific season
    if "wickets" in question_lower or "wicket" in question_lower:
        season = get_season_from_question(user_question)
        player_condition = get_player_condition_from_question(user_question, "d.bowler")

        if season is not None and player_condition is not None:
            extra_filters = ""

            if "for" in question_lower:
                team_condition = get_team_condition_after_keyword(user_question, "for", "d.bowling_team")
                if team_condition is not None:
                    extra_filters += f"\n  AND {team_condition}"

            if "against" in question_lower:
                opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.batting_team")
                if opponent_condition is not None:
                    extra_filters += f"\n  AND {opponent_condition}"

            if venue_context:
                extra_filters += f"\n  AND {venue_condition}"

            return f"""
SELECT
    d.bowler,
    d.season,
    COUNT(*) AS wickets
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {player_condition}
  AND d.season = '{season}'
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
  {extra_filters}
GROUP BY d.bowler, d.season;
""".strip()

    # Most fours/sixes in a specific season
    if boundary_runs is not None:
        season = get_season_from_question(user_question)

        if season is not None:
            player_condition = get_player_condition_from_question(user_question, "d.striker")

            if player_condition is not None:
                return f"""
SELECT
    d.striker AS batter,
    d.season,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
WHERE {player_condition}
  AND d.season = '{season}'
  AND d.runs_off_bat = {boundary_runs}
GROUP BY d.striker, d.season;
""".strip()

            team_condition = None
            team_label = "Selected team"

            if "for" in question_lower:
                team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
                team_label = get_team_label_after_keyword(user_question, "for")

            opponent_condition = None
            opponent_label = "Selected opponent"

            if "against" in question_lower:
                opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
                opponent_label = get_team_label_after_keyword(user_question, "against")

            where_clauses = [
                f"d.season = '{season}'",
                f"d.runs_off_bat = {boundary_runs}"
            ]

            select_parts = [
                "d.striker AS batter",
                "d.season"
            ]

            group_parts = [
                "d.striker",
                "d.season"
            ]

            if team_condition is not None:
                where_clauses.append(team_condition)
                select_parts.append(f"'{team_label}' AS team_group")

            if opponent_condition is not None:
                where_clauses.append(opponent_condition)
                select_parts.append(f"'{opponent_label}' AS opponent_group")

            where_sql = " AND ".join(where_clauses)
            select_sql = ",\n    ".join(select_parts)
            group_sql = ", ".join(group_parts)

            return f"""
SELECT TOP 10
    {select_sql},
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
WHERE {where_sql}
GROUP BY {group_sql}
ORDER BY total_{boundary_name} DESC;
""".strip()
    # Highest team scores for a team/opponent, optionally at a venue
    if (
        ("highest score" in question_lower
         or "highest scores" in question_lower
         or "best score" in question_lower
         or "best scores" in question_lower
         or "highest total" in question_lower
         or "highest totals" in question_lower
         or "best total" in question_lower
         or "best totals" in question_lower)
        and "individual" not in question_lower
        and "player" not in question_lower
    ):
        top_n = get_top_n_from_question(user_question, 10)

        team_condition = None
        team_label = None

        opponent_condition = None
        opponent_label = None

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
            team_label = get_team_label_after_keyword(user_question, "for")

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
            opponent_label = get_team_label_after_keyword(user_question, "against")

        where_clauses = []

        if team_condition is not None:
            where_clauses.append(team_condition)

        if opponent_condition is not None:
            where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        if len(where_clauses) > 0:
            where_sql = "WHERE " + " AND ".join(where_clauses)

            team_select = "d.batting_team AS batting_team"
            opponent_select = "d.bowling_team AS opponent"

            if team_label is not None:
                team_select = f"'{team_label}' AS team_group"

            if opponent_label is not None:
                opponent_select = f"'{opponent_label}' AS opponent_group"

            return f"""
SELECT TOP {top_n}
    {team_select},
    {opponent_select},
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS team_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
{where_sql}
  AND d.innings IN (1, 2)
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY team_score DESC;
""".strip()
    # List all hundreds ever or in a season
    if (
        ("list" in question_lower or "show" in question_lower)
        and ("hundreds" in question_lower or "centuries" in question_lower)
    ):
        season = get_season_from_question(user_question)

        season_filter = ""

        if season is not None:
            season_filter = f"WHERE d.season = '{season}'"

        return f"""
SELECT
    batter,
    batting_team,
    opponent,
    season,
    start_date,
    venue,
    runs_in_innings
FROM (
    SELECT
        d.match_id,
        d.innings,
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
    {season_filter}
    GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
) AS batter_innings
WHERE runs_in_innings >= 100
ORDER BY season, start_date, runs_in_innings DESC;
""".strip()
    # Highest individual scores for a team/opponent, optionally at a venue
    if (
        ("highest individual score" in question_lower
         or "highest individual scores" in question_lower
         or "highest score by a player" in question_lower
         or "highest scores by players" in question_lower
         or (
             "highest score" in question_lower
             and "against" in question_lower
             and ("who" in question_lower or "individual" in question_lower or "player" in question_lower)
         )
         or (
             "highest scores" in question_lower
             and "individual" in question_lower
         ))
    ):
        top_n = get_top_n_from_question(user_question, 10)

        team_condition = None
        team_label = None

        opponent_condition = None
        opponent_label = None

        if "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
            team_label = get_team_label_after_keyword(user_question, "for")

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
            opponent_label = get_team_label_after_keyword(user_question, "against")

        where_clauses = []

        if team_condition is not None:
            where_clauses.append(team_condition)

        if opponent_condition is not None:
            where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        if len(where_clauses) > 0:
            where_sql = "WHERE " + " AND ".join(where_clauses)

            team_select = "d.batting_team AS batting_team"
            opponent_select = "d.bowling_team AS opponent"

            if team_label is not None:
                team_select = f"'{team_label}' AS team_group"

            if opponent_label is not None:
                opponent_select = f"'{opponent_label}' AS opponent_group"

            return f"""
SELECT TOP {top_n}
    d.striker AS batter,
    {team_select},
    {opponent_select},
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
{where_sql}
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY runs_in_innings DESC;
""".strip()

    # List all fifties in a specific season only
    if (
        ("list" in question_lower or "show" in question_lower)
        and ("fifties" in question_lower or "50s" in question_lower)
    ):
        season = get_season_from_question(user_question)

        if season is not None:
            return f"""
SELECT
    batter,
    batting_team,
    opponent,
    season,
    start_date,
    venue,
    runs_in_innings
FROM (
    SELECT
        d.match_id,
        d.innings,
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
    WHERE d.season = '{season}'
    GROUP BY d.match_id, d.innings, d.striker, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
) AS batter_innings
WHERE runs_in_innings BETWEEN 50 AND 99
ORDER BY start_date, runs_in_innings DESC;
""".strip()

        return """
SELECT
    'Listing all fifties ever would return too many rows. Please specify a season, for example: list all fifties in 2014 season.' AS message;
""".strip()
    # List all fifers ever or in a season
    if (
        ("list" in question_lower or "show" in question_lower)
        and ("fifers" in question_lower or "five wicket hauls" in question_lower or "five-wicket hauls" in question_lower or "5 wicket hauls" in question_lower)
    ):
        season = get_season_from_question(user_question)

        if season is not None:
            return f"""
WITH fifers AS (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        d.bowling_team,
        d.batting_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE d.season = '{season}'
    GROUP BY d.match_id, d.innings, d.bowler, d.bowling_team, d.batting_team, m.season, m.start_date, m.venue
),
final_results AS (
    SELECT
        CAST(NULL AS VARCHAR(200)) AS message,
        bowler,
        bowling_team,
        opponent,
        season,
        start_date,
        venue,
        wickets,
        runs_conceded,
        legal_balls,
        ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy_rate
    FROM fifers
    WHERE wickets >= 5

    UNION ALL

    SELECT
        'No fifer was taken in this season.' AS message,
        NULL AS bowler,
        NULL AS bowling_team,
        NULL AS opponent,
        '{season}' AS season,
        NULL AS start_date,
        NULL AS venue,
        NULL AS wickets,
        NULL AS runs_conceded,
        NULL AS legal_balls,
        NULL AS economy_rate
    WHERE NOT EXISTS (
        SELECT 1
        FROM fifers
        WHERE wickets >= 5
    )
)
SELECT *
FROM final_results
ORDER BY
    CASE WHEN wickets IS NULL THEN 1 ELSE 0 END,
    start_date,
    wickets DESC,
    economy_rate ASC;
""".strip()

        return """
SELECT
    bowler,
    bowling_team,
    opponent,
    season,
    start_date,
    venue,
    wickets,
    runs_conceded,
    legal_balls,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy_rate
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        d.bowling_team,
        d.batting_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    GROUP BY d.match_id, d.innings, d.bowler, d.bowling_team, d.batting_team, m.season, m.start_date, m.venue
) AS bowling_figures
WHERE wickets >= 5
ORDER BY season, start_date, wickets DESC, economy_rate ASC;
""".strip()
        
    # Most hundreds/fifties against a team, optionally at a venue
    if (
        ("hundreds" in question_lower or "centuries" in question_lower or "fifties" in question_lower)
        and "against" in question_lower
        and "for" not in question_lower
        and ("most" in question_lower or "who" in question_lower)
    ):
        opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
        opponent_label = get_team_label_after_keyword(user_question, "against")

        if opponent_condition is not None:
            milestone_name = "hundreds"
            milestone_filter = "runs_in_innings >= 100"

            if "fifties" in question_lower:
                milestone_name = "fifties"
                milestone_filter = "runs_in_innings BETWEEN 50 AND 99"

            extra_filters = ""

            if venue_context:
                extra_filters = f"AND {venue_condition}"

            return f"""
SELECT TOP 10
    batter,
    '{opponent_label}' AS opponent_group,
    COUNT(*) AS {milestone_name}
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {opponent_condition}
      {extra_filters}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE {milestone_filter}
GROUP BY batter
ORDER BY {milestone_name} DESC;
""".strip()
    # Fastest fifty/hundred for team, against team, at venue, or combined filters
    if (
        "fastest fifty" in question_lower
        or "fastest 50" in question_lower
        or "fastest hundred" in question_lower
        or "fastest 100" in question_lower
        or "fastest century" in question_lower
    ):
        has_filter = (
            "for" in question_lower
            or "against" in question_lower
            or venue_context
        )

        if has_filter:
            if "fastest fifty" in question_lower or "fastest 50" in question_lower:
                return build_fastest_milestone_sql_with_filters(50, "fifty", user_question)

            if "fastest hundred" in question_lower or "fastest 100" in question_lower or "fastest century" in question_lower:
                return build_fastest_milestone_sql_with_filters(100, "hundred", user_question)
    # Highest individual score for a team, optionally against another team and/or at a venue
    if (
        ("highest individual score" in question_lower or "best individual score" in question_lower)
        and "for" in question_lower
    ):
        team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
        team_label = get_team_label_after_keyword(user_question, "for")

        opponent_condition = None
        opponent_label = None

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
            opponent_label = get_team_label_after_keyword(user_question, "against")

        if team_condition is not None:
            extra_filters = ""

            if opponent_condition is not None:
                extra_filters += f"\n  AND {opponent_condition}"

            if venue_context:
                extra_filters += f"\n  AND {venue_condition}"

            opponent_select = "d.bowling_team AS opponent"

            if opponent_label is not None:
                opponent_select = f"'{opponent_label}' AS opponent_group"

            return f"""
SELECT TOP 10
    d.striker AS batter,
    '{team_label}' AS team_group,
    {opponent_select},
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {team_condition}
  AND d.innings IN (1, 2)
  {extra_filters}
GROUP BY d.match_id, d.innings, d.striker, m.season, m.start_date, m.venue
ORDER BY runs_in_innings DESC;
""".strip()

    # Best team score/total for a team, optionally against another team and/or at a venue
    if (
        ("best score" in question_lower or "highest score" in question_lower or "best total" in question_lower or "highest total" in question_lower)
        and "for" in question_lower
        and "individual" not in question_lower
    ):
        team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
        team_label = get_team_label_after_keyword(user_question, "for")

        opponent_condition = None
        opponent_label = None

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
            opponent_label = get_team_label_after_keyword(user_question, "against")

        if team_condition is not None:
            extra_filters = ""

            if opponent_condition is not None:
                extra_filters += f"\n  AND {opponent_condition}"

            if venue_context:
                extra_filters += f"\n  AND {venue_condition}"

            opponent_select = "d.bowling_team AS opponent"

            if opponent_label is not None:
                opponent_select = f"'{opponent_label}' AS opponent_group"

            return f"""
SELECT TOP 10
    '{team_label}' AS team_group,
    {opponent_select},
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS team_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {team_condition}
  AND d.innings IN (1, 2)
  {extra_filters}
GROUP BY d.match_id, d.innings, m.season, m.start_date, m.venue
ORDER BY team_score DESC;
""".strip()

    # Best bowling figures for a team, optionally against another team and/or at a venue
    if "best bowling figures" in question_lower or "best figures" in question_lower:
        where_clauses = []

        bowling_team_condition = None
        batting_team_condition = None

        if "for" in question_lower:
            bowling_team_condition = get_team_condition_after_keyword(user_question, "for", "d.bowling_team")

        if "against" in question_lower:
            batting_team_condition = get_team_condition_after_keyword(user_question, "against", "d.batting_team")

        if bowling_team_condition is not None:
            where_clauses.append(bowling_team_condition)

        if batting_team_condition is not None:
            where_clauses.append(batting_team_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        where_sql = ""

        if len(where_clauses) > 0:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        return f"""
SELECT TOP 10
    bowler,
    bowling_team,
    batting_team AS opponent,
    season,
    start_date,
    venue,
    wickets,
    runs_conceded,
    legal_balls,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy_rate
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        d.bowling_team,
        d.batting_team,
        m.season,
        m.start_date,
        m.venue,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    {where_sql}
    GROUP BY d.match_id, d.innings, d.bowler, d.bowling_team, d.batting_team, m.season, m.start_date, m.venue
) AS bowling_figures
WHERE wickets > 0
ORDER BY wickets DESC, economy_rate ASC, runs_conceded ASC;
""".strip()

    # Most hundreds/fifties for a team, optionally against another team and/or at a venue
    if (
        ("hundreds" in question_lower or "centuries" in question_lower or "fifties" in question_lower)
        and "for" in question_lower
    ):
        team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
        team_label = get_team_label_after_keyword(user_question, "for")

        opponent_condition = None

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")

        if team_condition is not None:
            milestone_name = "hundreds"
            milestone_filter = "runs_in_innings >= 100"

            if "fifties" in question_lower:
                milestone_name = "fifties"
                milestone_filter = "runs_in_innings BETWEEN 50 AND 99"

            extra_filters = ""

            if opponent_condition is not None:
                extra_filters += f"\n      AND {opponent_condition}"

            if venue_context:
                extra_filters += f"\n      AND {venue_condition}"

            return f"""
SELECT TOP 10
    batter,
    '{team_label}' AS team_group,
    COUNT(*) AS {milestone_name}
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {team_condition}
      {extra_filters}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE {milestone_filter}
GROUP BY batter
ORDER BY {milestone_name} DESC;
""".strip()

    # Most runs for a team or franchise
    if "most runs" in question_lower and "for" in question_lower:
        team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")
        team_label = get_team_label_after_keyword(user_question, "for")

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    '{team_label}' AS team_group,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE {team_condition}
GROUP BY d.striker
ORDER BY total_runs DESC;
""".strip()

    # 2. Team win percentage
    if "win percentage" in question_lower or "win percent" in question_lower or "winning percentage" in question_lower:
        batting_team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        bowling_team_condition = get_team_condition_from_question(user_question, "d.bowling_team")
        winner_condition = get_team_condition_from_question(user_question, "m.winner")

        if batting_team_condition is not None and bowling_team_condition is not None and winner_condition is not None:
            return f"""
WITH team_matches AS (
    SELECT DISTINCT
        d.match_id
    FROM deliveries d
    WHERE {batting_team_condition}
       OR {bowling_team_condition}
),
team_wins AS (
    SELECT
        COUNT(*) AS wins
    FROM matches m
    JOIN team_matches tm
        ON m.match_id = tm.match_id
    WHERE {winner_condition}
),
team_total_matches AS (
    SELECT
        COUNT(*) AS matches_played
    FROM team_matches
)
SELECT
    team_wins.wins,
    team_total_matches.matches_played,
    ROUND(
        CAST(team_wins.wins AS FLOAT) * 100.0 /
        NULLIF(team_total_matches.matches_played, 0),
        2
    ) AS win_percentage
FROM team_wins
CROSS JOIN team_total_matches;
""".strip()

    # 3. Best bowling figures overall, for a team, or at a venue
    if "best bowling figures" in question_lower or "best figures" in question_lower:
        where_clauses = []

        team_condition = get_team_condition_from_question(user_question, "d.bowling_team")

        if "for" in question_lower and team_condition is not None:
            where_clauses.append(team_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        where_sql = ""

        if len(where_clauses) > 0:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        return f"""
SELECT TOP 10
    bowler,
    bowling_team,
    batting_team AS opponent,
    season,
    start_date,
    venue,
    wickets,
    runs_conceded,
    legal_balls,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy_rate
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        d.bowling_team,
        d.batting_team,
        m.season,
        m.start_date,
        m.venue,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    {where_sql}
    GROUP BY d.match_id, d.innings, d.bowler, d.bowling_team, d.batting_team, m.season, m.start_date, m.venue
) AS bowling_figures
WHERE wickets > 0
ORDER BY wickets DESC, economy_rate ASC, runs_conceded ASC;
""".strip()

    # 4. Highest individual score for a team, optionally at a venue
    if (
        "highest score" in question_lower
        and "for" in question_lower
        and (
            "individual" in question_lower
            or "which player" in question_lower
            or "who has" in question_lower
            or "player" in question_lower
        )
    ):
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            venue_filter = ""

            if venue_context:
                venue_filter = f"AND {venue_condition}"

            return f"""
SELECT TOP 10
    d.striker AS batter,
    '{team_label}' AS team_group,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {team_condition}
  AND d.innings IN (1, 2)
  {venue_filter}
GROUP BY d.match_id, d.innings, d.striker, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY runs_in_innings DESC;
""".strip()

    # 5. Team highest score overall or at a venue
    if (
        "highest score" in question_lower
        or "highest total" in question_lower
        or "best score" in question_lower
        or "best total" in question_lower
    ) and not has_player_reference(user_question):
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            venue_filter = ""

            if venue_context:
                venue_filter = f"AND {venue_condition}"

            return f"""
SELECT TOP 10
    '{team_label}' AS team_group,
    d.batting_team,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS team_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {team_condition}
  AND d.innings IN (1, 2)
  {venue_filter}
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY team_score DESC;
""".strip()
    # Lowest total successfully defended, optionally by team/opponent/venue
    if (
        "lowest total successfully defended" in question_lower
        or "lowest score successfully defended" in question_lower
        or "lowest ever total successfully defended" in question_lower
        or "lowest defended total" in question_lower
        or ("lowest total" in question_lower and "defended" in question_lower)
        or ("lowest score" in question_lower and "defended" in question_lower)
    ):
        where_clauses = [
            "d.innings = 1",
            "d.batting_team = m.winner"
        ]

        team_condition = None

        if "by" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "by", "d.batting_team")

        if team_condition is None and "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")

        if team_condition is not None:
            where_clauses.append(team_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        where_sql = " AND ".join(where_clauses)

        return f"""
SELECT TOP 10
    d.batting_team AS defending_team,
    d.bowling_team AS chasing_team,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS defended_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {where_sql}
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY defended_score ASC;
""".strip()

    # 6. Team lowest score overall or at a venue
    if ("lowest score" in question_lower or "lowest total" in question_lower) and not has_player_reference(user_question):
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            venue_filter = ""

            if venue_context:
                venue_filter = f"AND {venue_condition}"

            return f"""
SELECT TOP 10
    '{team_label}' AS team_group,
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
WHERE {team_condition}
  AND d.innings IN (1, 2)
  {venue_filter}
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY team_score ASC;
""".strip()

    # 7. Most hundreds/fifties for a team at a venue
    if (
        venue_context
        and ("hundreds" in question_lower or "centuries" in question_lower or "fifties" in question_lower)
        and "for" in question_lower
    ):
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            milestone_name = "hundreds"
            milestone_filter = "runs_in_innings >= 100"

            if "fifties" in question_lower:
                milestone_name = "fifties"
                milestone_filter = "runs_in_innings BETWEEN 50 AND 99"

            return f"""
SELECT TOP 10
    batter,
    '{team_label}' AS team_group,
    COUNT(*) AS {milestone_name}
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {team_condition}
      AND {venue_condition}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE {milestone_filter}
GROUP BY batter
ORDER BY {milestone_name} DESC;
""".strip()

    # 8. Most hundreds/fifties at a venue
    if venue_context and ("hundreds" in question_lower or "centuries" in question_lower or "fifties" in question_lower):
        milestone_name = "hundreds"
        milestone_filter = "runs_in_innings >= 100"

        if "fifties" in question_lower:
            milestone_name = "fifties"
            milestone_filter = "runs_in_innings BETWEEN 50 AND 99"

        return f"""
SELECT TOP 10
    batter,
    COUNT(*) AS {milestone_name}
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {venue_condition}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE {milestone_filter}
GROUP BY batter
ORDER BY {milestone_name} DESC;
""".strip()

    # 9. Most hundreds/fifties for a team
    if ("hundreds" in question_lower or "centuries" in question_lower or "fifties" in question_lower) and "for" in question_lower:
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            milestone_name = "hundreds"
            milestone_filter = "runs_in_innings >= 100"

            if "fifties" in question_lower:
                milestone_name = "fifties"
                milestone_filter = "runs_in_innings BETWEEN 50 AND 99"

            return f"""
SELECT TOP 10
    batter,
    '{team_label}' AS team_group,
    COUNT(*) AS {milestone_name}
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    WHERE {team_condition}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE {milestone_filter}
GROUP BY batter
ORDER BY {milestone_name} DESC;
""".strip()

    # 10. Most hundreds/fifties in a specific season
    if ("hundreds" in question_lower or "centuries" in question_lower or "fifties" in question_lower) and "season" in question_lower:
        season = get_season_from_question(user_question)

        if season is not None:
            milestone_name = "hundreds"
            milestone_filter = "runs_in_innings >= 100"

            if "fifties" in question_lower:
                milestone_name = "fifties"
                milestone_filter = "runs_in_innings BETWEEN 50 AND 99"

            return f"""
SELECT TOP 10
    season,
    batter,
    COUNT(*) AS {milestone_name}
FROM (
    SELECT
        season,
        match_id,
        innings,
        striker AS batter,
        SUM(runs_off_bat) AS runs_in_innings
    FROM deliveries
    WHERE season = '{season}'
    GROUP BY season, match_id, innings, striker
) AS batter_innings
WHERE {milestone_filter}
GROUP BY season, batter
ORDER BY {milestone_name} DESC;
""".strip()

    # 11. Purple Cap winner in a specific season or all seasons
    if "purple cap" in question_lower:
        season = get_season_from_question(user_question)

        if season is not None:
            return f"""
SELECT TOP 1
    season,
    bowler,
    COUNT(*) AS wickets
FROM deliveries
WHERE season = '{season}'
  AND wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY season, bowler
ORDER BY wickets DESC;
""".strip()

        return """
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
""".strip()

    # 12. Orange Cap winner in a specific season
    if "orange cap" in question_lower:
        season = get_season_from_question(user_question)

        if season is not None:
            return f"""
SELECT TOP 1
    season,
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
WHERE season = '{season}'
GROUP BY season, striker
ORDER BY total_runs DESC;
""".strip()

    # 13. Venue-specific player/team boundaries
    if venue_context and boundary_runs is not None:
        player_condition = get_player_condition_from_question(user_question, "d.striker")
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")

        if player_condition is not None:
            return f"""
SELECT
    d.striker AS batter,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {player_condition}
  AND {venue_condition}
  AND d.runs_off_bat = {boundary_runs}
GROUP BY d.striker;
""".strip()

        if team_condition is not None and ("how many" in question_lower or "total" in question_lower):
            return f"""
SELECT
    d.batting_team AS team,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {team_condition}
  AND {venue_condition}
  AND d.runs_off_bat = {boundary_runs}
GROUP BY d.batting_team;
""".strip()

        if "most" in question_lower or "who" in question_lower:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {venue_condition}
  AND d.runs_off_bat = {boundary_runs}
GROUP BY d.striker
ORDER BY total_{boundary_name} DESC;
""".strip()

    # 14. Venue-specific player/team runs
    if venue_context and "runs" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")

        if player_condition is not None:
            return f"""
SELECT
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {player_condition}
  AND {venue_condition}
GROUP BY d.striker;
""".strip()

        if team_condition is not None and ("how many" in question_lower or "total" in question_lower):
            return f"""
SELECT
    d.batting_team AS team,
    SUM(d.runs_off_bat + d.extras) AS total_runs
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {team_condition}
  AND {venue_condition}
GROUP BY d.batting_team;
""".strip()

        if "most" in question_lower or "who" in question_lower:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {venue_condition}
GROUP BY d.striker
ORDER BY total_runs DESC;
""".strip()

    # 15. Venue-specific player/team wickets
    if venue_context and ("wickets" in question_lower or "wicket" in question_lower):
        player_condition = get_player_condition_from_question(user_question, "d.bowler")
        team_condition = get_team_condition_from_question(user_question, "d.bowling_team")

        if player_condition is not None:
            return f"""
SELECT
    d.bowler,
    COUNT(*) AS wickets
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {player_condition}
  AND {venue_condition}
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowler;
""".strip()

        if team_condition is not None and ("how many" in question_lower or "total" in question_lower):
            return f"""
SELECT
    d.bowling_team AS team,
    COUNT(*) AS wickets
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {team_condition}
  AND {venue_condition}
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowling_team;
""".strip()

        if "most" in question_lower or "who" in question_lower:
            return f"""
SELECT TOP 10
    d.bowler,
    COUNT(*) AS wickets
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {venue_condition}
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowler
ORDER BY wickets DESC;
""".strip()

    # 16. Player/team fours and sixes support
    if boundary_runs is not None:
        is_specific_boundary_record = (
            "single innings" in question_lower
            or "single season" in question_lower
            or "single match" in question_lower
            or "in a match" in question_lower
        )

        if not is_specific_boundary_record:
            if "against" in question_lower:
                player_condition = get_player_condition_from_question(user_question, "d.striker")
                team_condition = get_team_condition_from_question(user_question, "d.bowling_team")
                team_label = get_team_label_from_question(user_question)

                if player_condition is not None and team_condition is not None:
                    return f"""
SELECT
    d.striker AS batter,
    '{team_label}' AS opponent_group,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
WHERE {player_condition}
  AND {team_condition}
  AND d.runs_off_bat = {boundary_runs}
GROUP BY d.striker;
""".strip()

                if team_condition is not None:
                    return f"""
SELECT TOP 10
    d.striker AS batter,
    '{team_label}' AS opponent_group,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
WHERE {team_condition}
  AND d.runs_off_bat = {boundary_runs}
GROUP BY d.striker
ORDER BY total_{boundary_name} DESC;
""".strip()

            if "for" in question_lower:
                player_condition = get_player_condition_from_question(user_question, "d.striker")
                team_condition = get_team_condition_from_question(user_question, "d.batting_team")
                team_label = get_team_label_from_question(user_question)

                if player_condition is not None and team_condition is not None:
                    return f"""
SELECT
    d.striker AS batter,
    '{team_label}' AS team_group,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
WHERE {player_condition}
  AND {team_condition}
  AND d.runs_off_bat = {boundary_runs}
GROUP BY d.striker;
""".strip()

                if team_condition is not None and ("most" in question_lower or "who" in question_lower):
                    return f"""
SELECT TOP 10
    d.striker AS batter,
    '{team_label}' AS team_group,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
WHERE {team_condition}
  AND d.runs_off_bat = {boundary_runs}
GROUP BY d.striker
ORDER BY total_{boundary_name} DESC;
""".strip()

            team_condition = get_team_condition_from_question(user_question, "d.batting_team")
            player_condition = get_player_condition_from_question(user_question, "d.striker")
            team_label = get_team_label_from_question(user_question)

            if player_condition is None and team_condition is not None and ("how many" in question_lower or "total" in question_lower):
                return f"""
SELECT
    '{team_label}' AS team_group,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
WHERE {team_condition}
  AND d.runs_off_bat = {boundary_runs};
""".strip()

            if player_condition is not None:
                return f"""
SELECT
    d.striker AS batter,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
WHERE {player_condition}
  AND d.runs_off_bat = {boundary_runs}
GROUP BY d.striker;
""".strip()

            if "most" in question_lower or "who" in question_lower:
                return f"""
SELECT TOP 10
    d.striker AS batter,
    COUNT(*) AS total_{boundary_name}
FROM deliveries d
WHERE d.runs_off_bat = {boundary_runs}
GROUP BY d.striker
ORDER BY total_{boundary_name} DESC;
""".strip()

    # 17. Best strike rate for a team with custom minimum balls
    if "best strike rate" in question_lower and "for" in question_lower:
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        minimum_balls = get_minimum_balls_from_question(user_question, 300)

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    d.batting_team,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
WHERE {team_condition}
GROUP BY d.striker, d.batting_team
HAVING SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) >= {minimum_balls}
ORDER BY strike_rate DESC;
""".strip()

    # 18. Best batting average for a team with custom minimum runs
    if ("best average" in question_lower or "best batting average" in question_lower) and "for" in question_lower:
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        minimum_runs = get_minimum_runs_from_question(user_question, 500)

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    d.batting_team,
    SUM(d.runs_off_bat) AS total_runs,
    COUNT(CASE
        WHEN d.player_dismissed = d.striker
             AND d.wicket_type NOT IN ('retired hurt', 'retired out')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(d.runs_off_bat) * 1.0 /
        NULLIF(
            COUNT(CASE
                WHEN d.player_dismissed = d.striker
                     AND d.wicket_type NOT IN ('retired hurt', 'retired out')
                THEN 1
            END),
            0
        ),
        2
    ) AS batting_average
FROM deliveries d
WHERE {team_condition}
GROUP BY d.striker, d.batting_team
HAVING SUM(d.runs_off_bat) >= {minimum_runs}
   AND COUNT(CASE
        WHEN d.player_dismissed = d.striker
             AND d.wicket_type NOT IN ('retired hurt', 'retired out')
        THEN 1
    END) > 0
ORDER BY batting_average DESC;
""".strip()

    # 19. Most runs for a team or franchise
    if "most runs" in question_lower and "for" in question_lower:
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    '{team_label}' AS team_group,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE {team_condition}
GROUP BY d.striker
ORDER BY total_runs DESC;
""".strip()

    # 20. Player/team runs against a team or franchise
    if "runs" in question_lower and "against" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")
        team_condition = get_team_condition_from_question(user_question, "d.bowling_team")
        team_label = get_team_label_from_question(user_question)

        if player_condition is not None and team_condition is not None:
            return f"""
SELECT
    d.striker AS batter,
    '{team_label}' AS opponent_group,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE {player_condition}
  AND {team_condition}
GROUP BY d.striker;
""".strip()

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    '{team_label}' AS opponent_group,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE {team_condition}
GROUP BY d.striker
ORDER BY total_runs DESC;
""".strip()

    # 21. Player-specific runs for a team
    if "runs" in question_lower and "for" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if player_condition is not None and team_condition is not None:
            return f"""
SELECT
    d.striker AS batter,
    '{team_label}' AS team_group,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE {player_condition}
  AND {team_condition}
GROUP BY d.striker;
""".strip()

    # 22. Player total career runs
    if "runs" in question_lower and "against" not in question_lower and "for" not in question_lower and "single season" not in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")

        if player_condition is not None:
            return f"""
SELECT
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
WHERE {player_condition}
GROUP BY d.striker;
""".strip()

    # 23. Player wickets against a team
    if "wickets" in question_lower and "against" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.bowler")
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if player_condition is not None and team_condition is not None:
            return f"""
SELECT
    d.bowler,
    '{team_label}' AS opponent_group,
    COUNT(*) AS wickets
FROM deliveries d
WHERE {player_condition}
  AND {team_condition}
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowler;
""".strip()

    # 24. Player-specific wickets for a team
    if "wickets" in question_lower and "for" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.bowler")
        team_condition = get_team_condition_from_question(user_question, "d.bowling_team")
        team_label = get_team_label_from_question(user_question)

        if player_condition is not None and team_condition is not None:
            return f"""
SELECT
    d.bowler,
    '{team_label}' AS team_group,
    COUNT(*) AS wickets
FROM deliveries d
WHERE {player_condition}
  AND {team_condition}
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowler;
""".strip()

    # 25. Player total career wickets
    if "wickets" in question_lower and "for" not in question_lower and "against" not in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.bowler")

        if player_condition is not None:
            return f"""
SELECT
    d.bowler,
    COUNT(*) AS wickets
FROM deliveries d
WHERE {player_condition}
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.bowler;
""".strip()

    # 26. Player-specific fifties against a team
    if "fifties" in question_lower and "against" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")
        team_condition = get_team_condition_from_question(user_question, "d.bowling_team")
        team_label = get_team_label_from_question(user_question)

        if player_condition is not None and team_condition is not None:
            return f"""
SELECT
    batter,
    '{team_label}' AS opponent_group,
    COUNT(*) AS fifties
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    WHERE {player_condition}
      AND {team_condition}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE runs_in_innings BETWEEN 50 AND 99
GROUP BY batter;
""".strip()

    # 27. Player-specific hundreds against a team
    if ("hundreds" in question_lower or "centuries" in question_lower) and "against" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")
        team_condition = get_team_condition_from_question(user_question, "d.bowling_team")
        team_label = get_team_label_from_question(user_question)

        if player_condition is not None and team_condition is not None:
            return f"""
SELECT
    batter,
    '{team_label}' AS opponent_group,
    COUNT(*) AS hundreds
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    WHERE {player_condition}
      AND {team_condition}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE runs_in_innings >= 100
GROUP BY batter;
""".strip()

    # 28. Player strike rate in death overs
    if "strike rate" in question_lower and "death" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")

        if player_condition is not None:
            return f"""
SELECT
    d.striker AS batter,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS death_overs_strike_rate
FROM deliveries d
WHERE {player_condition}
  AND FLOOR(d.ball) BETWEEN 15 AND 19
GROUP BY d.striker;
""".strip()

    # 29. Player-specific highest score against a team
    if "highest score" in question_lower and "against" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")
        team_condition = get_team_condition_from_question(user_question, "d.bowling_team")
        team_label = get_team_label_from_question(user_question)

        if player_condition is not None and team_condition is not None:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    d.batting_team,
    '{team_label}' AS opponent_group,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {player_condition}
  AND {team_condition}
GROUP BY d.match_id, d.innings, d.striker, d.batting_team, m.season, m.start_date, m.venue
ORDER BY runs_in_innings DESC;
""".strip()

    # 30. Player-specific hundreds
    if "hundreds" in question_lower or "centuries" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")

        if player_condition is not None:
            return f"""
SELECT
    batter,
    COUNT(*) AS hundreds
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    WHERE {player_condition}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE runs_in_innings >= 100
GROUP BY batter;
""".strip()

    # 31. Player-specific fifties
    if "fifties" in question_lower or "50s" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")

        if player_condition is not None:
            return f"""
SELECT
    batter,
    COUNT(*) AS fifties
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings
    FROM deliveries d
    WHERE {player_condition}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE runs_in_innings BETWEEN 50 AND 99
GROUP BY batter;
""".strip()

    # 32. Team-specific ducks
    if ("ducks" in question_lower or "duck" in question_lower) and "for" in question_lower:
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            return f"""
SELECT TOP 10
    batter,
    '{team_label}' AS team_group,
    COUNT(*) AS ducks
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings,
        MAX(CASE
                WHEN d.player_dismissed = d.striker
                     AND d.wicket_type NOT IN ('retired hurt', 'retired out')
                THEN 1
                ELSE 0
            END) AS was_dismissed
    FROM deliveries d
    WHERE {team_condition}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE runs_in_innings = 0
  AND was_dismissed = 1
GROUP BY batter
ORDER BY ducks DESC;
""".strip()

    # 33. Player-specific or overall ducks
    if "ducks" in question_lower or "duck" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")

        if player_condition is not None:
            return f"""
SELECT
    batter,
    COUNT(*) AS ducks
FROM (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_in_innings,
        MAX(CASE
                WHEN d.player_dismissed = d.striker
                     AND d.wicket_type NOT IN ('retired hurt', 'retired out')
                THEN 1
                ELSE 0
            END) AS was_dismissed
    FROM deliveries d
    WHERE {player_condition}
    GROUP BY d.match_id, d.innings, d.striker
) AS batter_innings
WHERE runs_in_innings = 0
  AND was_dismissed = 1
GROUP BY batter;
""".strip()

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

    # 34. Player-specific strike rate
    if "strike rate" in question_lower:
        player_condition = get_player_condition_from_question(user_question, "d.striker")

        if player_condition is not None:
            return f"""
SELECT
    d.striker AS batter,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
WHERE {player_condition}
GROUP BY d.striker;
""".strip()

    # 35. Most fifties overall
    if "most fifties" in question_lower:
        return """
SELECT TOP 10
    batter,
    COUNT(*) AS fifties
FROM (
    SELECT
        match_id,
        innings,
        striker AS batter,
        SUM(runs_off_bat) AS runs_in_innings
    FROM deliveries
    GROUP BY match_id, innings, striker
) AS batter_innings
WHERE runs_in_innings BETWEEN 50 AND 99
GROUP BY batter
ORDER BY fifties DESC;
""".strip()

    # 36. Best batting average overall with minimum 500 runs
    if "best average" in question_lower or "best batting average" in question_lower:
        minimum_runs = get_minimum_runs_from_question(user_question, 500)

        return f"""
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS total_runs,
    COUNT(CASE
        WHEN player_dismissed = striker
             AND wicket_type NOT IN ('retired hurt', 'retired out')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(runs_off_bat) * 1.0 /
        NULLIF(
            COUNT(CASE
                WHEN player_dismissed = striker
                     AND wicket_type NOT IN ('retired hurt', 'retired out')
                THEN 1
            END),
            0
        ),
        2
    ) AS batting_average
FROM deliveries
GROUP BY striker
HAVING SUM(runs_off_bat) >= {minimum_runs}
   AND COUNT(CASE
        WHEN player_dismissed = striker
             AND wicket_type NOT IN ('retired hurt', 'retired out')
        THEN 1
    END) > 0
ORDER BY batting_average DESC;
""".strip()

    # 37. Most balls bowled ever
    if "most balls" in question_lower and ("bowled" in question_lower or "bowling" in question_lower):
        return """
SELECT TOP 10
    bowler,
    legal_balls_bowled,
    CAST(legal_balls_bowled / 6 AS VARCHAR(10)) + '.' + CAST(legal_balls_bowled % 6 AS VARCHAR(1)) AS overs_bowled
FROM (
    SELECT
        bowler,
        SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls_bowled
    FROM deliveries
    GROUP BY bowler
) AS bowler_balls
ORDER BY legal_balls_bowled DESC;
""".strip()

    # 38. Highest individual score for a team fallback
    if "highest score" in question_lower and (" for " in question_lower or " csk" in question_lower or " mi" in question_lower):
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            return f"""
SELECT TOP 10
    d.striker AS batter,
    '{team_label}' AS team_group,
    d.bowling_team AS opponent,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat) AS runs_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {team_condition}
GROUP BY d.match_id, d.innings, d.striker, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY runs_in_innings DESC;
""".strip()

    # 39. Highest team score overall
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

    # 40. Lowest team score overall
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

    # 41. Most expensive bowling spell
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

    # 42. Highest successful chases
    # Highest successful chase, optionally by team/opponent/venue
    if (
        "successful chase" in question_lower
        or "successful run chase" in question_lower
        or "highest chase" in question_lower
        or "highest ever successful run chase" in question_lower
        or "highest successful chase" in question_lower
        or "highest total chased" in question_lower
        or "highest total chased down" in question_lower
        or "highest ever total chased down" in question_lower
    ):
        where_clauses = [
            "d.innings = 2",
            "d.batting_team = m.winner"
        ]

        team_condition = None

        if "by" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "by", "d.batting_team")

        if team_condition is None and "for" in question_lower:
            team_condition = get_team_condition_after_keyword(user_question, "for", "d.batting_team")

        if team_condition is not None:
            where_clauses.append(team_condition)

        if "against" in question_lower:
            opponent_condition = get_team_condition_after_keyword(user_question, "against", "d.bowling_team")
            if opponent_condition is not None:
                where_clauses.append(opponent_condition)

        if venue_context:
            where_clauses.append(venue_condition)

        where_sql = " AND ".join(where_clauses)

        return f"""
SELECT TOP 10
    d.batting_team AS chasing_team,
    d.bowling_team AS defending_team,
    m.season,
    m.start_date,
    m.venue,
    SUM(d.runs_off_bat + d.extras) AS chase_score
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {where_sql}
GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.season, m.start_date, m.venue
ORDER BY chase_score DESC;
""".strip()   
    # 43. Most runs in a single season
    if "most runs" in question_lower and "single season" in question_lower:
        return """
SELECT TOP 10
    season,
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
GROUP BY season, striker
ORDER BY total_runs DESC;
""".strip()

    # 44. Most wickets in a single season
    if "most wickets" in question_lower and "single season" in question_lower:
        return """
SELECT TOP 10
    season,
    bowler,
    COUNT(*) AS wickets
FROM deliveries
WHERE wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY season, bowler
ORDER BY wickets DESC;
""".strip()

    # 45. Most sixes in a single season
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

    # 46. Most hundreds in a single season
    if "hundreds" in question_lower and "single season" in question_lower:
        return """
SELECT TOP 10
    season,
    batter,
    COUNT(*) AS hundreds
FROM (
    SELECT
        season,
        match_id,
        innings,
        striker AS batter,
        SUM(runs_off_bat) AS runs_in_innings
    FROM deliveries
    GROUP BY season, match_id, innings, striker
) AS batter_innings
WHERE runs_in_innings >= 100
GROUP BY season, batter
ORDER BY hundreds DESC;
""".strip()

    # 47. Most five-wicket hauls / fifers
    if "five wicket haul" in question_lower or "five-wicket haul" in question_lower or "fifer" in question_lower or "5 wicket haul" in question_lower:
        return """
SELECT TOP 10
    bowler,
    COUNT(*) AS five_wicket_hauls
FROM (
    SELECT
        match_id,
        innings,
        bowler,
        COUNT(*) AS wickets
    FROM deliveries
    WHERE wicket_type IS NOT NULL
      AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
    GROUP BY match_id, innings, bowler
) AS bowling_spells
WHERE wickets >= 5
GROUP BY bowler
ORDER BY five_wicket_hauls DESC;
""".strip()

    # 48. Highest aggregate runs in a match
    if "aggregate" in question_lower and "match" in question_lower:
        return """
WITH innings_scores AS (
    SELECT
        d.match_id,
        d.innings,
        d.batting_team,
        m.season,
        m.start_date,
        m.venue,
        SUM(d.runs_off_bat + d.extras) AS team_score
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE d.innings IN (1, 2)
    GROUP BY d.match_id, d.innings, d.batting_team, m.season, m.start_date, m.venue
)
SELECT TOP 10
    match_id,
    season,
    start_date,
    venue,
    MIN(batting_team) AS team_1,
    MAX(batting_team) AS team_2,
    SUM(team_score) AS match_aggregate_runs
FROM innings_scores
GROUP BY match_id, season, start_date, venue
ORDER BY match_aggregate_runs DESC;
""".strip()

    # 49. Most sixes in a single match
    if "sixes" in question_lower and ("single match" in question_lower or "in a match" in question_lower):
        return """
SELECT TOP 10
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
WHERE d.innings IN (1, 2)
GROUP BY d.match_id, m.season, m.start_date, m.venue
ORDER BY total_sixes DESC;
""".strip()

    # 50. Most fours in a single innings
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

    # 51. Most sixes in a single innings
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

    # 52. Fastest fifty
    if "fastest fifty" in question_lower or "fastest 50" in question_lower:
        return build_fastest_milestone_sql(50, "fifty")

    # 53. Fastest hundred
    if "fastest hundred" in question_lower or "fastest 100" in question_lower or "fastest century" in question_lower:
        return build_fastest_milestone_sql(100, "hundred")

    # 54. Largest victory by runs
    if ("largest victory" in question_lower or "biggest victory" in question_lower or "largest win" in question_lower or "biggest win" in question_lower) and "runs" in question_lower:
        return """
SELECT TOP 10
    winner,
    season,
    start_date,
    venue,
    winner_runs AS victory_margin_runs
FROM matches
WHERE winner_runs IS NOT NULL
  AND winner_runs > 0
ORDER BY winner_runs DESC;
""".strip()

    # 55. Smallest victory by runs
    if ("smallest victory" in question_lower or "narrowest victory" in question_lower or "smallest win" in question_lower or "narrowest win" in question_lower) and "runs" in question_lower:
        return """
SELECT TOP 10
    winner,
    season,
    start_date,
    venue,
    winner_runs AS victory_margin_runs
FROM matches
WHERE winner_runs IS NOT NULL
  AND winner_runs > 0
ORDER BY winner_runs ASC;
""".strip()

    # 56. Largest victory by wickets
    if ("largest victory" in question_lower or "biggest victory" in question_lower or "largest win" in question_lower or "biggest win" in question_lower) and "wickets" in question_lower:
        return """
SELECT TOP 10
    winner,
    season,
    start_date,
    venue,
    winner_wickets AS victory_margin_wickets
FROM matches
WHERE winner_wickets IS NOT NULL
  AND winner_wickets > 0
ORDER BY winner_wickets DESC;
""".strip()

    # 57. Smallest victory by wickets
    if ("smallest victory" in question_lower or "narrowest victory" in question_lower or "smallest win" in question_lower or "narrowest win" in question_lower) and "wickets" in question_lower:
        return """
SELECT TOP 10
    winner,
    season,
    start_date,
    venue,
    winner_wickets AS victory_margin_wickets
FROM matches
WHERE winner_wickets IS NOT NULL
  AND winner_wickets > 0
ORDER BY winner_wickets ASC;
""".strip()

    # 58. Largest victory by balls remaining
    if ("largest victory" in question_lower or "biggest victory" in question_lower or "largest win" in question_lower or "biggest win" in question_lower) and "balls" in question_lower:
        return """
WITH chase_balls AS (
    SELECT
        d.match_id,
        m.winner,
        m.season,
        m.start_date,
        m.venue,
        d.batting_team,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls_used
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE d.innings = 2
      AND d.batting_team = m.winner
    GROUP BY d.match_id, m.winner, m.season, m.start_date, m.venue, d.batting_team
)
SELECT TOP 10
    winner,
    season,
    start_date,
    venue,
    120 - legal_balls_used AS balls_remaining
FROM chase_balls
WHERE 120 - legal_balls_used >= 0
ORDER BY balls_remaining DESC;
""".strip()

    # 59. Smallest victory by balls remaining
    if ("smallest victory" in question_lower or "narrowest victory" in question_lower or "smallest win" in question_lower or "narrowest win" in question_lower) and "balls" in question_lower:
        return """
WITH chase_balls AS (
    SELECT
        d.match_id,
        m.winner,
        m.season,
        m.start_date,
        m.venue,
        d.batting_team,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls_used
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE d.innings = 2
      AND d.batting_team = m.winner
    GROUP BY d.match_id, m.winner, m.season, m.start_date, m.venue, d.batting_team
)
SELECT TOP 10
    winner,
    season,
    start_date,
    venue,
    120 - legal_balls_used AS balls_remaining
FROM chase_balls
WHERE 120 - legal_balls_used >= 0
ORDER BY balls_remaining ASC;
""".strip()

    # 60. Top 10 run scorers
    if "top 10 run scorers" in question_lower:
        return """
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
GROUP BY striker
ORDER BY total_runs DESC;
""".strip()

    # 61. Top 10 wicket takers
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

    # 62. Most runs in death overs
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

    # 63. Most runs in powerplay
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

    # 64. Most wickets in powerplay
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

    # 65. Most wickets in death overs
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

    # 66. Most wins while chasing
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

    # 67. Best economy rate
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

    # 68. Venues hosted most IPL matches
    if "venues hosted the most" in question_lower or "venue hosted the most" in question_lower:
        return """
SELECT TOP 10
    venue,
    COUNT(*) AS match_count
FROM matches
GROUP BY venue
ORDER BY match_count DESC;
""".strip()

    # 69. Matches in each season
    if "matches were played in each season" in question_lower:
        return """
SELECT
    season,
    COUNT(*) AS match_count
FROM matches
GROUP BY season
ORDER BY season;
""".strip()

    # 70. Teams with most wins
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

    # 71. Most runs conceded by bowlers
    if "bowlers have conceded the most runs" in question_lower or "bowler conceded the most runs" in question_lower:
        return """
SELECT TOP 10
    bowler,
    SUM(runs_off_bat + extras) AS total_runs_conceded
FROM deliveries
GROUP BY bowler
ORDER BY total_runs_conceded DESC;
""".strip()

    # 72. How many matches has a team won?
    if "how many matches" in question_lower and "won" in question_lower:
        team_condition = get_team_condition_from_question(user_question, "winner")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            return f"""
SELECT
    '{team_label}' AS team_group,
    COUNT(*) AS wins
FROM matches
WHERE {team_condition};
""".strip()

    return None
def get_player_condition_before_keyword(user_question, keyword, column_name):
    question_lower = user_question.lower()
    keyword_lower = keyword.lower()

    index = question_lower.find(keyword_lower)

    if index == -1:
        return None

    text_before = user_question[:index]
    return get_player_condition_from_question(text_before, column_name)


def get_player_condition_after_keyword(user_question, keyword, column_name):
    question_lower = user_question.lower()
    keyword_lower = keyword.lower()

    index = question_lower.find(keyword_lower)

    if index == -1:
        return None

    text_after = user_question[index + len(keyword):]
    return get_player_condition_from_question(text_after, column_name)

def build_analysis_response(user_question):
    question_lower = user_question.lower()
    # Final / specific final match summary
    if "final" in question_lower:
        season = get_season_from_question(user_question)

        if season is not None:
            match_filter_sql = f"""
ms.is_final = 1
AND ms.season_year = {season}
""".strip()

            analysis_result = analyze_match_summaries(
                match_filter_sql=match_filter_sql,
                context_label=f"{season} final",
                limit=1,
            )

            return {
                "method": "analysis_layer",
                "matched_question": "Final match summary",
                "sql_query": analysis_result["sql_query"],
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "match_summaries": analysis_result["match_summaries"],
                },
                "error": None
            }
    # Team bowler recommendation:
    # e.g. "Which GT bowler should bowl to Pooran?"
    # e.g. "Which MI bowler should bowl to Kohli in the death overs?"
    is_team_bowler_recommendation = (
        ("which" in question_lower or "who" in question_lower)
        and "bowler" in question_lower
        and ("bowl to" in question_lower or "to" in question_lower)
    )

    if is_team_bowler_recommendation:
        team_condition = get_team_condition_from_question(user_question, "se.bowling_team")
        batter_condition = get_player_condition_after_keyword(user_question, "to", "se.striker")

        if batter_condition is None:
            batter_condition = get_player_condition_from_question(user_question, "se.striker")

        if team_condition is not None and batter_condition is not None:
            phase_condition, phase_label = get_phase_condition_from_question(user_question, "se")

            if phase_condition is None:
                phase_label = "all overs"

            venue_condition = None

            if has_venue_context(user_question):
                venue_condition = get_venue_condition_from_question(user_question)

            analysis_result = analyze_team_bowler_recommendation(
                batter_condition=batter_condition,
                team_condition=team_condition,
                phase_condition=phase_condition,
                phase_label=phase_label.replace("_", " "),
                venue_condition=venue_condition,
            )

            combined_sql = analysis_result["sql_queries"]["direct_options"]
            combined_sql += "\n\n--- proxy_options ---\n" + analysis_result["sql_queries"]["proxy_options"]
            combined_sql += "\n\n--- recommended_lengths_lines ---\n" + analysis_result["sql_queries"]["recommended_lengths_lines"]

            return {
                "method": "analysis_layer",
                "matched_question": "Team bowler recommendation",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "direct_options": analysis_result["direct_options"],
                    "proxy_options": analysis_result["proxy_options"],
                    "recommended_lengths_lines": analysis_result["recommended_lengths_lines"],
                },
                "error": None,
            }

    # Batting plan against a bowler:
    # e.g. "How should Kohli play Rabada?"
    # e.g. "Where should Kohli target Rabada?"
    # e.g. "What shots should Kohli avoid against Rashid?"
    is_batter_plan_question = (
        ("how should" in question_lower and "play" in question_lower)
        or ("where should" in question_lower and "target" in question_lower)
        or ("what shots" in question_lower and "avoid" in question_lower)
        or ("which shots" in question_lower and "avoid" in question_lower)
    )

    if is_batter_plan_question:
        batter_condition = None
        bowler_condition = None

        if "play" in question_lower:
            batter_condition = get_player_condition_before_keyword(user_question, "play", "se.striker")
            bowler_condition = get_player_condition_after_keyword(user_question, "play", "se.bowler")

        elif "target" in question_lower:
            batter_condition = get_player_condition_before_keyword(user_question, "target", "se.striker")
            bowler_condition = get_player_condition_after_keyword(user_question, "target", "se.bowler")

        elif "avoid" in question_lower and "against" in question_lower:
            batter_condition = get_player_condition_before_keyword(user_question, "avoid", "se.striker")
            bowler_condition = get_player_condition_after_keyword(user_question, "against", "se.bowler")

        if batter_condition is not None and bowler_condition is not None:
            phase_condition, phase_label = get_phase_condition_from_question(user_question, "se")

            if phase_condition is None:
                phase_label = "all overs"

            venue_condition = None

            if has_venue_context(user_question):
                venue_condition = get_venue_condition_from_question(user_question)

            analysis_result = analyze_batter_plan_against_bowler(
                batter_condition=batter_condition,
                bowler_condition=bowler_condition,
                phase_condition=phase_condition,
                phase_label=phase_label.replace("_", " "),
                venue_condition=venue_condition,
            )

            combined_sql = analysis_result["sql_queries"]["direct_summary"]
            combined_sql += "\n\n--- scoring_areas ---\n" + analysis_result["sql_queries"]["scoring_areas"]
            combined_sql += "\n\n--- scoring_shots ---\n" + analysis_result["sql_queries"]["scoring_shots"]
            combined_sql += "\n\n--- risky_shots ---\n" + analysis_result["sql_queries"]["risky_shots"]
            combined_sql += "\n\n--- length_line_attack ---\n" + analysis_result["sql_queries"]["length_line_attack"]

            return {
                "method": "analysis_layer",
                "matched_question": "Batter plan against bowler",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "direct_summary": analysis_result["direct_summary"],
                    "scoring_areas": analysis_result["scoring_areas"],
                    "scoring_shots": analysis_result["scoring_shots"],
                    "risky_shots": analysis_result["risky_shots"],
                    "length_line_attack": analysis_result["length_line_attack"],
                },
                "error": None,
            }
    # Direct bowler-vs-batter tactical decision:
    # e.g. "Should Rashid Khan bowl to Pooran in the powerplay?"
    # e.g. "Should Kohli face Rabada?"
    is_direct_matchup_decision = (
        ("should" in question_lower and "bowl to" in question_lower)
        or ("should" in question_lower and "face" in question_lower)
    )

    if is_direct_matchup_decision:
        batter_condition = None
        bowler_condition = None

        if "bowl to" in question_lower:
            bowler_condition = get_player_condition_before_keyword(user_question, "bowl to", "se.bowler")
            batter_condition = get_player_condition_after_keyword(user_question, "bowl to", "se.striker")

        elif "face" in question_lower:
            batter_condition = get_player_condition_before_keyword(user_question, "face", "se.striker")
            bowler_condition = get_player_condition_after_keyword(user_question, "face", "se.bowler")

        if batter_condition is not None and bowler_condition is not None:
            phase_condition, phase_label = get_phase_condition_from_question(user_question, "se")

            if phase_condition is None:
                phase_label = "all overs"

            venue_condition = None

            if has_venue_context(user_question):
                venue_condition = get_venue_condition_from_question(user_question)

            analysis_result = analyze_bowler_vs_batter_decision(
                batter_condition=batter_condition,
                bowler_condition=bowler_condition,
                phase_condition=phase_condition,
                phase_label=phase_label.replace("_", " "),
                venue_condition=venue_condition,
            )

            combined_sql = analysis_result["sql_queries"]["direct_matchup"]
            combined_sql += "\n\n--- batter_benchmark ---\n" + analysis_result["sql_queries"]["batter_benchmark"]
            combined_sql += "\n\n--- phase_breakdown ---\n" + analysis_result["sql_queries"]["phase_breakdown"]
            combined_sql += "\n\n--- recommended_lengths_lines ---\n" + analysis_result["sql_queries"]["recommended_lengths_lines"]
            combined_sql += "\n\n--- shot_directions ---\n" + analysis_result["sql_queries"]["shot_directions"]
            combined_sql += "\n\n--- shot_types ---\n" + analysis_result["sql_queries"]["shot_types"]
            combined_sql += "\n\n--- similar_batter_matchup ---\n" + analysis_result["sql_queries"]["similar_batter_matchup"]
            combined_sql += "\n\n--- similar_batter_benchmark ---\n" + analysis_result["sql_queries"]["similar_batter_benchmark"]
            combined_sql += "\n\n--- similar_batter_lengths_lines ---\n" + analysis_result["sql_queries"]["similar_batter_lengths_lines"]
            combined_sql += "\n\n--- similar_batter_shot_directions ---\n" + analysis_result["sql_queries"]["similar_batter_shot_directions"]

            return {
                "method": "analysis_layer",
                "matched_question": "Bowler vs batter decision",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "direct_matchup": analysis_result["direct_matchup"],
                    "batter_benchmark": analysis_result["batter_benchmark"],
                    "phase_breakdown": analysis_result["phase_breakdown"],
                    "recommended_lengths_lines": analysis_result["recommended_lengths_lines"],
                    "shot_directions": analysis_result["shot_directions"],
                    "shot_types": analysis_result["shot_types"],
                    "similar_batter_matchup": analysis_result["similar_batter_matchup"],
                    "similar_batter_benchmark": analysis_result["similar_batter_benchmark"],
                    "similar_batter_lengths_lines": analysis_result["similar_batter_lengths_lines"],
                    "similar_batter_shot_directions": analysis_result["similar_batter_shot_directions"],
                },
                "error": None,
            }
    # Batter-specific bowling plan:
    # e.g. "what ball should be bowled to Pooran in death overs?"
    # e.g. "if captain has no choice but to bowl spin to Shivam Dube"
    is_batter_bowling_plan_question = (
        "what bowl" in question_lower
        or "what ball" in question_lower
        or "which ball" in question_lower
        or "what should be bowled" in question_lower
        or "bowling plan to" in question_lower
        or "bowl to" in question_lower
        or "bowl spin to" in question_lower
        or "bowl pace to" in question_lower
        or "type of spin" in question_lower
        or "type of pace" in question_lower
        or (
            "no choice" in question_lower
            and ("spin" in question_lower or "pace" in question_lower)
            and "to" in question_lower
        )
        or (
            "should" in question_lower
            and "bowl" in question_lower
            and "to" in question_lower
        )
    )

    if is_batter_bowling_plan_question:
        batter_condition = get_player_condition_from_question(user_question, "se.striker")

        if batter_condition is not None:
            phase_condition, phase_label = get_phase_condition_from_question(user_question, "se")

            if phase_condition is None:
                phase_label = "all overs"

            forced_mode = None

            if "spin" in question_lower and (
                "no choice" in question_lower
                or "must bowl" in question_lower
                or "forced" in question_lower
                or "type of spin" in question_lower
            ):
                forced_mode = "spin"
            elif "pace" in question_lower and (
                "no choice" in question_lower
                or "must bowl" in question_lower
                or "forced" in question_lower
                or "type of pace" in question_lower
            ):
                forced_mode = "pace"

            analysis_result = analyze_batter_bowling_plan(
                player_condition=batter_condition,
                phase_condition=phase_condition,
                phase_label=phase_label.replace("_", " "),
                forced_mode=forced_mode,
            )

            combined_sql = analysis_result["sql_queries"]["best_lengths"]
            combined_sql += "\n\n--- best_lines ---\n" + analysis_result["sql_queries"]["best_lines"]
            combined_sql += "\n\n--- bowling_types ---\n" + analysis_result["sql_queries"]["bowling_types"]
            combined_sql += "\n\n--- pace_options ---\n" + analysis_result["sql_queries"]["pace_options"]
            combined_sql += "\n\n--- spin_options ---\n" + analysis_result["sql_queries"]["spin_options"]
            combined_sql += "\n\n--- active_bowler_options ---\n" + analysis_result["sql_queries"]["active_bowler_options"]

            return {
                "method": "analysis_layer",
                "matched_question": "Batter bowling plan",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "best_lengths": analysis_result["best_lengths"],
                    "best_lines": analysis_result["best_lines"],
                    "bowling_types": analysis_result["bowling_types"],
                    "pace_options": analysis_result["pace_options"],
                    "spin_options": analysis_result["spin_options"],
                    "active_bowler_options": analysis_result["active_bowler_options"],
                },
                "error": None,
            }
    # Prediction / next season winner analysis
    if (
        "who will win next year" in question_lower
        or "who will win next season" in question_lower
        or "predict next season" in question_lower
        or "predict winner" in question_lower
        or "likely to win" in question_lower
        or "title chances" in question_lower
        or "win next year" in question_lower
        or "win next season" in question_lower
    ):
        analysis_result = analyze_team_title_chances()

        return {
            "method": "analysis_layer",
            "matched_question": "Team title chance analysis",
            "sql_query": analysis_result["sql_query"],
            "result": analysis_result["summary"],
            "analysis_paragraph": analysis_result.get("paragraph"),
            "error": None
        }

    # Bowler strategy analysis using line, length, shots, handedness, and phase
    if (
        "bowling strategy" in question_lower
        or "bowling plan" in question_lower
        or "line and length" in question_lower
        or "line length" in question_lower
        or "what should" in question_lower and "bowl" in question_lower
        or "avoid bowling" in question_lower
        or "bowl more" in question_lower
        or "ball type" in question_lower
        or "bowling pattern" in question_lower
    ):
        bowler_condition = get_player_condition_from_question(user_question, "se.bowler")

        if bowler_condition is not None:
            analysis_result = analyze_bowler_strategy(bowler_condition)

            combined_sql = "\n\n--- effective_line_length ---\n" + analysis_result["sql_queries"]["effective_line_length"]
            combined_sql += "\n\n--- expensive_line_length ---\n" + analysis_result["sql_queries"]["expensive_line_length"]
            combined_sql += "\n\n--- shots_conceded ---\n" + analysis_result["sql_queries"]["shots_conceded"]
            combined_sql += "\n\n--- wicket_shots ---\n" + analysis_result["sql_queries"]["wicket_shots"]
            combined_sql += "\n\n--- handedness ---\n" + analysis_result["sql_queries"]["handedness"]
            combined_sql += "\n\n--- phases ---\n" + analysis_result["sql_queries"]["phases"]

            return {
                "method": "analysis_layer",
                "matched_question": "Bowler strategy analysis",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "effective_line_length": analysis_result["effective_line_length"],
                    "expensive_line_length": analysis_result["expensive_line_length"],
                    "shots_conceded": analysis_result["shots_conceded"],
                    "wicket_shots": analysis_result["wicket_shots"],
                    "handedness": analysis_result["handedness"],
                    "phases": analysis_result["phases"],
                },
                "error": None
            }

    # Bowler matchup analysis
    if (
        "bowler" in question_lower
        or "bowling" in question_lower
        or "batsman" in question_lower
        or "batter" in question_lower
        or "matchup" in question_lower
        or "matchups" in question_lower
        or "most success against" in question_lower
        or "hits them for the most runs" in question_lower
        or "highest average against" in question_lower
        or "highest strike rate against" in question_lower
    ):
        bowler_condition = get_player_condition_from_question(user_question, "d.bowler")

        if bowler_condition is not None:
            analysis_result = analyze_bowler_matchups(bowler_condition)

            combined_sql = "\n\n--- most_dismissed ---\n" + analysis_result["sql_queries"]["most_dismissed"]
            combined_sql += "\n\n--- most_runs ---\n" + analysis_result["sql_queries"]["most_runs"]
            combined_sql += "\n\n--- highest_average ---\n" + analysis_result["sql_queries"]["highest_average"]
            combined_sql += "\n\n--- highest_strike_rate ---\n" + analysis_result["sql_queries"]["highest_strike_rate"]
            combined_sql += "\n\n--- phases ---\n" + analysis_result["sql_queries"]["phases"]

            return {
                "method": "analysis_layer",
                "matched_question": "Bowler matchup analysis",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "most_dismissed": analysis_result["most_dismissed"],
                    "most_runs": analysis_result["most_runs"],
                    "highest_average": analysis_result["highest_average"],
                    "highest_strike_rate": analysis_result["highest_strike_rate"],
                    "phases": analysis_result["phases"],
                },
                "error": None
            }

    # Full team profile analysis
    if (
        "team report" in question_lower
        or "team profile" in question_lower
        or "analyse team" in question_lower
        or "analyze team" in question_lower
        or "analyse" in question_lower
        or "analyze" in question_lower
        or "profile" in question_lower
    ):
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")

        if team_condition is not None:
            team_label = get_team_label_from_question(user_question)
            analysis_result = analyze_team_profile(team_condition, team_label)

            combined_sql = "\n\n--- overall ---\n" + analysis_result["sql_queries"]["overall"]
            combined_sql += "\n\n--- season_trend ---\n" + analysis_result["sql_queries"]["season_trend"]
            combined_sql += "\n\n--- batting ---\n" + analysis_result["sql_queries"]["batting"]
            combined_sql += "\n\n--- bowling ---\n" + analysis_result["sql_queries"]["bowling"]
            combined_sql += "\n\n--- chase_defend ---\n" + analysis_result["sql_queries"]["chase_defend"]
            combined_sql += "\n\n--- playoff ---\n" + analysis_result["sql_queries"]["playoff"]
            combined_sql += "\n\n--- venues ---\n" + analysis_result["sql_queries"]["venues"]
            combined_sql += "\n\n--- phase_batting ---\n" + analysis_result["sql_queries"]["phase_batting"]
            combined_sql += "\n\n--- top_run_scorers ---\n" + analysis_result["sql_queries"]["top_run_scorers"]
            combined_sql += "\n\n--- top_wicket_takers ---\n" + analysis_result["sql_queries"]["top_wicket_takers"]
            return {
                "method": "analysis_layer",
                "matched_question": "Full team profile analysis",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "overall": analysis_result["overall"],
                    "season_trend": analysis_result["season_trend"],
                    "batting": analysis_result["batting"],
                    "bowling": analysis_result["bowling"],
                    "chase_defend": analysis_result["chase_defend"],
                    "playoff": analysis_result["playoff"],
                    "venues": analysis_result["venues"],
                    "phase_batting": analysis_result["phase_batting"],
                    "top_run_scorers": analysis_result["top_run_scorers"],
                    "top_wicket_takers": analysis_result["top_wicket_takers"],
                },
                "error": None
            }

    # Player shot selection analysis
    if (
        "shot" in question_lower
        or "shots" in question_lower
        or "shot selection" in question_lower
        or "shouldn't play" in question_lower
        or "shouldnt play" in question_lower
        or "avoid playing" in question_lower
        or "avoid shot" in question_lower
        or "batting pattern" in question_lower
    ):
        player_condition = get_player_condition_from_question(user_question, "se.striker")

        if player_condition is not None:
            analysis_result = analyze_player_shots(player_condition)

            combined_sql = "\n\n--- shot_summary ---\n" + analysis_result["sql_queries"]["shot_summary"]
            combined_sql += "\n\n--- shot_dismissals ---\n" + analysis_result["sql_queries"]["shot_dismissals"]
            combined_sql += "\n\n--- risky_shots ---\n" + analysis_result["sql_queries"]["risky_shots"]
            combined_sql += "\n\n--- best_shots ---\n" + analysis_result["sql_queries"]["best_shots"]
            combined_sql += "\n\n--- line_length ---\n" + analysis_result["sql_queries"]["line_length"]
            combined_sql += "\n\n--- phase_shots ---\n" + analysis_result["sql_queries"]["phase_shots"]

            return {
                "method": "analysis_layer",
                "matched_question": "Player shot selection analysis",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "shot_summary": analysis_result["shot_summary"],
                    "shot_dismissals": analysis_result["shot_dismissals"],
                    "risky_shots": analysis_result["risky_shots"],
                    "best_shots": analysis_result["best_shots"],
                    "line_length": analysis_result["line_length"],
                    "phase_shots": analysis_result["phase_shots"],
                },
                "error": None
            }
    # Player dismissal analysis
    if (
        "dismissal" in question_lower
        or "dismissals" in question_lower
        or "gets out" in question_lower
        or "get out" in question_lower
        or "got out" in question_lower
        or "weakness" in question_lower
    ):
        player_condition = get_player_condition_from_question(user_question, "pd.batter")

        if player_condition is not None:
            analysis_result = analyze_player_dismissals(player_condition)

            combined_sql = "\n\n--- wicket_types ---\n" + analysis_result["sql_queries"]["wicket_types"]
            combined_sql += "\n\n--- phases ---\n" + analysis_result["sql_queries"]["phases"]
            combined_sql += "\n\n--- bowlers ---\n" + analysis_result["sql_queries"]["bowlers"]
            combined_sql += "\n\n--- opponents ---\n" + analysis_result["sql_queries"]["opponents"]
            combined_sql += "\n\n--- venues ---\n" + analysis_result["sql_queries"]["venues"]

            if "seasons" in analysis_result["sql_queries"]:
                combined_sql += "\n\n--- seasons ---\n" + analysis_result["sql_queries"]["seasons"]

            return {
                "method": "analysis_layer",
                "matched_question": "Player dismissal analysis",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "wicket_types": analysis_result["wicket_types"],
                    "phases": analysis_result["phases"],
                    "bowlers": analysis_result["bowlers"],
                    "opponents": analysis_result["opponents"],
                    "venues": analysis_result["venues"],
                    "seasons": analysis_result.get("seasons"),
                },
                "error": None
            }

    # Full player profile analysis
    if (
        "analyse" in question_lower
        or "analyze" in question_lower
        or "profile" in question_lower
        or "full analysis" in question_lower
        or "player report" in question_lower
        or "scouting report" in question_lower
    ):
        player_condition = get_player_condition_from_question(user_question, "d.striker")

        if player_condition is not None:
            analysis_result = analyze_player_profile(player_condition)

            combined_sql = "\n\n--- career ---\n" + analysis_result["sql_queries"]["career"]
            combined_sql += "\n\n--- season_trend ---\n" + analysis_result["sql_queries"]["season_trend"]
            combined_sql += "\n\n--- phase_performance ---\n" + analysis_result["sql_queries"]["phase_performance"]
            combined_sql += "\n\n--- opponent_performance ---\n" + analysis_result["sql_queries"]["opponent_performance"]
            combined_sql += "\n\n--- venue_performance ---\n" + analysis_result["sql_queries"]["venue_performance"]
            combined_sql += "\n\n--- playoff_performance ---\n" + analysis_result["sql_queries"]["playoff_performance"]
            combined_sql += "\n\n--- dismissal_types ---\n" + analysis_result["sql_queries"]["dismissal_types"]
            combined_sql += "\n\n--- bowler_success ---\n" + analysis_result["sql_queries"]["bowler_success"]
            combined_sql += "\n\n--- bowler_dismissals ---\n" + analysis_result["sql_queries"]["bowler_dismissals"]
            combined_sql += "\n\n--- quiet_bowlers ---\n" + analysis_result["sql_queries"]["quiet_bowlers"]
            combined_sql += "\n\n--- preferred_bowler_types ---\n" + analysis_result["sql_queries"]["preferred_bowler_types"]
            combined_sql += "\n\n--- difficult_bowler_types ---\n" + analysis_result["sql_queries"]["difficult_bowler_types"]
            combined_sql += "\n\n--- active_quiet_bowlers ---\n" + analysis_result["sql_queries"]["active_quiet_bowlers"]
            return {
                "method": "analysis_layer",
                "matched_question": "Full player profile analysis",
                "sql_query": combined_sql,
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "career": analysis_result["career"],
                    "season_trend": analysis_result["season_trend"],
                    "phase_performance": analysis_result["phase_performance"],
                    "opponent_performance": analysis_result["opponent_performance"],
                    "venue_performance": analysis_result["venue_performance"],
                    "playoff_performance": analysis_result["playoff_performance"],
                    "dismissal_types": analysis_result["dismissal_types"],
                    "bowler_success": analysis_result["bowler_success"],
                    "bowler_dismissals": analysis_result["bowler_dismissals"],
                    "quiet_bowlers": analysis_result["quiet_bowlers"],
                    "preferred_bowler_types": analysis_result["preferred_bowler_types"],
                    "difficult_bowler_types": analysis_result["difficult_bowler_types"],
                    "active_quiet_bowlers": analysis_result["active_quiet_bowlers"],
                },
                "error": None
            }
    # Last N encounters between two teams, e.g. last 5 encounters of MI vs CSK
    if (
        ("last" in question_lower or "recent" in question_lower)
        and (
            "encounter" in question_lower
            or "encounters" in question_lower
            or "meeting" in question_lower
            or "meetings" in question_lower
            or "matches" in question_lower
            or "games" in question_lower
        )
        and "vs" in question_lower
    ):
        limit_match = re.search(r"\blast\s+(\d+)\b", question_lower)

        if limit_match is not None:
            match_limit = int(limit_match.group(1))
        else:
            match_limit = 5

        team_one_condition = get_team_condition_before_keyword(user_question, "vs", "dx.batting_team")
        team_two_condition = get_team_condition_after_keyword(user_question, "vs", "dy.batting_team")

        team_one_label = get_team_label_before_keyword(user_question, "vs")
        team_two_label = get_team_label_after_keyword(user_question, "vs")

        if team_one_condition is not None and team_two_condition is not None:
            match_filter_sql = f"""
EXISTS (
    SELECT 1
    FROM deliveries dx
    WHERE dx.match_id = m.match_id
      AND {team_one_condition}
)
AND EXISTS (
    SELECT 1
    FROM deliveries dy
    WHERE dy.match_id = m.match_id
      AND {team_two_condition}
)
""".strip()

            analysis_result = analyze_match_summaries(
                match_filter_sql=match_filter_sql,
                context_label=f"last {match_limit} encounters of {team_one_label} vs {team_two_label}",
                limit=match_limit,
            )

            return {
                "method": "analysis_layer",
                "matched_question": "Last team encounters summary",
                "sql_query": analysis_result["sql_query"],
                "result": analysis_result["summary"],
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "match_summaries": analysis_result["match_summaries"],
                },
                "error": None
            }

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

    analysis_response = build_analysis_response(user_question)

    if analysis_response is not None:
        return analysis_response

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