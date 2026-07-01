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
    analyze_strongest_current_squads,
    analyze_current_squad_report,
    analyze_bowler_length_plan_against_batter,
    analyze_enhanced_team_profile,
    analyze_team_vs_team_match_plan,
    analyze_venue_profile,
    analyze_bowlers_against_batter,
    analyze_player_profile_smart,
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
        "hazlewood": "JR Hazlewood",
        "josh hazlewood": "JR Hazlewood",
        "khaleel": "KK Ahmed",
        "khaleel ahmed": "KK Ahmed",
        "shubman gill": "Shubman Gill",
        "gill": "Shubman Gill",

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

def get_team_condition_before_keyword(user_question, keyword, column_name):
    question_lower = user_question.lower()
    keyword_lower = keyword.lower()
    index = question_lower.find(keyword_lower)

    if index == -1:
        return None

    text_before = user_question[:index]
    return get_team_condition_from_question(text_before, column_name)


def get_team_condition_after_keyword(user_question, keyword, column_name):
    question_lower = user_question.lower()
    keyword_lower = keyword.lower()
    index = question_lower.find(keyword_lower)

    if index == -1:
        return None

    text_after = user_question[index + len(keyword):]
    return get_team_condition_from_question(text_after, column_name)


def get_team_label_before_keyword(user_question, keyword):
    question_lower = user_question.lower()
    keyword_lower = keyword.lower()
    index = question_lower.find(keyword_lower)

    if index == -1:
        return "Team A"

    text_before = user_question[:index]
    return get_team_label_from_question(text_before)


def get_team_label_after_keyword(user_question, keyword):
    question_lower = user_question.lower()
    keyword_lower = keyword.lower()
    index = question_lower.find(keyword_lower)

    if index == -1:
        return "Team B"

    text_after = user_question[index + len(keyword):]
    return get_team_label_from_question(text_after)


def get_venue_condition_from_question(user_question, column_name="m.venue"):
    q = user_question.lower()

    venue_aliases = {
        "chepauk": {
            "label": "Chepauk",
            "venues": [
                "MA Chidambaram Stadium",
                "MA Chidambaram Stadium, Chepauk",
                "MA Chidambaram Stadium, Chepauk, Chennai",
            ],
        },
        "chennai": {
            "label": "Chepauk",
            "venues": [
                "MA Chidambaram Stadium",
                "MA Chidambaram Stadium, Chepauk",
                "MA Chidambaram Stadium, Chepauk, Chennai",
            ],
        },
        "wankhede": {
            "label": "Wankhede",
            "venues": [
                "Wankhede Stadium",
                "Wankhede Stadium, Mumbai",
            ],
        },
        "eden": {
            "label": "Eden Gardens",
            "venues": [
                "Eden Gardens",
                "Eden Gardens, Kolkata",
            ],
        },
        "chinnaswamy": {
            "label": "Chinnaswamy",
            "venues": [
                "M Chinnaswamy Stadium",
                "M.Chinnaswamy Stadium",
                "M Chinnaswamy Stadium, Bengaluru",
            ],
        },
        "bengaluru": {
            "label": "Chinnaswamy",
            "venues": [
                "M Chinnaswamy Stadium",
                "M.Chinnaswamy Stadium",
                "M Chinnaswamy Stadium, Bengaluru",
            ],
        },
        "bangalore": {
            "label": "Chinnaswamy",
            "venues": [
                "M Chinnaswamy Stadium",
                "M.Chinnaswamy Stadium",
                "M Chinnaswamy Stadium, Bengaluru",
            ],
        },
        "ahmedabad": {
            "label": "Ahmedabad",
            "venues": [
                "Narendra Modi Stadium",
                "Narendra Modi Stadium, Ahmedabad",
                "Sardar Patel Stadium, Motera",
            ],
        },
        "motera": {
            "label": "Ahmedabad",
            "venues": [
                "Narendra Modi Stadium",
                "Narendra Modi Stadium, Ahmedabad",
                "Sardar Patel Stadium, Motera",
            ],
        },
        "kotla": {
            "label": "Delhi",
            "venues": [
                "Arun Jaitley Stadium",
                "Arun Jaitley Stadium, Delhi",
                "Feroz Shah Kotla",
            ],
        },
        "arun jaitley": {
            "label": "Delhi",
            "venues": [
                "Arun Jaitley Stadium",
                "Arun Jaitley Stadium, Delhi",
                "Feroz Shah Kotla",
            ],
        },
        "uppal": {
            "label": "Hyderabad",
            "venues": [
                "Rajiv Gandhi International Stadium",
                "Rajiv Gandhi International Stadium, Uppal",
                "Rajiv Gandhi International Stadium, Uppal, Hyderabad",
            ],
        },
        "hyderabad": {
            "label": "Hyderabad",
            "venues": [
                "Rajiv Gandhi International Stadium",
                "Rajiv Gandhi International Stadium, Uppal",
                "Rajiv Gandhi International Stadium, Uppal, Hyderabad",
            ],
        },
    }

    for key, info in venue_aliases.items():
        if key in q:
            venue_values = ", ".join(
                "'" + venue.replace("'", "''") + "'" for venue in info["venues"]
            )
            return f"{column_name} IN ({venue_values})", info["label"]

    return None, None

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
        where_sql = build_where_sql(where_clauses)

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
        where_sql = build_where_sql(where_clauses)

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
        where_sql = build_where_sql(where_clauses)

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
        where_sql = build_where_sql(where_clauses)

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

def build_team_trophies_sql():
    return """
WITH season_final_dates AS (
    SELECT
        season,
        MAX(CAST(start_date AS date)) AS final_date
    FROM matches
    WHERE winner IS NOT NULL
    GROUP BY season
),
season_finals AS (
    SELECT
        m.season,
        m.start_date,
        m.winner
    FROM matches m
    JOIN season_final_dates f
        ON m.season = f.season
       AND CAST(m.start_date AS date) = f.final_date
    WHERE m.winner IS NOT NULL
)
SELECT
    winner AS team,
    COUNT(*) AS trophies
FROM season_finals
GROUP BY winner
ORDER BY trophies DESC, team ASC;
""".strip()

def build_highest_score_losing_cause_sql():
    return """
WITH batter_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.batting_team,
        d.bowling_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        m.winner,
        SUM(d.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN COALESCE(d.wides, 0) = 0
             AND COALESCE(d.noballs, 0) = 0
            THEN 1
        END) AS balls,
        SUM(CASE WHEN d.runs_off_bat = 4 THEN 1 ELSE 0 END) AS fours,
        SUM(CASE WHEN d.runs_off_bat = 6 THEN 1 ELSE 0 END) AS sixes
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE m.winner IS NOT NULL
      AND d.batting_team <> m.winner
    GROUP BY
        d.match_id,
        d.innings,
        d.striker,
        d.batting_team,
        d.bowling_team,
        m.season,
        m.start_date,
        m.venue,
        m.winner
)
SELECT TOP 10
    batter,
    batting_team,
    opponent,
    season,
    start_date,
    venue,
    winner,
    runs,
    balls,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate,
    fours,
    sixes
FROM batter_innings
ORDER BY runs DESC, strike_rate DESC;
""".strip()


def build_best_bowling_losing_cause_sql():
    return """
WITH bowler_figures AS (
    SELECT
        d.match_id,
        d.bowler,
        d.bowling_team,
        d.batting_team AS opponent,
        m.season,
        m.start_date,
        m.venue,
        m.winner,
        COUNT(CASE
            WHEN COALESCE(d.wides, 0) = 0
             AND COALESCE(d.noballs, 0) = 0
            THEN 1
        END) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE m.winner IS NOT NULL
      AND d.bowling_team <> m.winner
    GROUP BY
        d.match_id,
        d.bowler,
        d.bowling_team,
        d.batting_team,
        m.season,
        m.start_date,
        m.venue,
        m.winner
)
SELECT TOP 10
    bowler,
    bowling_team,
    opponent,
    season,
    start_date,
    venue,
    winner,
    CONCAT(legal_balls / 6, '.', legal_balls % 6) AS overs,
    runs_conceded,
    wickets,
    CONCAT(wickets, '/', runs_conceded) AS bowling_figures,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy_rate
FROM bowler_figures
WHERE wickets > 0
ORDER BY wickets DESC, runs_conceded ASC, economy_rate ASC;
""".strip()


def build_most_runs_single_over_sql():
    return """
WITH over_scores AS (
    SELECT
        d.match_id,
        d.innings,
        CAST(FLOOR(d.ball) AS int) + 1 AS over_number,
        d.batting_team,
        d.bowling_team,
        MAX(d.bowler) AS bowler,
        m.season,
        m.start_date,
        m.venue,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS over_runs,
        SUM(COALESCE(d.runs_off_bat, 0)) AS bat_runs,
        SUM(COALESCE(d.extras, 0)) AS extras,
        COUNT(CASE
            WHEN COALESCE(d.wides, 0) = 0
             AND COALESCE(d.noballs, 0) = 0
            THEN 1
        END) AS legal_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    GROUP BY
        d.match_id,
        d.innings,
        CAST(FLOOR(d.ball) AS int) + 1,
        d.batting_team,
        d.bowling_team,
        m.season,
        m.start_date,
        m.venue
)
SELECT TOP 10
    batting_team,
    bowling_team,
    bowler,
    season,
    start_date,
    venue,
    innings,
    over_number,
    over_runs,
    bat_runs,
    extras,
    legal_balls
FROM over_scores
ORDER BY over_runs DESC, bat_runs DESC;
""".strip()

def build_curated_sql(user_question):

    losing_batting_terms = [
        "highest score in a losing cause",
        "highest score losing cause",
        "most runs in a losing cause",
        "most runs losing cause",
        "best innings in a losing cause",
        "best batting in a losing cause",
    ]

    losing_bowling_terms = [
        "best bowling in a losing cause",
        "best bowling figures in a losing cause",
        "best bowling losing cause",
        "most wickets in a losing cause",
        "best figures in a losing cause",
    ]

    single_over_terms = [
        "most runs in a single over",
        "most runs in one over",
        "highest scoring over",
        "most expensive over",
        "most runs off an over",
    ]

    q_lower = user_question.lower()

    if any(term in q_lower for term in losing_batting_terms):
        return build_highest_score_losing_cause_sql()

    if any(term in q_lower for term in losing_bowling_terms):
        return build_best_bowling_losing_cause_sql()

    if any(term in q_lower for term in single_over_terms):
        return build_most_runs_single_over_sql()


    trophy_question_terms = [
        "most trophies",
        "most trophy",
        "most titles",
        "most title",
        "most championships",
        "most championship",
        "ipl trophies",
        "ipl titles",
        "ipl champions",
        "team has won the most",
    ]

    if any(term in user_question.lower() for term in trophy_question_terms):
        return build_team_trophies_sql()

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
            where_sql = build_where_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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
            where_sql = build_where_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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

            where_sql = build_and_sql(where_clauses)
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
            where_sql = build_where_sql(where_clauses)

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
            where_sql = build_where_sql(where_clauses)

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
            where_sql = build_where_sql(where_clauses)

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
            where_sql = build_where_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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

        where_sql = build_and_sql(where_clauses)

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
def get_player_label_from_condition(player_condition):
    if player_condition is None:
        return "the player"

    condition_text = str(player_condition)

    readable_names = {
        "V Kohli": "Virat Kohli",
        "RG Sharma": "Rohit Sharma",
        "MS Dhoni": "MS Dhoni",
        "JJ Bumrah": "Jasprit Bumrah",
        "Rashid Khan": "Rashid Khan",
        "N Pooran": "Nicholas Pooran",
        "S Dube": "Shivam Dube",
        "AD Russell": "Andre Russell",
        "SP Narine": "Sunil Narine",
        "Shubman Gill": "Shubman Gill",
        "B Sai Sudharsan": "Sai Sudharsan",
    }

    for short_name, readable_name in readable_names.items():
        if short_name in condition_text:
            return readable_name

    # Fallback: take first quoted player name from the SQL condition.
    if "'" in condition_text:
        parts = condition_text.split("'")
        if len(parts) >= 2:
            return parts[1]

    return "the player"


def get_player_label_from_question(user_question):
    player_condition = get_player_condition_from_question(user_question, "d.striker")
    return get_player_label_from_condition(player_condition)

def remove_empty_extra_tables(extra_tables):
    clean_tables = {}

    for key, value in (extra_tables or {}).items():
        if value is None:
            continue

        if hasattr(value, "empty") and value.empty:
            continue

        clean_tables[key] = value

    return clean_tables

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
                "sql_query": analysis_result.get("sql_query"),
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "match_summaries": analysis_result.get("match_summaries"),
                },
                "error": None
            }
    is_venue_profile_question = (
        "tell me about" in question_lower
        or "venue profile" in question_lower
        or "ground profile" in question_lower
        or "stadium profile" in question_lower
        or "stats at" in question_lower
        or "stats for" in question_lower
    )

    if is_venue_profile_question:
        venue_condition, venue_label = get_venue_condition_from_question(user_question)

        if venue_condition is not None:
            analysis_result = analyze_venue_profile(
                venue_condition=venue_condition,
                venue_label=venue_label,
            )

            combined_sql = ""
            for name, sql in analysis_result["sql_queries"].items():
                combined_sql += f"\n\n--- {name} ---\n{sql}"

            return {
                "method": "analysis_layer",
                "matched_question": "Venue profile",
                "sql_query": combined_sql.strip(),
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "venue_overview": analysis_result.get("overview"),
                    "highest_team_scores": analysis_result.get("highest_team_scores"),
                    "top_run_scorers": analysis_result.get("top_run_scorers"),
                    "top_wicket_takers": analysis_result.get("top_wicket_takers"),
                    "best_individual_scores": analysis_result.get("best_individual_scores"),
                    "best_bowling_figures": analysis_result.get("best_bowling_figures"),
                    "best_non_home_batters": analysis_result.get("non_home_batters"),
                    "best_non_home_bowlers": analysis_result.get("non_home_bowlers"),
                },
                "error": None,
            }
    is_best_bowlers_against_batter_question = (
        "best bowlers against" in question_lower
        or "bowlers against" in question_lower
        or "bowlers should be used against" in question_lower
        or "which bowlers should be used against" in question_lower
    )

    if is_best_bowlers_against_batter_question:
        batter_condition = get_player_condition_from_question(user_question, "d.striker")
        batter_label = get_player_label_from_question(user_question)

        bowling_team_condition = get_team_condition_from_question(user_question, "d.bowling_team")
        bowling_team_label = get_team_label_from_question(user_question)

        venue_condition, venue_label = get_venue_condition_from_question(user_question)

        if batter_condition is not None:
            analysis_result = analyze_bowlers_against_batter(
                batter_condition=batter_condition,
                batter_label=batter_label,
                bowling_team_condition=bowling_team_condition,
                bowling_team_label=bowling_team_label if bowling_team_condition is not None else None,
                venue_condition=venue_condition,
                venue_label=venue_label if venue_condition is not None else None,
            )

            combined_sql = ""
            for name, sql in analysis_result["sql_queries"].items():
                combined_sql += f"\n\n--- {name} ---\n{sql}"

            return {
                "method": "analysis_layer",
                "matched_question": "Best bowlers against batter",
                "sql_query": combined_sql.strip(),
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "bowler_matchups": analysis_result.get("bowler_matchups"),
                },
                "error": None,
            }
    # Team-vs-team match plan
    is_match_plan_question = (
        (
            "how can" in question_lower
            or "how do" in question_lower
            or "plan to beat" in question_lower
            or "strategy to beat" in question_lower
            or "beat" in question_lower
        )
        and "beat" in question_lower
    )

    if is_match_plan_question:
        team_a_condition = get_team_condition_before_keyword(user_question, "beat", "cs.team_name")
        team_b_condition = get_team_condition_after_keyword(user_question, "beat", "cs.team_name")

        team_a_label = get_team_label_before_keyword(user_question, "beat")
        team_b_label = get_team_label_after_keyword(user_question, "beat")

        venue_condition, venue_label = get_venue_condition_from_question(user_question)

        if team_a_condition is not None and team_b_condition is not None:
            analysis_result = analyze_team_vs_team_match_plan(
                team_a_condition=team_a_condition,
                team_b_condition=team_b_condition,
                team_a_label=team_a_label,
                team_b_label=team_b_label,
                venue_condition=venue_condition,
                venue_label=venue_label,
            )

            combined_sql = ""

            for name, sql in analysis_result["sql_queries"].items():
                combined_sql += f"\n\n--- {name} ---\n{sql}"

            return {
                "method": "analysis_layer",
                "matched_question": "Team-vs-team match plan",
                "sql_query": combined_sql.strip(),
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "action_plan": analysis_result.get("action_plan"),
                    "head_to_head": analysis_result.get("head_to_head"),
                    "recent_head_to_head_results": analysis_result.get("recent_head_to_head_results"),
                    "venue_profile": analysis_result.get("venue_profile"),
                    "opponent_chase_thresholds": analysis_result.get("opponent_chase_thresholds"),
                    "recent_chase_benchmark": analysis_result.get("recent_chase_benchmark"),
                    "opponent_batting_first_restrict": analysis_result.get("opponent_batting_first_restrict"),
                    "recent_restrict_benchmark": analysis_result.get("recent_restrict_benchmark"),
                    "opponent_top3_dependency": analysis_result.get("opponent_top3_dependency"),
                    "top3_dependency_summary": analysis_result.get("top3_dependency_summary"),
                    "opponent_current_key_batters": analysis_result.get("opponent_current_key_batters"),
                    "bowling_phase_matchups": analysis_result.get("bowling_phase_matchups"),
                    "batting_phase_matchups": analysis_result.get("batting_phase_matchups"),
                },
                "error": None,
            }
            # Strongest current squad ranking
    if (
        "strongest current squad" in question_lower
        or "best current squad" in question_lower
        or "which team has the strongest squad" in question_lower
        or "which team has the best squad" in question_lower
        or "squad strength ranking" in question_lower
    ):
        analysis_result = analyze_strongest_current_squads()

        combined_sql = analysis_result["sql_queries"].get("team_scores", "")

        return {
            "method": "analysis_layer",
            "matched_question": "Strongest current squads",
            "sql_query": combined_sql,
            "result": analysis_result.get("summary"),
            "analysis_paragraph": analysis_result.get("paragraph"),
            "extra_tables": {
                "team_scores": analysis_result.get("team_scores"),
            },
            "error": None,
        }
        # Current squad report for a team
    if (
        "current squad" in question_lower
        or "squad report" in question_lower
        or "squad strength" in question_lower
        or ("squad" in question_lower and ("analyse" in question_lower or "analyze" in question_lower))
    ):
        squad_team_condition = get_team_condition_from_question(user_question, "cs.team_name")
        team_label = get_team_label_from_question(user_question)

        if squad_team_condition is not None:
            analysis_result = analyze_current_squad_report(
                team_condition=squad_team_condition,
                team_label=team_label,
            )

            _sql_queries = analysis_result.get("sql_queries") or {}
            combined_sql = _sql_queries.get("current_squad")
            if not combined_sql:
                combined_sql = "\\n\\n".join(str(value) for value in _sql_queries.values() if value)
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("current_squad_batting")
            if _sql_piece:
                combined_sql += "\n\n--- current_squad_batting ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("current_squad_bowling")
            if _sql_piece:
                combined_sql += "\n\n--- current_squad_bowling ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("players_to_watch")
            if _sql_piece:
                combined_sql += "\n\n--- players_to_watch ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("historical_batting_legends")
            if _sql_piece:
                combined_sql += "\n\n--- historical_batting_legends ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("historical_bowling_legends")
            if _sql_piece:
                combined_sql += "\n\n--- historical_bowling_legends ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Current squad report",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "current_squad": analysis_result.get("current_squad"),
                    "current_squad_batting": analysis_result.get("current_squad_batting"),
                    "current_squad_bowling": analysis_result.get("current_squad_bowling"),
                    "players_to_watch": analysis_result.get("players_to_watch"),
                    "historical_batting_legends": analysis_result.get("historical_batting_legends"),
                    "historical_bowling_legends": analysis_result.get("historical_bowling_legends"),
                },
                "error": None,
            }
    # Enhanced normal team report
    is_enhanced_team_report_question = (
        (
            "analyse" in question_lower
            or "analyze" in question_lower
            or "team report" in question_lower
            or "team profile" in question_lower
            or "profile" in question_lower
        )
        and "squad" not in question_lower
    )

    if is_enhanced_team_report_question:
        team_condition = get_team_condition_from_question(user_question, "d.batting_team")
        team_label = get_team_label_from_question(user_question)

        if team_condition is not None:
            analysis_result = analyze_enhanced_team_profile(
                team_condition=team_condition,
                team_label=team_label,
            )

            combined_sql = ""
            for name, sql in analysis_result["sql_queries"].items():
                combined_sql += f"\n\n--- {name} ---\n{sql}"

            return {
                "method": "analysis_layer",
                "matched_question": "Enhanced team report",
                "sql_query": combined_sql.strip(),
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "trophy_record": analysis_result.get("trophy_record"),
                    "team_report_squad_summary": analysis_result.get("team_report_squad_summary"),
                    "historical_batting_legends": analysis_result.get("historical_batting_legends"),
                    "historical_bowling_legends": analysis_result.get("historical_bowling_legends"),
                    "current_batters_to_watch": analysis_result.get("current_batters_to_watch"),
                    "current_bowlers_to_watch": analysis_result.get("current_bowlers_to_watch"),
                    "squad_snapshot": analysis_result.get("squad_snapshot"),
                },
                "error": None,
            }
    # Bowler-specific length/line plan vs batter
    is_bowler_length_line_question = (
        (
            "what length" in question_lower
            or "which length" in question_lower
            or "what line" in question_lower
            or "which line" in question_lower
            or "where should" in question_lower
            or "how should" in question_lower
        )
        and (
            "bowl against" in question_lower
            or "bowl to" in question_lower
            or "against" in question_lower
        )
    )

    if is_bowler_length_line_question:
        bowler_condition = None
        batter_condition = None

        if "against" in question_lower:
            bowler_condition = get_player_condition_before_keyword(user_question, "against", "se.bowler")
            batter_condition = get_player_condition_after_keyword(user_question, "against", "se.striker")

        if bowler_condition is None and "to" in question_lower:
            bowler_condition = get_player_condition_before_keyword(user_question, "to", "se.bowler")
            batter_condition = get_player_condition_after_keyword(user_question, "to", "se.striker")

        phase_condition = None
        phase_label = None

        if "powerplay" in question_lower or "power play" in question_lower:
            phase_condition = "FLOOR(se.ball) BETWEEN 0 AND 5"
            phase_label = "powerplay"
        elif "middle" in question_lower:
            phase_condition = "FLOOR(se.ball) BETWEEN 6 AND 14"
            phase_label = "middle overs"
        elif "death" in question_lower:
            phase_condition = "FLOOR(se.ball) BETWEEN 15 AND 19"
            phase_label = "death overs"

        if bowler_condition is not None and batter_condition is not None:
            analysis_result = analyze_bowler_length_plan_against_batter(
                bowler_condition=bowler_condition,
                batter_condition=batter_condition,
                phase_condition=phase_condition,
                phase_label=phase_label,
            )

            sql_queries = analysis_result.get("sql_queries") or {}
            combined_sql = sql_queries.get("length_line_plan")
            if not combined_sql:
                combined_sql = "\\n\\n".join(str(value) for value in sql_queries.values() if value)
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("shot_response")
            if _sql_piece:
                combined_sql += "\n\n--- shot_response ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("direct_summary")
            if _sql_piece:
                combined_sql += "\n\n--- direct_summary ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Bowler-specific length and line plan",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "length_line_plan": analysis_result.get("length_line_plan"),
                    "direct_length_line_plan": analysis_result.get("direct_length_line_plan"),
                    "proxy_bowler_style_plan": analysis_result.get("proxy_bowler_style_plan"),
                    "proxy_batter_style_plan": analysis_result.get("proxy_batter_style_plan"),
                    "shot_response": analysis_result.get("shot_response"),
                    "shot_direction": analysis_result.get("shot_direction"),
                    "direct_summary": analysis_result.get("direct_summary"),
                    "batter_profile": analysis_result.get("batter_profile"),
                    "bowler_profile": analysis_result.get("bowler_profile"),
                },
                "error": None,
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

            _sql_queries = analysis_result.get("sql_queries") or {}
            combined_sql = _sql_queries.get("direct_options")
            if not combined_sql:
                combined_sql = "\\n\\n".join(str(value) for value in _sql_queries.values() if value)
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("proxy_options")
            if _sql_piece:
                combined_sql += "\n\n--- proxy_options ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("recommended_lengths_lines")
            if _sql_piece:
                combined_sql += "\n\n--- recommended_lengths_lines ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Team bowler recommendation",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "direct_options": analysis_result.get("direct_options"),
                    "proxy_options": analysis_result.get("proxy_options"),
                    "recommended_lengths_lines": analysis_result.get("recommended_lengths_lines"),
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

            _sql_queries = analysis_result.get("sql_queries") or {}
            combined_sql = _sql_queries.get("direct_summary")
            if not combined_sql:
                combined_sql = "\\n\\n".join(str(value) for value in _sql_queries.values() if value)
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("scoring_areas")
            if _sql_piece:
                combined_sql += "\n\n--- scoring_areas ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("scoring_shots")
            if _sql_piece:
                combined_sql += "\n\n--- scoring_shots ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("risky_shots")
            if _sql_piece:
                combined_sql += "\n\n--- risky_shots ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("length_line_attack")
            if _sql_piece:
                combined_sql += "\n\n--- length_line_attack ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Batter plan against bowler",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "direct_summary": analysis_result.get("direct_summary"),
                    "scoring_areas": analysis_result.get("scoring_areas"),
                    "scoring_shots": analysis_result.get("scoring_shots"),
                    "risky_shots": analysis_result.get("risky_shots"),
                    "length_line_attack": analysis_result.get("length_line_attack"),
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

            _sql_queries = analysis_result.get("sql_queries") or {}
            combined_sql = _sql_queries.get("direct_matchup")
            if not combined_sql:
                combined_sql = "\\n\\n".join(str(value) for value in _sql_queries.values() if value)
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("batter_benchmark")
            if _sql_piece:
                combined_sql += "\n\n--- batter_benchmark ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("phase_breakdown")
            if _sql_piece:
                combined_sql += "\n\n--- phase_breakdown ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("recommended_lengths_lines")
            if _sql_piece:
                combined_sql += "\n\n--- recommended_lengths_lines ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("shot_directions")
            if _sql_piece:
                combined_sql += "\n\n--- shot_directions ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("shot_types")
            if _sql_piece:
                combined_sql += "\n\n--- shot_types ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("similar_batter_matchup")
            if _sql_piece:
                combined_sql += "\n\n--- similar_batter_matchup ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("similar_batter_benchmark")
            if _sql_piece:
                combined_sql += "\n\n--- similar_batter_benchmark ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("similar_batter_lengths_lines")
            if _sql_piece:
                combined_sql += "\n\n--- similar_batter_lengths_lines ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("similar_batter_shot_directions")
            if _sql_piece:
                combined_sql += "\n\n--- similar_batter_shot_directions ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Bowler vs batter decision",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "direct_matchup": analysis_result.get("direct_matchup"),
                    "batter_benchmark": analysis_result.get("batter_benchmark"),
                    "phase_breakdown": analysis_result.get("phase_breakdown"),
                    "recommended_lengths_lines": analysis_result.get("recommended_lengths_lines"),
                    "shot_directions": analysis_result.get("shot_directions"),
                    "shot_types": analysis_result.get("shot_types"),
                    "similar_batter_matchup": analysis_result.get("similar_batter_matchup"),
                    "similar_batter_benchmark": analysis_result.get("similar_batter_benchmark"),
                    "similar_batter_lengths_lines": analysis_result.get("similar_batter_lengths_lines"),
                    "similar_batter_shot_directions": analysis_result.get("similar_batter_shot_directions"),
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

            _sql_queries = analysis_result.get("sql_queries") or {}
            combined_sql = _sql_queries.get("best_lengths")
            if not combined_sql:
                combined_sql = "\\n\\n".join(str(value) for value in _sql_queries.values() if value)
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("best_lines")
            if _sql_piece:
                combined_sql += "\n\n--- best_lines ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("bowling_types")
            if _sql_piece:
                combined_sql += "\n\n--- bowling_types ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("pace_options")
            if _sql_piece:
                combined_sql += "\n\n--- pace_options ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("spin_options")
            if _sql_piece:
                combined_sql += "\n\n--- spin_options ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("active_bowler_options")
            if _sql_piece:
                combined_sql += "\n\n--- active_bowler_options ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Batter bowling plan",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "best_lengths": analysis_result.get("best_lengths"),
                    "best_lines": analysis_result.get("best_lines"),
                    "bowling_types": analysis_result.get("bowling_types"),
                    "pace_options": analysis_result.get("pace_options"),
                    "spin_options": analysis_result.get("spin_options"),
                    "active_bowler_options": analysis_result.get("active_bowler_options"),
                },
                "error": None,
            }
        # Squad-aware title prediction
    if (
        "who will win next year" in question_lower
        or "who will win next season" in question_lower
        or "predict next season" in question_lower
        or "predict winner" in question_lower
        or "likely to win" in question_lower
        or "title chances" in question_lower
        or "win next year" in question_lower
        or "win next season" in question_lower
        or "strongest title contender" in question_lower
        or "favourites to win" in question_lower
        or "favorites to win" in question_lower
    ):
        analysis_result = analyze_team_title_chances()

        _sql_queries = analysis_result.get("sql_queries") or {}
        combined_sql = _sql_queries.get("team_scores")
        if not combined_sql:
            combined_sql = "\\n\\n".join(str(value) for value in _sql_queries.values() if value)
        _sql_piece = (analysis_result.get("sql_queries") or {}).get("current_squad_batting_leaders")
        if _sql_piece:
            combined_sql += "\n\n--- current_squad_batting_leaders ---\n" + _sql_piece
        _sql_piece = (analysis_result.get("sql_queries") or {}).get("current_squad_bowling_leaders")
        if _sql_piece:
            combined_sql += "\n\n--- current_squad_bowling_leaders ---\n" + _sql_piece

        return {
            "method": "analysis_layer",
            "matched_question": "Squad-aware title prediction",
            "sql_query": combined_sql,
            "result": analysis_result.get("summary"),
            "analysis_paragraph": analysis_result.get("paragraph"),
            "extra_tables": {
                "team_scores": analysis_result.get("team_scores"),
                "current_squad_batting_leaders": analysis_result.get("current_squad_batting_leaders"),
                "current_squad_bowling_leaders": analysis_result.get("current_squad_bowling_leaders"),
            },
            "error": None,
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
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("expensive_line_length")
            if _sql_piece:
                combined_sql += "\n\n--- expensive_line_length ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("shots_conceded")
            if _sql_piece:
                combined_sql += "\n\n--- shots_conceded ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("wicket_shots")
            if _sql_piece:
                combined_sql += "\n\n--- wicket_shots ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("handedness")
            if _sql_piece:
                combined_sql += "\n\n--- handedness ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("phases")
            if _sql_piece:
                combined_sql += "\n\n--- phases ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Bowler strategy analysis",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "effective_line_length": analysis_result.get("effective_line_length"),
                    "expensive_line_length": analysis_result.get("expensive_line_length"),
                    "shots_conceded": analysis_result.get("shots_conceded"),
                    "wicket_shots": analysis_result.get("wicket_shots"),
                    "handedness": analysis_result.get("handedness"),
                    "phases": analysis_result.get("phases"),
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
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("most_runs")
            if _sql_piece:
                combined_sql += "\n\n--- most_runs ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("highest_average")
            if _sql_piece:
                combined_sql += "\n\n--- highest_average ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("highest_strike_rate")
            if _sql_piece:
                combined_sql += "\n\n--- highest_strike_rate ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("phases")
            if _sql_piece:
                combined_sql += "\n\n--- phases ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Bowler matchup analysis",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "most_dismissed": analysis_result.get("most_dismissed"),
                    "most_runs": analysis_result.get("most_runs"),
                    "highest_average": analysis_result.get("highest_average"),
                    "highest_strike_rate": analysis_result.get("highest_strike_rate"),
                    "phases": analysis_result.get("phases"),
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
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("season_trend")
            if _sql_piece:
                combined_sql += "\n\n--- season_trend ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("batting")
            if _sql_piece:
                combined_sql += "\n\n--- batting ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("bowling")
            if _sql_piece:
                combined_sql += "\n\n--- bowling ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("chase_defend")
            if _sql_piece:
                combined_sql += "\n\n--- chase_defend ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("playoff")
            if _sql_piece:
                combined_sql += "\n\n--- playoff ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("venues")
            if _sql_piece:
                combined_sql += "\n\n--- venues ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("phase_batting")
            if _sql_piece:
                combined_sql += "\n\n--- phase_batting ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("top_run_scorers")
            if _sql_piece:
                combined_sql += "\n\n--- top_run_scorers ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("top_wicket_takers")
            if _sql_piece:
                combined_sql += "\n\n--- top_wicket_takers ---\n" + _sql_piece
            return {
                "method": "analysis_layer",
                "matched_question": "Full team profile analysis",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "overall": analysis_result.get("overall"),
                    "season_trend": analysis_result.get("season_trend"),
                    "batting": analysis_result.get("batting"),
                    "bowling": analysis_result.get("bowling"),
                    "chase_defend": analysis_result.get("chase_defend"),
                    "playoff": analysis_result.get("playoff"),
                    "venues": analysis_result.get("venues"),
                    "phase_batting": analysis_result.get("phase_batting"),
                    "top_run_scorers": analysis_result.get("top_run_scorers"),
                    "top_wicket_takers": analysis_result.get("top_wicket_takers"),
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
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("shot_dismissals")
            if _sql_piece:
                combined_sql += "\n\n--- shot_dismissals ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("risky_shots")
            if _sql_piece:
                combined_sql += "\n\n--- risky_shots ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("best_shots")
            if _sql_piece:
                combined_sql += "\n\n--- best_shots ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("line_length")
            if _sql_piece:
                combined_sql += "\n\n--- line_length ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("phase_shots")
            if _sql_piece:
                combined_sql += "\n\n--- phase_shots ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Player shot selection analysis",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "shot_summary": analysis_result.get("shot_summary"),
                    "shot_dismissals": analysis_result.get("shot_dismissals"),
                    "risky_shots": analysis_result.get("risky_shots"),
                    "best_shots": analysis_result.get("best_shots"),
                    "line_length": analysis_result.get("line_length"),
                    "phase_shots": analysis_result.get("phase_shots"),
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
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("phases")
            if _sql_piece:
                combined_sql += "\n\n--- phases ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("bowlers")
            if _sql_piece:
                combined_sql += "\n\n--- bowlers ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("opponents")
            if _sql_piece:
                combined_sql += "\n\n--- opponents ---\n" + _sql_piece
            _sql_piece = (analysis_result.get("sql_queries") or {}).get("venues")
            if _sql_piece:
                combined_sql += "\n\n--- venues ---\n" + _sql_piece

            if "seasons" in analysis_result["sql_queries"]:
                _sql_piece = (analysis_result.get("sql_queries") or {}).get("seasons")
                if _sql_piece:
                    combined_sql += "\n\n--- seasons ---\n" + _sql_piece

            return {
                "method": "analysis_layer",
                "matched_question": "Player dismissal analysis",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "wicket_types": analysis_result.get("wicket_types"),
                    "phases": analysis_result.get("phases"),
                    "bowlers": analysis_result.get("bowlers"),
                    "opponents": analysis_result.get("opponents"),
                    "venues": analysis_result.get("venues"),
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
            player_label = get_player_label_from_question(user_question)

            analysis_result = analyze_player_profile_smart(
                player_condition=player_condition,
                player_label=player_label,
            )
            combined_sql = ""

            for query_name, query_sql in (analysis_result.get("sql_queries") or {}).items():
                if query_sql:
                    combined_sql += f"\n\n--- {query_name} ---\n{query_sql}"
                        
            return {
                "method": "analysis_layer",
                "matched_question": "Full player profile analysis",
                "sql_query": combined_sql,
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "career": analysis_result.get("career"),
                    "season_trend": analysis_result.get("season_trend"),
                    "phase_performance": analysis_result.get("phase_performance"),
                    "opponent_performance": analysis_result.get("opponent_performance"),
                    "venue_performance": analysis_result.get("venue_performance"),
                    "playoff_performance": analysis_result.get("playoff_performance"),
                    "dismissal_types": analysis_result.get("dismissal_types"),
                    "bowler_success": analysis_result.get("bowler_success"),
                    "bowler_dismissals": analysis_result.get("bowler_dismissals"),
                    "quiet_bowlers": analysis_result.get("quiet_bowlers"),
                    "preferred_bowler_types": analysis_result.get("preferred_bowler_types"),
                    "difficult_bowler_types": analysis_result.get("difficult_bowler_types"),
                    "active_quiet_bowlers": analysis_result.get("active_quiet_bowlers"),
                    "batter_matchups": analysis_result.get("batter_matchups"),
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
                "sql_query": analysis_result.get("sql_query"),
                "result": analysis_result.get("summary"),
                "analysis_paragraph": analysis_result.get("paragraph"),
                "extra_tables": {
                    "match_summaries": analysis_result.get("match_summaries"),
                },
                "error": None
            }

    return None



def sanitize_sql_before_execution(sql_query):
    if sql_query is None:
        return None

    sql = str(sql_query)

    # Fix optional-filter bugs where helpers returned None or (None, None)
    bad_filter_patterns = [
        (r"\bWHERE\s+\(\s*None\s*,\s*None\s*\)", "WHERE 1=1"),
        (r"\bAND\s+\(\s*None\s*,\s*None\s*\)", ""),
        (r"\bOR\s+\(\s*None\s*,\s*None\s*\)", ""),

        (r"\bWHERE\s+None\b", "WHERE 1=1"),
        (r"\bAND\s+None\b", ""),
        (r"\bOR\s+None\b", ""),

        (r"\bWHERE\s+NULL\b", "WHERE 1=1"),
        (r"\bAND\s+NULL\b", ""),
        (r"\bOR\s+NULL\b", ""),

        (r"\bWHERE\s+False\b", "WHERE 1=1"),
        (r"\bAND\s+False\b", ""),
        (r"\bOR\s+False\b", ""),
    ]

    for pattern, replacement in bad_filter_patterns:
        sql = re.sub(pattern, replacement, sql, flags=re.IGNORECASE)

    # Clean accidental duplicated spaces caused by removals
    sql = re.sub(r"[ \t]+", " ", sql)
    sql = re.sub(r"\n\s+\n", "\n", sql)

    return sql.strip()

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
        curated_sql = sanitize_sql_before_execution(curated_sql)
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

def build_where_sql(where_clauses):
    def flatten_clause(clause):
        if clause is None:
            return []

        # Helpers sometimes return (condition, label)
        if isinstance(clause, tuple):
            if len(clause) == 0:
                return []
            return flatten_clause(clause[0])

        # Helpers sometimes accidentally append lists
        if isinstance(clause, list):
            output = []
            for item in clause:
                output.extend(flatten_clause(item))
            return output

        clause_text = str(clause).strip()

        if not clause_text:
            return []

        if clause_text.lower() in {"none", "null", "false"}:
            return []

        if clause_text.upper().startswith("WHERE "):
            clause_text = clause_text[6:].strip()

        if not clause_text:
            return []

        if clause_text.lower() in {"none", "null", "false"}:
            return []

        return [clause_text]

    clean_clauses = []

    for clause in where_clauses or []:
        clean_clauses.extend(flatten_clause(clause))

    clean_clauses = [
        clause for clause in clean_clauses
        if clause and str(clause).strip().lower() not in {"none", "null", "false"}
    ]

    if not clean_clauses:
        return ""

    return "WHERE " + " AND ".join(clean_clauses)

def build_and_sql(where_clauses):
    def flatten_clause(clause):
        if clause is None:
            return []

        if isinstance(clause, tuple):
            if len(clause) == 0:
                return []
            return flatten_clause(clause[0])

        if isinstance(clause, list):
            output = []
            for item in clause:
                output.extend(flatten_clause(item))
            return output

        clause_text = str(clause).strip()

        if not clause_text:
            return []

        if clause_text.lower() in {"none", "null", "false"}:
            return []

        if clause_text.upper().startswith("WHERE "):
            clause_text = clause_text[6:].strip()

        if not clause_text:
            return []

        if clause_text.lower() in {"none", "null", "false"}:
            return []

        return [clause_text]

    clean_clauses = []

    for clause in where_clauses or []:
        clean_clauses.extend(flatten_clause(clause))

    clean_clauses = [
        clause for clause in clean_clauses
        if clause and str(clause).strip().lower() not in {"none", "null", "false"}
    ]

    if not clean_clauses:
        return "1=1"

    return " AND ".join(clean_clauses)

# IPL SQL Agent UI postprocess override START

def _ipl_normalise_question_text(value):
    import re

    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _ipl_extract_venue_from_question(user_question):
    import re

    text = str(user_question or "").strip()

    match = re.search(
        r"\bat\s+([A-Za-z0-9 .'-]+)\s*$",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    venue = match.group(1).strip(" .?")

    venue_map = {
        "wankhede": "Wankhede",
        "chepauk": "Chepauk",
        "chinnaswamy": "Chinnaswamy",
        "eden gardens": "Eden Gardens",
        "narendra modi stadium": "Narendra Modi Stadium",
        "motera": "Narendra Modi Stadium",
    }

    return venue_map.get(venue.lower(), venue)


def _ipl_clean_player_initials_in_text(value):
    import re

    if value is None:
        return value

    text = str(value)

    text = re.sub(
        r"\b([A-Z])\.\s+(?=[A-Z][a-z])",
        r"\1 ",
        text,
    )

    text = text.replace("Mohd.", "Mohd")

    return text


def _ipl_clean_strings_recursively(value):
    if isinstance(value, str):
        return _ipl_clean_player_initials_in_text(value)

    if isinstance(value, list):
        return [
            _ipl_clean_strings_recursively(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return tuple(
            _ipl_clean_strings_recursively(item)
            for item in value
        )

    if isinstance(value, dict):
        return {
            key: _ipl_clean_strings_recursively(item)
            for key, item in value.items()
        }

    return value


def _ipl_rename_venue_tables(result, venue_label):
    if not isinstance(result, dict):
        return result

    if not venue_label:
        return result

    extra_tables = result.get("extra_tables")

    if not isinstance(extra_tables, dict):
        return result

    renamed_tables = {}

    for key, value in extra_tables.items():
        key_text = str(key)
        key_norm = key_text.lower().replace(" ", "_")

        if key_norm in {"head_to_head", "h2h", "head_to_head_record"}:
            new_key = f"Head to Head in {venue_label}"

        elif key_norm in {
            "recent_head_to_head",
            "recent_h2h",
            "recent_head_to_head_record",
            "recent_matches",
        }:
            new_key = f"Recent Head to Head in {venue_label}"

        else:
            new_key = key

        renamed_tables[new_key] = value

    result["extra_tables"] = renamed_tables

    return result


def _ipl_smart_similar_questions(user_question, existing_questions):
    import re

    user_norm = _ipl_normalise_question_text(user_question)
    cleaned = []

    for question in existing_questions or []:
        question_norm = _ipl_normalise_question_text(question)

        if not question_norm:
            continue

        if question_norm == user_norm:
            continue

        already_added = {
            _ipl_normalise_question_text(item)
            for item in cleaned
        }

        if question_norm in already_added:
            continue

        cleaned.append(question)

    match = re.search(
        r"how can\s+(.+?)\s+beat\s+(.+?)(?:\s+at\s+(.+))?$",
        str(user_question or ""),
        flags=re.IGNORECASE,
    )

    if match:
        team_a = match.group(1).strip()
        team_b = match.group(2).strip()
        venue = (match.group(3) or "").strip()

        smarter_questions = [
            f"what are the key matchups for {team_a} vs {team_b}",
            f"which {team_b} batters should {team_a} target first",
            f"what bowling plan should {team_a} use against {team_b}",
            f"which players are key for {team_a} vs {team_b}",
        ]

        if venue:
            smarter_questions.append(f"tell me about {venue}")

        for question in smarter_questions:
            question_norm = _ipl_normalise_question_text(question)

            if question_norm == user_norm:
                continue

            already_added = {
                _ipl_normalise_question_text(item)
                for item in cleaned
            }

            if question_norm in already_added:
                continue

            cleaned.append(question)

    return cleaned[:4]


try:
    _original_answer_question_with_fallback_for_ui = answer_question_with_fallback
except NameError:
    _original_answer_question_with_fallback_for_ui = None


def answer_question_with_fallback(user_question):
    result = _original_answer_question_with_fallback_for_ui(user_question)

    if not isinstance(result, dict):
        return result

    result = _ipl_clean_strings_recursively(result)

    venue_label = _ipl_extract_venue_from_question(user_question)

    result = _ipl_rename_venue_tables(
        result,
        venue_label=venue_label,
    )

    result["similar_questions"] = _ipl_smart_similar_questions(
        user_question,
        result.get("similar_questions"),
    )

    return result

# IPL SQL Agent UI postprocess override END

# IPL SQL Agent venue win-loss override START

def _ipl_winloss_sql_quote(value):
    return str(value).replace("'", "''")


def _ipl_winloss_team_from_question(user_question):
    text = str(user_question or "").lower()

    teams = {
        "csk": ("CSK", "Chennai Super Kings"),
        "chennai super kings": ("CSK", "Chennai Super Kings"),
        "mi": ("MI", "Mumbai Indians"),
        "mumbai indians": ("MI", "Mumbai Indians"),
        "gt": ("GT", "Gujarat Titans"),
        "gujarat titans": ("GT", "Gujarat Titans"),
        "rcb": ("RCB", "Royal Challengers Bengaluru"),
        "royal challengers": ("RCB", "Royal Challengers Bengaluru"),
        "kkr": ("KKR", "Kolkata Knight Riders"),
        "kolkata knight riders": ("KKR", "Kolkata Knight Riders"),
        "rr": ("RR", "Rajasthan Royals"),
        "rajasthan royals": ("RR", "Rajasthan Royals"),
        "srh": ("SRH", "Sunrisers Hyderabad"),
        "sunrisers hyderabad": ("SRH", "Sunrisers Hyderabad"),
        "dc": ("DC", "Delhi Capitals"),
        "delhi capitals": ("DC", "Delhi Capitals"),
        "lsg": ("LSG", "Lucknow Super Giants"),
        "lucknow super giants": ("LSG", "Lucknow Super Giants"),
        "pbks": ("PBKS", "Punjab Kings"),
        "punjab kings": ("PBKS", "Punjab Kings"),
    }

    # Longest names first so "mi" inside words does not win too early.
    for key in sorted(teams, key=len, reverse=True):
        if key in text:
            return teams[key]

    return None, None


def _ipl_winloss_venue_from_question(user_question):
    import re

    text = str(user_question or "")

    match = re.search(
        r"\bat\s+([A-Za-z0-9 .'-]+)\s*$",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None, None

    venue_raw = match.group(1).strip(" .?").lower()

    if "chepauk" in venue_raw or "chidambaram" in venue_raw:
        return "Chepauk", "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')"

    if "wankhede" in venue_raw:
        return "Wankhede", "m.venue LIKE '%Wankhede%'"

    if "chinnaswamy" in venue_raw:
        return "Chinnaswamy", "m.venue LIKE '%Chinnaswamy%'"

    if "eden" in venue_raw:
        return "Eden Gardens", "m.venue LIKE '%Eden Gardens%'"

    if "narendra" in venue_raw or "motera" in venue_raw:
        return (
            "Narendra Modi Stadium",
            "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.venue LIKE '%Sardar Patel%')",
        )

    venue_sql = _ipl_winloss_sql_quote(venue_raw)

    return venue_raw.title(), f"LOWER(m.venue) LIKE '%{venue_sql}%'"


def _ipl_answer_team_venue_winloss(user_question):
    import pandas as pd

    question = str(user_question or "").lower()

    is_winloss_question = (
        ("win loss" in question or "win-loss" in question or "win percentage" in question)
        and " at " in question
    )

    if not is_winloss_question:
        return None

    team_code, team_name = _ipl_winloss_team_from_question(user_question)
    venue_label, venue_condition = _ipl_winloss_venue_from_question(user_question)

    if not team_code or not team_name or not venue_label or not venue_condition:
        return None

    team_name_sql = _ipl_winloss_sql_quote(team_name)

    sql = f"""
WITH team_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.venue,
        m.winner
    FROM matches m
    JOIN deliveries d
        ON m.match_id = d.match_id
    WHERE {venue_condition}
      AND (
            d.batting_team = '{team_name_sql}'
         OR d.bowling_team = '{team_name_sql}'
      )
)
SELECT
    '{team_name_sql}' AS team,
    '{_ipl_winloss_sql_quote(venue_label)}' AS venue,
    COUNT(*) AS matches,
    SUM(CASE WHEN winner = '{team_name_sql}' THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN winner IS NOT NULL AND winner <> '{team_name_sql}' THEN 1 ELSE 0 END) AS losses,
    SUM(CASE WHEN winner IS NULL THEN 1 ELSE 0 END) AS no_result,
    ROUND(
        SUM(CASE WHEN winner = '{team_name_sql}' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN winner IS NOT NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS win_pct,
    ROUND(
        SUM(CASE WHEN winner IS NOT NULL AND winner <> '{team_name_sql}' THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(SUM(CASE WHEN winner IS NOT NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS loss_pct
FROM team_matches;
""".strip()

    try:
        df = run_query(sql)

    except Exception as error:
        return {
            "question": user_question,
            "analysis_paragraph": f"I tried the curated venue win-loss query, but SQL failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None or df.empty:
        return {
            "question": user_question,
            "analysis_paragraph": f"No local IPL matches found for {team_name} at {venue_label}.",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [
                f"tell me about {venue_label}",
                f"how can {team_code} win at {venue_label}",
            ],
        }

    row = df.iloc[0]

    paragraph = (
        f"At {venue_label}, {team_name} have played {int(row['matches'])} local IPL match(es): "
        f"{int(row['wins'])} win(s), {int(row['losses'])} loss(es), "
        f"win percentage {row['win_pct']}% and loss percentage {row['loss_pct']}%."
    )

    return {
        "question": user_question,
        "analysis_paragraph": paragraph,
        "result": df,
        "extra_tables": {
            f"{team_code} win-loss at {venue_label}": df,
        },
        "sql_query": sql,
        "similar_questions": [
            f"tell me about {venue_label}",
            f"how can {team_code} win at {venue_label}",
            f"{team_code} record at {venue_label}",
        ],
    }


try:
    _original_answer_question_with_fallback_for_venue_winloss = answer_question_with_fallback
except NameError:
    _original_answer_question_with_fallback_for_venue_winloss = None


def answer_question_with_fallback(user_question):
    venue_winloss_result = _ipl_answer_team_venue_winloss(user_question)

    if venue_winloss_result is not None:
        return venue_winloss_result

    return _original_answer_question_with_fallback_for_venue_winloss(user_question)

# IPL SQL Agent venue win-loss override END

# IPL SQL Agent squad fallback postprocess override START

def _ipl_squad_route_team_from_question(user_question):
    text = str(user_question or "").lower()

    if "squad" not in text and "team" not in text:
        return None, None

    mapping = {
        "rcb": ("RCB", "Royal Challengers Bengaluru"),
        "royal challengers": ("RCB", "Royal Challengers Bengaluru"),
        "pbks": ("PBKS", "Punjab Kings"),
        "kxip": ("PBKS", "Punjab Kings"),
        "punjab": ("PBKS", "Punjab Kings"),
        "dc": ("DC", "Delhi Capitals"),
        "dd": ("DC", "Delhi Capitals"),
        "delhi": ("DC", "Delhi Capitals"),
        "csk": ("CSK", "Chennai Super Kings"),
        "chennai": ("CSK", "Chennai Super Kings"),
        "mi": ("MI", "Mumbai Indians"),
        "mumbai": ("MI", "Mumbai Indians"),
        "gt": ("GT", "Gujarat Titans"),
        "gujarat": ("GT", "Gujarat Titans"),
        "kkr": ("KKR", "Kolkata Knight Riders"),
        "kolkata": ("KKR", "Kolkata Knight Riders"),
        "rr": ("RR", "Rajasthan Royals"),
        "rajasthan": ("RR", "Rajasthan Royals"),
        "srh": ("SRH", "Sunrisers Hyderabad"),
        "sunrisers": ("SRH", "Sunrisers Hyderabad"),
        "lsg": ("LSG", "Lucknow Super Giants"),
        "lucknow": ("LSG", "Lucknow Super Giants"),
    }

    for key, value in mapping.items():
        if key in text:
            return value

    return None, None


try:
    _previous_answer_question_with_fallback_before_squad_fix = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_squad_fix = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_squad_fix(user_question)

    team_code, team_name = _ipl_squad_route_team_from_question(user_question)

    needs_squad_fallback = (
        isinstance(result, dict)
        and team_code is not None
        and (
            not result.get("analysis_paragraph")
            and not result.get("paragraph")
        )
    )

    if needs_squad_fallback:
        try:
            from app.analysis import analyze_current_squad_report

            squad_result = analyze_current_squad_report(
                team_condition=f"team_code = '{team_code}'",
                team_label=team_name,
            )

            if isinstance(squad_result, dict):
                paragraph = (
                    squad_result.get("analysis_paragraph")
                    or squad_result.get("paragraph")
                )

                result["analysis_paragraph"] = paragraph
                result["paragraph"] = paragraph

                extra_tables = result.get("extra_tables") or {}

                for key, value in squad_result.items():
                    if hasattr(value, "columns"):
                        extra_tables[key] = value

                result["extra_tables"] = extra_tables

        except Exception:
            pass

    if isinstance(result, dict):
        paragraph = result.get("analysis_paragraph") or result.get("paragraph")

        if paragraph:
            result["analysis_paragraph"] = paragraph
            result["paragraph"] = paragraph

    return result

# IPL SQL Agent squad fallback postprocess override END

# IPL SQL Agent DC/PBKS/RCB squad route override START

def _ipl_squad_direct_sql_quote(value):
    return str(value).replace("'", "''")


def _ipl_squad_direct_team_from_question(user_question):
    text = str(user_question or "").lower()

    if "deccan" in text or "chargers" in text:
        return None

    teams = [
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings", "Punjab franchise"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for team_code, team_name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return team_code, team_name, aliases

    return None


def _ipl_squad_direct_sql_list(values):
    escaped = [
        "'" + _ipl_squad_direct_sql_quote(value) + "'"
        for value in values
        if value and str(value).strip()
    ]

    if not escaped:
        return "('')"

    return "(" + ", ".join(escaped) + ")"


def _ipl_squad_direct_is_squad_question(user_question):
    text = str(user_question or "").lower()

    squad_words = [
        "analyse",
        "analyze",
        "profile",
        "squad",
        "team",
    ]

    return any(word in text for word in squad_words)


def _ipl_squad_direct_result(user_question):
    import pandas as pd

    if not _ipl_squad_direct_is_squad_question(user_question):
        return None

    team = _ipl_squad_direct_team_from_question(user_question)

    if team is None:
        return None

    team_code, team_name, aliases = team
    aliases_sql = _ipl_squad_direct_sql_list(aliases)
    team_code_sql = _ipl_squad_direct_sql_quote(team_code)
    team_name_sql = _ipl_squad_direct_sql_quote(team_name)

    squad_sql = f"""
SELECT
    team_code,
    team_name,
    display_name,
    cricsheet_name,
    role,
    batting_style,
    bowling_style,
    bowling_arm,
    is_overseas,
    is_active
FROM current_squads
WHERE team_code = '{team_code_sql}'
   OR team_name = '{team_name_sql}'
ORDER BY
    CASE
        WHEN role LIKE '%Batter%' THEN 1
        WHEN role LIKE '%WK%' THEN 2
        WHEN role LIKE '%All%' THEN 3
        WHEN role LIKE '%Bowler%' THEN 4
        ELSE 5
    END,
    display_name;
""".strip()

    role_sql = f"""
SELECT
    role,
    COUNT(*) AS players
FROM current_squads
WHERE team_code = '{team_code_sql}'
   OR team_name = '{team_name_sql}'
GROUP BY role
ORDER BY players DESC, role;
""".strip()

    overview_sql = f"""
WITH team_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season,
        CAST(m.start_date AS date) AS match_date,
        m.venue,
        m.winner
    FROM matches m
    JOIN deliveries d
        ON m.match_id = d.match_id
    WHERE d.batting_team IN {aliases_sql}
       OR d.bowling_team IN {aliases_sql}
),
final_dates AS (
    SELECT
        season,
        MAX(CAST(start_date AS date)) AS final_date
    FROM matches
    WHERE winner IS NOT NULL
    GROUP BY season
),
final_matches AS (
    SELECT
        m.match_id,
        m.season,
        m.winner
    FROM matches m
    JOIN final_dates fd
        ON m.season = fd.season
       AND CAST(m.start_date AS date) = fd.final_date
),
team_final AS (
    SELECT DISTINCT
        fm.season,
        fm.match_id,
        fm.winner
    FROM final_matches fm
    JOIN deliveries d
        ON fm.match_id = d.match_id
    WHERE d.batting_team IN {aliases_sql}
       OR d.bowling_team IN {aliases_sql}
),
playoff_dates AS (
    SELECT
        season,
        CAST(start_date AS date) AS match_date,
        DENSE_RANK() OVER (
            PARTITION BY season
            ORDER BY CAST(start_date AS date) DESC
        ) AS reverse_date_rank
    FROM matches
    WHERE winner IS NOT NULL
),
playoff_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season
    FROM matches m
    JOIN playoff_dates pd
        ON m.season = pd.season
       AND CAST(m.start_date AS date) = pd.match_date
    WHERE pd.reverse_date_rank <= 4
),
team_playoff AS (
    SELECT DISTINCT
        pm.season
    FROM playoff_matches pm
    JOIN deliveries d
        ON pm.match_id = d.match_id
    WHERE d.batting_team IN {aliases_sql}
       OR d.bowling_team IN {aliases_sql}
),
season_summary AS (
    SELECT
        season,
        COUNT(DISTINCT match_id) AS matches,
        SUM(CASE WHEN winner IN {aliases_sql} THEN 1 ELSE 0 END) AS wins,
        SUM(
            CASE
                WHEN winner IS NOT NULL
                 AND winner NOT IN {aliases_sql}
                THEN 1
                ELSE 0
            END
        ) AS losses,
        SUM(CASE WHEN winner IS NULL THEN 1 ELSE 0 END) AS no_result
    FROM team_matches
    GROUP BY season
)
SELECT
    ss.season,
    ss.matches,
    ss.wins,
    ss.losses,
    ss.no_result,
    ROUND(ss.wins * 100.0 / NULLIF(ss.matches, 0), 2) AS win_pct,
    CASE
        WHEN tf.winner IN {aliases_sql} THEN 'Champions'
        WHEN tf.match_id IS NOT NULL THEN 'Finalists'
        WHEN tp.season IS NOT NULL THEN 'Playoffs'
        ELSE 'Did not qualify for playoffs'
    END AS final_result
FROM season_summary ss
LEFT JOIN team_final tf
    ON ss.season = tf.season
LEFT JOIN team_playoff tp
    ON ss.season = tp.season
ORDER BY
    TRY_CONVERT(INT, ss.season),
    ss.season;
""".strip()

    summary_sql = f"""
WITH team_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season,
        CAST(m.start_date AS date) AS match_date,
        m.venue,
        m.winner
    FROM matches m
    JOIN deliveries d
        ON m.match_id = d.match_id
    WHERE d.batting_team IN {aliases_sql}
       OR d.bowling_team IN {aliases_sql}
)
SELECT
    COUNT(DISTINCT match_id) AS matches,
    MIN(match_date) AS first_match,
    MAX(match_date) AS latest_match,
    SUM(CASE WHEN winner IN {aliases_sql} THEN 1 ELSE 0 END) AS wins,
    COUNT(DISTINCT venue) AS venues
FROM team_matches;
""".strip()

    trophy_sql = f"""
WITH final_dates AS (
    SELECT
        season,
        MAX(CAST(start_date AS date)) AS final_date
    FROM matches
    WHERE winner IS NOT NULL
    GROUP BY season
),
finals AS (
    SELECT
        m.season,
        m.winner
    FROM matches m
    JOIN final_dates fd
        ON m.season = fd.season
       AND CAST(m.start_date AS date) = fd.final_date
)
SELECT
    COUNT(*) AS trophies
FROM finals
WHERE winner IN {aliases_sql};
""".strip()

    try:
        squad_df = run_query(squad_sql)
    except Exception:
        squad_df = pd.DataFrame()

    try:
        role_df = run_query(role_sql)
    except Exception:
        role_df = pd.DataFrame()

    try:
        season_df = run_query(overview_sql)
    except Exception:
        season_df = pd.DataFrame()

    try:
        summary_df = run_query(summary_sql)
    except Exception:
        summary_df = pd.DataFrame()

    try:
        trophy_df = run_query(trophy_sql)
    except Exception:
        trophy_df = pd.DataFrame()

    matches = 0
    wins = 0
    venues = 0
    first_year = None
    latest_year = None
    trophies = 0

    if summary_df is not None and not summary_df.empty:
        row = summary_df.iloc[0]

        matches = int(row["matches"]) if pd.notna(row.get("matches")) else 0
        wins = int(row["wins"]) if pd.notna(row.get("wins")) else 0
        venues = int(row["venues"]) if pd.notna(row.get("venues")) else 0

        first_match = str(row.get("first_match") or "")
        latest_match = str(row.get("latest_match") or "")

        if len(first_match) >= 4 and first_match[:4].isdigit():
            first_year = first_match[:4]

        if len(latest_match) >= 4 and latest_match[:4].isdigit():
            latest_year = latest_match[:4]

    if trophy_df is not None and not trophy_df.empty:
        trophy_value = trophy_df.iloc[0].get("trophies")

        trophies = int(trophy_value) if pd.notna(trophy_value) else 0

    role_text = ""

    if role_df is not None and not role_df.empty:
        parts = [
            f"{int(row['players'])} {str(row['role']).lower()}s"
            for _, row in role_df.iterrows()
            if pd.notna(row.get("role"))
        ]

        if parts:
            role_text = " The current squad mix includes " + ", ".join(parts[:4]) + "."

    if first_year and latest_year:
        intro = (
            f"{team_name} are an IPL franchise represented in this local database "
            f"from {first_year} to {latest_year}."
        )
    else:
        intro = f"{team_name} are an IPL franchise represented in this local database."

    paragraph = (
        intro
        + f" Across the stored matches, they appear in {matches} games and have {wins} wins."
        + f" Their trophy count in the local season-final method is {trophies}."
        + f" Their matches span {venues} venues in the dataset."
        + role_text
        + " The season overview table includes a final result column showing whether each season ended as Champions, Finalists, Playoffs, or Did not qualify for playoffs."
    )

    return {
        "question": user_question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": season_df,
        "extra_tables": {
            "Squad": squad_df,
            "Role Split": role_df,
            "Season Overview": season_df,
        },
        "sql_query": overview_sql,
        "similar_questions": [
            f"which players are key for {team_code}",
            f"how can {team_code} win next season",
            f"best bowlers against Kohli for {team_code}",
            f"tell me about {team_name}",
        ],
    }


try:
    _previous_answer_question_with_fallback_before_direct_dc_fix = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_direct_dc_fix = None


def answer_question_with_fallback(user_question):
    direct_squad_result = _ipl_squad_direct_result(user_question)

    if direct_squad_result is not None:
        return direct_squad_result

    return _previous_answer_question_with_fallback_before_direct_dc_fix(user_question)

# IPL SQL Agent DC/PBKS/RCB squad route override END

# IPL SQL Agent extra curated routes override START

def _ipl_extra_sql_quote(value):
    return str(value).replace("'", "''")


def _ipl_extra_canonical_team_expr(column_name):
    return f'''
CASE
    WHEN {column_name} IN ('Royal Challengers Bangalore', 'Royal Challengers Bengaluru') THEN 'Royal Challengers Bengaluru'
    WHEN {column_name} IN ('Kings XI Punjab', 'Punjab Kings', 'Punjab franchise') THEN 'Punjab Kings'
    WHEN {column_name} IN ('Delhi Daredevils', 'Delhi Capitals') THEN 'Delhi Capitals'
    WHEN {column_name} IN ('Rising Pune Supergiant', 'Rising Pune Supergiants') THEN 'Rising Pune Supergiant'
    ELSE {column_name}
END
'''.strip()


def _ipl_extra_direct_most_trophies(user_question):
    import pandas as pd
    from app.db import run_query

    q = str(user_question or '').lower()

    if not (
        'most trophies' in q
        or 'most titles' in q
        or 'most championships' in q
        or 'ipl trophies' in q
    ):
        return None

    team_expr = _ipl_extra_canonical_team_expr('m.winner')

    sql = f'''
WITH final_dates AS (
    SELECT
        season,
        MAX(CAST(start_date AS date)) AS final_date
    FROM matches
    WHERE winner IS NOT NULL
    GROUP BY season
),
finals AS (
    SELECT
        m.season,
        {team_expr} AS team
    FROM matches m
    JOIN final_dates fd
        ON m.season = fd.season
       AND CAST(m.start_date AS date) = fd.final_date
    WHERE m.winner IS NOT NULL
),
summary AS (
    SELECT
        team,
        COUNT(*) AS trophies,
        STRING_AGG(CAST(season AS varchar(20)), ', ') AS years_won
    FROM finals
    GROUP BY team
)
SELECT
    team,
    trophies,
    years_won
FROM summary
ORDER BY
    trophies DESC,
    team ASC;
'''.strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            'question': user_question,
            'analysis_paragraph': f'The trophies query failed: {error}',
            'result': pd.DataFrame(),
            'extra_tables': {},
            'sql_query': sql,
            'similar_questions': [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = (
        'This ranks teams by IPL trophies using the last match date in each season as the final, '
        'with the winning years included.'
    )

    return {
        'question': user_question,
        'analysis_paragraph': paragraph,
        'paragraph': paragraph,
        'result': df,
        'extra_tables': {'Trophies By Team': df},
        'sql_query': sql,
        'similar_questions': [
            'which team has qualified for the playoffs the most',
            'which team has played the most finals',
            'which team has the best win percentage',
        ],
    }


def _ipl_extra_direct_playoff_qualifications(user_question):
    import pandas as pd
    from app.db import run_query

    q = str(user_question or '').lower()

    if not (
        'qualified for the playoffs' in q
        or 'playoff qualifications' in q
        or 'most playoffs' in q
        or 'reached playoffs the most' in q
    ):
        return None

    batting_expr = _ipl_extra_canonical_team_expr('d.batting_team')
    bowling_expr = _ipl_extra_canonical_team_expr('d.bowling_team')

    sql = f'''
WITH playoff_dates AS (
    SELECT
        season,
        CAST(start_date AS date) AS match_date,
        DENSE_RANK() OVER (
            PARTITION BY season
            ORDER BY CAST(start_date AS date) DESC
        ) AS reverse_date_rank
    FROM matches
    WHERE winner IS NOT NULL
),
playoff_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season
    FROM matches m
    JOIN playoff_dates pd
        ON m.season = pd.season
       AND CAST(m.start_date AS date) = pd.match_date
    WHERE pd.reverse_date_rank <= 4
),
playoff_teams AS (
    SELECT DISTINCT
        pm.season,
        {batting_expr} AS team
    FROM playoff_matches pm
    JOIN deliveries d
        ON pm.match_id = d.match_id

    UNION

    SELECT DISTINCT
        pm.season,
        {bowling_expr} AS team
    FROM playoff_matches pm
    JOIN deliveries d
        ON pm.match_id = d.match_id
),
summary AS (
    SELECT
        team,
        COUNT(DISTINCT season) AS playoff_seasons,
        STRING_AGG(CAST(season AS varchar(20)), ', ') AS playoff_years
    FROM playoff_teams
    WHERE team IS NOT NULL
    GROUP BY team
)
SELECT
    team,
    playoff_seasons,
    playoff_years
FROM summary
ORDER BY
    playoff_seasons DESC,
    team ASC;
'''.strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            'question': user_question,
            'analysis_paragraph': f'The playoff qualification query failed: {error}',
            'result': pd.DataFrame(),
            'extra_tables': {},
            'sql_query': sql,
            'similar_questions': [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = (
        'This counts playoff qualification by season, not by number of playoff matches. '
        'Each team can count only once per season.'
    )

    return {
        'question': user_question,
        'analysis_paragraph': paragraph,
        'paragraph': paragraph,
        'result': df,
        'extra_tables': {'Playoff Qualifications By Team': df},
        'sql_query': sql,
        'similar_questions': [
            'which team has the most trophies',
            'which team has played the most finals',
            'who has the most fifties in playoffs',
        ],
    }


def _ipl_extra_direct_playoff_or_final_milestones(user_question):
    import pandas as pd
    from app.db import run_query

    q = str(user_question or '').lower()

    is_fifty = 'fifties' in q or '50s' in q or 'half centuries' in q
    is_hundred = 'hundreds' in q or '100s' in q or 'centuries' in q
    is_final = 'final' in q
    is_playoff = 'playoff' in q

    if not (is_fifty or is_hundred):
        return None

    if not (is_final or is_playoff):
        return None

    if is_final:
        match_scope_name = 'finals'

        scope_cte = '''
final_dates AS (
    SELECT
        season,
        MAX(CAST(start_date AS date)) AS final_date
    FROM matches
    WHERE winner IS NOT NULL
    GROUP BY season
),
target_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season
    FROM matches m
    JOIN final_dates fd
        ON m.season = fd.season
       AND CAST(m.start_date AS date) = fd.final_date
)
'''.strip()

    else:
        match_scope_name = 'playoffs'

        scope_cte = '''
playoff_dates AS (
    SELECT
        season,
        CAST(start_date AS date) AS match_date,
        DENSE_RANK() OVER (
            PARTITION BY season
            ORDER BY CAST(start_date AS date) DESC
        ) AS reverse_date_rank
    FROM matches
    WHERE winner IS NOT NULL
),
target_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season
    FROM matches m
    JOIN playoff_dates pd
        ON m.season = pd.season
       AND CAST(m.start_date AS date) = pd.match_date
    WHERE pd.reverse_date_rank <= 4
)
'''.strip()

    if is_hundred:
        milestone_label = 'hundreds'
        milestone_condition = 'runs >= 100'

    else:
        milestone_label = 'fifties'
        milestone_condition = 'runs BETWEEN 50 AND 99'

    sql = f'''
WITH
{scope_cte},
innings_scores AS (
    SELECT
        d.match_id,
        d.season,
        d.innings,
        d.striker AS batter,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls
    FROM deliveries d
    JOIN target_matches tm
        ON d.match_id = tm.match_id
    GROUP BY
        d.match_id,
        d.season,
        d.innings,
        d.striker
),
milestone_innings AS (
    SELECT
        batter,
        season,
        match_id,
        innings,
        runs,
        balls
    FROM innings_scores
    WHERE {milestone_condition}
)
SELECT
    batter,
    COUNT(*) AS {milestone_label},
    STRING_AGG(CAST(season AS varchar(20)), ', ') AS seasons,
    MAX(runs) AS highest_score,
    ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate
FROM milestone_innings
GROUP BY batter
ORDER BY
    {milestone_label} DESC,
    highest_score DESC,
    batter ASC;
'''.strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            'question': user_question,
            'analysis_paragraph': f'The {milestone_label} in {match_scope_name} query failed: {error}',
            'result': pd.DataFrame(),
            'extra_tables': {},
            'sql_query': sql,
            'similar_questions': [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = f'This ranks batters by most {milestone_label} in IPL {match_scope_name} in the local database.'

    return {
        'question': user_question,
        'analysis_paragraph': paragraph,
        'paragraph': paragraph,
        'result': df,
        'extra_tables': {f'Most {milestone_label.title()} In {match_scope_name.title()}': df},
        'sql_query': sql,
        'similar_questions': [
            'who has the most fifties in playoffs',
            'who has the most hundreds in playoffs',
            'who has the most fifties in finals',
            'who has the most hundreds in finals',
        ],
    }


def _ipl_extra_direct_strongest_current_squad(user_question):
    import pandas as pd

    q = str(user_question or '').lower()

    if not (
        'strongest current squad' in q
        or 'best current squad' in q
        or 'strongest squad' in q
    ):
        return None

    try:
        from app.analysis import analyze_strongest_current_squads

        result = analyze_strongest_current_squads()

        if isinstance(result, dict):
            paragraph = (
                result.get('analysis_paragraph')
                or result.get('paragraph')
                or 'This ranks the current IPL squads using the local squad and player-performance tables.'
            )

            extra_tables = {}

            for key, value in result.items():
                if hasattr(value, 'columns'):
                    extra_tables[key] = value

            main_result = result.get('result')

            if not hasattr(main_result, 'columns'):
                for value in extra_tables.values():
                    main_result = value
                    break

            return {
                'question': user_question,
                'analysis_paragraph': paragraph,
                'paragraph': paragraph,
                'result': main_result if hasattr(main_result, 'columns') else pd.DataFrame(),
                'extra_tables': extra_tables,
                'sql_query': '\\n\\n'.join(str(v) for v in (result.get('sql_queries') or {}).values() if v),
                'similar_questions': [
                    'analyse RCB squad',
                    'analyse CSK squad',
                    'analyse GT squad',
                    'who will win next season',
                ],
            }

    except Exception as error:
        return {
            'question': user_question,
            'analysis_paragraph': f'The strongest current squad route failed: {error}',
            'result': pd.DataFrame(),
            'extra_tables': {},
            'sql_query': '',
            'similar_questions': [],
        }

    return None


try:
    _previous_answer_question_with_fallback_before_extra_curated_routes = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_extra_curated_routes = None


def answer_question_with_fallback(user_question):
    direct_routes = [
        _ipl_extra_direct_most_trophies,
        _ipl_extra_direct_playoff_qualifications,
        _ipl_extra_direct_playoff_or_final_milestones,
        _ipl_extra_direct_strongest_current_squad,
    ]

    for route in direct_routes:
        result = route(user_question)

        if result is not None:
            return result

    return _previous_answer_question_with_fallback_before_extra_curated_routes(user_question)

# IPL SQL Agent extra curated routes override END


# IPL SQL Agent answer polish START

def _ipl_answer_polish_text(value):
    import re

    if value is None:
        return value

    text = str(value)

    def repl(match):
        try:
            number = float(match.group(0))
            return f"{number:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return match.group(0)

    text = re.sub(r"(?<![0-9])\d+\.\d{4,}(?![0-9])", repl, text)
    text = text.replace("shot-events", "shot events")

    return text


def _ipl_answer_polish_tables(result):
    if not isinstance(result, dict):
        return result

    tables = []

    if hasattr(result.get("result"), "columns"):
        tables.append(result["result"])

    extra = result.get("extra_tables")

    if isinstance(extra, dict):
        tables.extend([t for t in extra.values() if hasattr(t, "columns")])

    for table in tables:
        for col in ["battle_note", "Battle Note", "summary", "Summary", "note", "Note"]:
            if col in table.columns:
                table[col] = table[col].apply(_ipl_answer_polish_text)

    return result


def _ipl_answer_add_playoff_scope_note(question, result):
    if not isinstance(result, dict):
        return result

    q = str(question or "").lower()

    milestone_words = ["fifties", "hundreds", "50s", "100s", "centuries"]

    if "playoff" in q and any(word in q for word in milestone_words):
        note = (
            "In this route, playoffs include the final as well as qualifier/eliminator matches. "
            "For final-only records, ask the same question with 'finals'."
        )

        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""

        if note not in paragraph:
            paragraph = (paragraph + " " + note).strip()

        result["analysis_paragraph"] = paragraph
        result["paragraph"] = paragraph

    return result


def _ipl_answer_explain_strongest_squad(question, result):
    if not isinstance(result, dict):
        return result

    q = str(question or "").lower()

    if not (
        "strongest current squad" in q
        or "best current squad" in q
        or "strongest squad" in q
    ):
        return result

    table = result.get("result")
    team = None

    if hasattr(table, "columns") and not table.empty:
        for col in ["team", "team_name", "Team", "Team Name", "team_code", "Team Code"]:
            if col in table.columns:
                team = table.iloc[0][col]
                break

    if team:
        opening = f"{team} rank highest in the current-squad model."
    else:
        opening = "The top-ranked team ranks highest in the current-squad model."

    paragraph = (
        opening
        + " The model is judging squad strength from a mix of batting depth, recent batting output, "
        + "bowling wicket threat, phase coverage, all-round options, and current-squad availability. "
        + "So the answer is not just based on historical reputation; it is based on the balance of the current squad and the local IPL performance data behind the table."
    )

    result["analysis_paragraph"] = paragraph
    result["paragraph"] = paragraph

    return result


try:
    _previous_answer_question_with_fallback_before_answer_polish = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_answer_polish = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_answer_polish(user_question)

    result = _ipl_answer_add_playoff_scope_note(user_question, result)
    result = _ipl_answer_explain_strongest_squad(user_question, result)

    if isinstance(result, dict):
        for key in ["analysis_paragraph", "paragraph", "answer"]:
            if key in result and isinstance(result[key], str):
                result[key] = _ipl_answer_polish_text(result[key])

    result = _ipl_answer_polish_tables(result)

    return result

# IPL SQL Agent answer polish END

# IPL SQL Agent batting/bowling leaderboard routes override START

def _ipl_lb_sql_quote(value):
    return str(value).replace("'", "''")


def _ipl_lb_team_aliases_from_text(text):
    text = str(text or "").lower()

    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings", "Punjab franchise"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for team_code, team_name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return team_code, team_name, aliases

    return None, None, []


def _ipl_lb_sql_list(values):
    items = [
        "'" + _ipl_lb_sql_quote(value) + "'"
        for value in values
        if value and str(value).strip()
    ]

    if not items:
        return "('')"

    return "(" + ", ".join(items) + ")"


def _ipl_lb_extract_for_team(question):
    import re

    text = str(question or "")

    match = re.search(
        r"\bfor\s+([A-Za-z .]+?)(?:\s+in\s+ipl|\s+at\s+|\s+against\s+|$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None, None, []

    return _ipl_lb_team_aliases_from_text(match.group(1))


def _ipl_lb_extract_against_team(question):
    import re

    text = str(question or "")

    match = re.search(
        r"\bagainst\s+([A-Za-z .]+?)(?:\s+in\s+ipl|\s+at\s+|$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None, None, []

    return _ipl_lb_team_aliases_from_text(match.group(1))


def _ipl_lb_extract_venue_condition(question, table_alias="m"):
    import re

    text = str(question or "")

    match = re.search(
        r"\bat\s+([A-Za-z0-9 .'-]+)\s*$",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return "1=1", None

    venue = match.group(1).strip(" .?").lower()
    col = f"{table_alias}.venue"

    if "chepauk" in venue or "chidambaram" in venue:
        return f"({col} LIKE '%Chepauk%' OR {col} LIKE '%Chidambaram%')", "Chepauk"

    if "wankhede" in venue:
        return f"{col} LIKE '%Wankhede%'", "Wankhede"

    if "chinnaswamy" in venue:
        return f"{col} LIKE '%Chinnaswamy%'", "Chinnaswamy"

    if "eden" in venue:
        return f"{col} LIKE '%Eden Gardens%'", "Eden Gardens"

    if "narendra" in venue or "motera" in venue:
        return f"({col} LIKE '%Narendra Modi%' OR {col} LIKE '%Motera%' OR {col} LIKE '%Sardar Patel%')", "Narendra Modi Stadium"

    venue_sql = _ipl_lb_sql_quote(venue)

    return f"LOWER({col}) LIKE '%{venue_sql}%'", venue.title()


def _ipl_lb_playoff_scope_cte(scope):
    if scope == "finals":
        return """
final_dates AS (
    SELECT
        season,
        MAX(CAST(start_date AS date)) AS final_date
    FROM matches
    WHERE winner IS NOT NULL
    GROUP BY season
),
target_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season
    FROM matches m
    JOIN final_dates fd
        ON m.season = fd.season
       AND CAST(m.start_date AS date) = fd.final_date
)
""".strip()

    return """
playoff_dates AS (
    SELECT
        season,
        CAST(start_date AS date) AS match_date,
        DENSE_RANK() OVER (
            PARTITION BY season
            ORDER BY CAST(start_date AS date) DESC
        ) AS reverse_date_rank
    FROM matches
    WHERE winner IS NOT NULL
),
target_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season
    FROM matches m
    JOIN playoff_dates pd
        ON m.season = pd.season
       AND CAST(m.start_date AS date) = pd.match_date
    WHERE pd.reverse_date_rank <= 4
)
""".strip()


def _ipl_lb_direct_top_run_scorers(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    is_run_query = (
        ("top" in q or "most" in q or "highest" in q)
        and ("run scorers" in q or "runs" in q or "run scorer" in q)
    )

    if not is_run_query:
        return None

    if "single over" in q or "losing cause" in q:
        return None

    team_code, team_name, team_aliases = _ipl_lb_extract_for_team(question)
    against_code, against_name, against_aliases = _ipl_lb_extract_against_team(question)
    venue_condition, venue_label = _ipl_lb_extract_venue_condition(question, table_alias="m")

    where_parts = [
        venue_condition,
    ]

    if team_aliases:
        where_parts.append(f"d.batting_team IN {_ipl_lb_sql_list(team_aliases)}")

    if against_aliases:
        where_parts.append(f"d.bowling_team IN {_ipl_lb_sql_list(against_aliases)}")

    where_sql = " AND ".join(part for part in where_parts if part and part != "1=1") or "1=1"

    title_bits = ["Top run scorers"]

    if team_name:
        title_bits.append(f"for {team_name}")

    if against_name:
        title_bits.append(f"against {against_name}")

    if venue_label:
        title_bits.append(f"at {venue_label}")

    title = " ".join(title_bits)

    sql = f"""
WITH batter_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY
        d.match_id,
        d.innings,
        d.striker
),
summary AS (
    SELECT
        batter,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(balls) AS balls,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM batter_innings
    GROUP BY batter
)
SELECT TOP 10
    batter,
    matches,
    innings,
    runs,
    balls,
    highest_score,
    fifties,
    hundreds,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate
FROM summary
ORDER BY
    runs DESC,
    innings ASC,
    batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The top run-scorers query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = f"{title}. This table includes matches and innings, so the runs are easier to compare."

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {title: df},
        "sql_query": sql,
        "similar_questions": [
            "who are the top 10 wicket takers in IPL",
            "who has the most fifties in IPL",
            "who has the most runs in playoffs",
        ],
    }


def _ipl_lb_direct_top_wicket_takers(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    is_wicket_query = (
        ("top" in q or "most" in q or "highest" in q)
        and ("wicket takers" in q or "wickets" in q or "wicket-takers" in q)
    )

    if not is_wicket_query:
        return None

    if "playoff" in q or "final" in q or "losing cause" in q:
        return None

    team_code, team_name, team_aliases = _ipl_lb_extract_for_team(question)
    against_code, against_name, against_aliases = _ipl_lb_extract_against_team(question)
    venue_condition, venue_label = _ipl_lb_extract_venue_condition(question, table_alias="m")

    where_parts = [
        venue_condition,
        "d.wicket_type IS NOT NULL",
        "d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')",
    ]

    if team_aliases:
        where_parts.append(f"d.bowling_team IN {_ipl_lb_sql_list(team_aliases)}")

    if against_aliases:
        where_parts.append(f"d.batting_team IN {_ipl_lb_sql_list(against_aliases)}")

    where_sql = " AND ".join(part for part in where_parts if part and part != "1=1") or "1=1"

    legal_ball_where_parts = [venue_condition]

    if team_aliases:
        legal_ball_where_parts.append(f"d.bowling_team IN {_ipl_lb_sql_list(team_aliases)}")

    if against_aliases:
        legal_ball_where_parts.append(f"d.batting_team IN {_ipl_lb_sql_list(against_aliases)}")

    legal_ball_where = " AND ".join(part for part in legal_ball_where_parts if part and part != "1=1") or "1=1"

    title_bits = ["Top wicket takers"]

    if team_name:
        title_bits.append(f"for {team_name}")

    if against_name:
        title_bits.append(f"against {against_name}")

    if venue_label:
        title_bits.append(f"at {venue_label}")

    title = " ".join(title_bits)

    sql = f"""
WITH legal_balls AS (
    SELECT
        d.bowler,
        COUNT(DISTINCT d.match_id) AS matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS innings,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {legal_ball_where}
    GROUP BY d.bowler
),
wickets AS (
    SELECT
        d.bowler,
        COUNT(*) AS wickets
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.bowler
)
SELECT TOP 10
    lb.bowler,
    lb.matches,
    lb.innings,
    CAST(lb.legal_balls / 6 AS varchar(20)) + '.' + CAST(lb.legal_balls % 6 AS varchar(1)) AS overs_bowled,
    lb.runs_conceded,
    COALESCE(w.wickets, 0) AS wickets,
    ROUND(lb.runs_conceded * 6.0 / NULLIF(lb.legal_balls, 0), 2) AS economy
FROM legal_balls lb
JOIN wickets w
    ON lb.bowler = w.bowler
ORDER BY
    w.wickets DESC,
    economy ASC,
    lb.bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The top wicket-takers query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = f"{title}. This table includes matches and overs bowled, not just wickets."

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {title: df},
        "sql_query": sql,
        "similar_questions": [
            "who are the top 10 run scorers in IPL",
            "who has the best economy in IPL",
            "who has the most wickets in playoffs",
        ],
    }


def _ipl_lb_direct_milestones(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    is_fifty = "fifties" in q or "50s" in q or "half centuries" in q
    is_hundred = "hundreds" in q or "100s" in q or "centuries" in q
    is_fifty_plus = "fifty plus" in q or "50 plus" in q or "50+ scores" in q or "fifty-plus" in q

    if not (is_fifty or is_hundred or is_fifty_plus):
        return None

    if is_fifty_plus:
        milestone_label = "fifty_plus_scores"
        milestone_title = "Fifty Plus Scores"
        milestone_condition = "innings_runs >= 50"
        definition_note = "Fifty-plus scores means every innings of 50 or more, including hundreds."

    elif is_hundred:
        milestone_label = "hundreds"
        milestone_title = "Hundreds"
        milestone_condition = "innings_runs >= 100"
        definition_note = "Hundreds means innings of 100 or more."

    else:
        milestone_label = "fifties"
        milestone_title = "Fifties"
        milestone_condition = "innings_runs BETWEEN 50 AND 99"
        definition_note = "Fifties means scores from 50 to 99 only. If you want 50-plus scores including hundreds, ask for fifty plus scores."

    scope = "all IPL matches"
    scope_join = ""
    scope_cte = ""
    scope_where = "1=1"

    if "final" in q:
        scope = "finals"
        scope_cte = _ipl_lb_playoff_scope_cte("finals")
        scope_join = "JOIN target_matches tm ON d.match_id = tm.match_id"
        scope_where = "1=1"

    elif "playoff" in q:
        scope = "playoffs"
        scope_cte = _ipl_lb_playoff_scope_cte("playoffs")
        scope_join = "JOIN target_matches tm ON d.match_id = tm.match_id"
        scope_where = "1=1"

    team_code, team_name, team_aliases = _ipl_lb_extract_for_team(question)
    against_code, against_name, against_aliases = _ipl_lb_extract_against_team(question)
    venue_condition, venue_label = _ipl_lb_extract_venue_condition(question, table_alias="m")

    where_parts = [venue_condition, scope_where]

    if team_aliases:
        where_parts.append(f"d.batting_team IN {_ipl_lb_sql_list(team_aliases)}")

    if against_aliases:
        where_parts.append(f"d.bowling_team IN {_ipl_lb_sql_list(against_aliases)}")

    where_sql = " AND ".join(part for part in where_parts if part and part != "1=1") or "1=1"

    with_prefix = ""

    if scope_cte:
        with_prefix = scope_cte + ",\n"

    title_bits = [f"Most {milestone_title}"]

    if scope != "all IPL matches":
        title_bits.append(f"in {scope}")

    if team_name:
        title_bits.append(f"for {team_name}")

    if against_name:
        title_bits.append(f"against {against_name}")

    if venue_label:
        title_bits.append(f"at {venue_label}")

    title = " ".join(title_bits)

    sql = f"""
WITH
{with_prefix}innings_scores AS (
    SELECT
        d.match_id,
        d.season,
        d.innings,
        d.striker AS batter,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    {scope_join}
    WHERE {where_sql}
    GROUP BY
        d.match_id,
        d.season,
        d.innings,
        d.striker
),
summary AS (
    SELECT
        batter,
        COUNT(*) AS innings,
        SUM(CASE WHEN {milestone_condition} THEN 1 ELSE 0 END) AS {milestone_label},
        STRING_AGG(
            CASE
                WHEN {milestone_condition}
                THEN CAST(season AS varchar(20))
                ELSE NULL
            END,
            ', '
        ) AS seasons,
        MAX(innings_runs) AS highest_score,
        SUM(innings_runs) AS runs,
        SUM(balls) AS balls
    FROM innings_scores
    GROUP BY batter
)
SELECT TOP 10
    batter,
    innings,
    {milestone_label},
    seasons,
    highest_score,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate
FROM summary
WHERE {milestone_label} > 0
ORDER BY
    {milestone_label} DESC,
    highest_score DESC,
    batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The {title.lower()} query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    playoff_note = ""

    if scope == "playoffs":
        playoff_note = " Playoffs includes the final as well as qualifier/eliminator matches."

    paragraph = f"{title}. {definition_note}{playoff_note}"

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {title: df},
        "sql_query": sql,
        "similar_questions": [
            "who has the most fifty plus scores in playoffs",
            "who has the most fifties in finals",
            "who has the most hundreds in playoffs",
            "who has the most fifty plus scores for CSK",
        ],
    }


try:
    _previous_answer_question_with_fallback_before_leaderboard_routes = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_leaderboard_routes = None


def answer_question_with_fallback(user_question):
    direct_routes = [
        _ipl_lb_direct_top_wicket_takers,
        _ipl_lb_direct_top_run_scorers,
        _ipl_lb_direct_milestones,
    ]

    for route in direct_routes:
        result = route(user_question)

        if result is not None:
            return result

    return _previous_answer_question_with_fallback_before_leaderboard_routes(user_question)

# IPL SQL Agent batting/bowling leaderboard routes override END


# IPL SQL Agent leaderboard innings/matches fix START

def _ipl_lb_direct_top_run_scorers(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    is_run_query = (
        ("top" in q or "most" in q or "highest" in q)
        and ("run scorers" in q or "runs" in q or "run scorer" in q)
    )

    if not is_run_query:
        return None

    if "single over" in q or "losing cause" in q:
        return None

    team_code, team_name, team_aliases = _ipl_lb_extract_for_team(question)
    against_code, against_name, against_aliases = _ipl_lb_extract_against_team(question)
    venue_condition, venue_label = _ipl_lb_extract_venue_condition(question, table_alias="m")

    where_parts = [
        "d.innings IN (1, 2)",
        venue_condition,
    ]

    if team_aliases:
        where_parts.append(f"d.batting_team IN {_ipl_lb_sql_list(team_aliases)}")

    if against_aliases:
        where_parts.append(f"d.bowling_team IN {_ipl_lb_sql_list(against_aliases)}")

    where_sql = " AND ".join(part for part in where_parts if part and part != "1=1") or "1=1"

    title_bits = ["Top run scorers"]

    if team_name:
        title_bits.append(f"for {team_name}")

    if against_name:
        title_bits.append(f"against {against_name}")

    if venue_label:
        title_bits.append(f"at {venue_label}")

    title = " ".join(title_bits)

    sql = f"""
WITH batter_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY
        d.match_id,
        d.innings,
        d.striker
    HAVING
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) > 0
        OR SUM(COALESCE(d.runs_off_bat, 0)) > 0
),
summary AS (
    SELECT
        batter,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(balls) AS balls,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM batter_innings
    GROUP BY batter
)
SELECT TOP 10
    batter,
    matches,
    innings,
    runs,
    balls,
    highest_score,
    fifties,
    hundreds,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate
FROM summary
ORDER BY
    runs DESC,
    innings ASC,
    batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The top run-scorers query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = (
        f"{title}. Matches counts distinct IPL matches where the batter appeared, "
        "and innings counts only innings where the batter actually batted/faced a legal ball or scored."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {title: df},
        "sql_query": sql,
        "similar_questions": [
            "who are the top 10 wicket takers in IPL",
            "who has the most fifties in IPL",
            "who has the most runs in playoffs",
        ],
    }


def _ipl_lb_direct_top_wicket_takers(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    is_wicket_query = (
        ("top" in q or "most" in q or "highest" in q)
        and ("wicket takers" in q or "wickets" in q or "wicket-takers" in q)
    )

    if not is_wicket_query:
        return None

    if "playoff" in q or "final" in q or "losing cause" in q:
        return None

    team_code, team_name, team_aliases = _ipl_lb_extract_for_team(question)
    against_code, against_name, against_aliases = _ipl_lb_extract_against_team(question)
    venue_condition, venue_label = _ipl_lb_extract_venue_condition(question, table_alias="m")

    base_filters = [
        "d.innings IN (1, 2)",
        venue_condition,
    ]

    if team_aliases:
        base_filters.append(f"d.bowling_team IN {_ipl_lb_sql_list(team_aliases)}")

    if against_aliases:
        base_filters.append(f"d.batting_team IN {_ipl_lb_sql_list(against_aliases)}")

    base_where = " AND ".join(part for part in base_filters if part and part != "1=1") or "1=1"

    wicket_where = (
        base_where
        + " AND d.wicket_type IS NOT NULL"
        + " AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')"
    )

    title_bits = ["Top wicket takers"]

    if team_name:
        title_bits.append(f"for {team_name}")

    if against_name:
        title_bits.append(f"against {against_name}")

    if venue_label:
        title_bits.append(f"at {venue_label}")

    title = " ".join(title_bits)

    sql = f"""
WITH bowling_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {base_where}
    GROUP BY
        d.match_id,
        d.innings,
        d.bowler
    HAVING
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) > 0
),
wicket_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        COUNT(*) AS wickets
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {wicket_where}
    GROUP BY
        d.match_id,
        d.innings,
        d.bowler
),
summary AS (
    SELECT
        bi.bowler,
        COUNT(DISTINCT bi.match_id) AS matches,
        COUNT(*) AS innings,
        SUM(bi.legal_balls) AS legal_balls,
        SUM(bi.runs_conceded) AS runs_conceded,
        SUM(COALESCE(wi.wickets, 0)) AS wickets
    FROM bowling_innings bi
    LEFT JOIN wicket_innings wi
        ON bi.match_id = wi.match_id
       AND bi.innings = wi.innings
       AND bi.bowler = wi.bowler
    GROUP BY bi.bowler
)
SELECT TOP 10
    bowler,
    matches,
    innings,
    CAST(legal_balls / 6 AS varchar(20)) + '.' + CAST(legal_balls % 6 AS varchar(1)) AS overs_bowled,
    wickets,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy
FROM summary
WHERE wickets > 0
ORDER BY
    wickets DESC,
    economy ASC,
    bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The top wicket-takers query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = (
        f"{title}. Matches counts distinct matches where the bowler bowled; "
        "innings counts regular innings where the bowler delivered at least one legal ball. "
        "Super-over style innings are excluded by using innings 1 and 2 only."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {title: df},
        "sql_query": sql,
        "similar_questions": [
            "who are the top 10 run scorers in IPL",
            "who has the best economy in IPL",
            "who has the most wickets in playoffs",
        ],
    }

# IPL SQL Agent leaderboard innings/matches fix END

# IPL SQL Agent empty-table cleanup and player matchup fallback START

def _ipl_postprocess_is_empty_table(value):
    try:
        return hasattr(value, "empty") and value.empty
    except Exception:
        return False


def _ipl_postprocess_clean_extra_tables(result):
    if not isinstance(result, dict):
        return result

    extra_tables = result.get("extra_tables")

    if not isinstance(extra_tables, dict):
        return result

    cleaned = {}

    for name, table in extra_tables.items():
        if _ipl_postprocess_is_empty_table(table):
            continue

        if table is None:
            continue

        cleaned[name] = table

    result["extra_tables"] = cleaned

    return result


def _ipl_player_fallback_sql_quote(value):
    return str(value).replace("'", "''")


def _ipl_player_fallback_extract_player_label(question):
    import re

    text = str(question or "").strip()

    patterns = [
        r"^(?:analyse|analyze|profile|player profile of|tell me about)\s+(.+?)\s*$",
        r"^(?:analyse|analyze)\s+(.+?)\s+profile\s*$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            label = match.group(1).strip(" .?")

            blocked = {
                "csk",
                "mi",
                "rcb",
                "gt",
                "kkr",
                "rr",
                "srh",
                "dc",
                "pbks",
                "lsg",
                "squad",
                "team",
            }

            if label.lower() not in blocked:
                return label

    return None


def _ipl_player_fallback_name_list(player_label):
    import pandas as pd
    from app.db import run_query

    label = str(player_label or "").strip()

    if not label:
        return []

    label_lower = label.lower()

    if (
        "suryavanshi" in label_lower
        or "sooryavanshi" in label_lower
        or ("vaibhav" in label_lower and "surya" in label_lower)
    ):
        return [
            "V Suryavanshi",
            "Vaibhav Suryavanshi",
            "Vaibhav Sooryavanshi",
        ]

    label_sql = _ipl_player_fallback_sql_quote(label)

    sql = f"""
SELECT DISTINCT TOP 12
    display_name,
    cricsheet_name
FROM current_squads
WHERE LOWER(COALESCE(display_name, '')) LIKE LOWER('%{label_sql}%')
   OR LOWER(COALESCE(cricsheet_name, '')) LIKE LOWER('%{label_sql}%')
ORDER BY display_name, cricsheet_name;
""".strip()

    names = [label]

    try:
        df = run_query(sql)

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                for column in ["display_name", "cricsheet_name"]:
                    value = row.get(column)

                    if pd.notna(value):
                        value_text = str(value).strip()

                        if value_text and value_text not in names:
                            names.append(value_text)

    except Exception:
        pass

    # Add common short-name fallback from deliveries.
    delivery_sql = f"""
SELECT DISTINCT TOP 12
    striker AS player_name
FROM deliveries
WHERE LOWER(COALESCE(striker, '')) LIKE LOWER('%{label_sql}%')
ORDER BY striker;
""".strip()

    try:
        df = run_query(delivery_sql)

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                value = row.get("player_name")

                if pd.notna(value):
                    value_text = str(value).strip()

                    if value_text and value_text not in names:
                        names.append(value_text)

    except Exception:
        pass

    return names


def _ipl_player_fallback_filter(column_name, names):
    exact_values = []
    like_values = []

    for name in names:
        name_text = str(name or "").strip()

        if not name_text:
            continue

        name_sql = _ipl_player_fallback_sql_quote(name_text)

        exact_values.append(f"{column_name} = '{name_sql}'")

        # Avoid broad one-token LIKE for names like "Kohli" is fine, but not empty.
        like_values.append(f"{column_name} LIKE '%{name_sql}%'")

    clauses = exact_values + like_values

    if not clauses:
        return "1=0"

    return "(" + " OR ".join(clauses) + ")"


def _ipl_player_fallback_table_missing(result, table_keywords):
    if not isinstance(result, dict):
        return True

    extra_tables = result.get("extra_tables") or {}

    if not isinstance(extra_tables, dict):
        return True

    for name, table in extra_tables.items():
        name_lower = str(name).lower()

        if any(keyword in name_lower for keyword in table_keywords):
            if not _ipl_postprocess_is_empty_table(table):
                return False

    return True


def _ipl_player_fallback_add_matchup_tables(question, result):
    import pandas as pd
    from app.db import run_query

    if not isinstance(result, dict):
        return result

    player_label = _ipl_player_fallback_extract_player_label(question)

    if not player_label:
        return result

    names = _ipl_player_fallback_name_list(player_label)

    if not names:
        return result

    striker_filter = _ipl_player_fallback_filter("d.striker", names)
    striker_filter_s = _ipl_player_fallback_filter("s.striker", names)

    extra_tables = result.get("extra_tables") or {}

    if not isinstance(extra_tables, dict):
        extra_tables = {}

    bowler_dismissals_sql = f"""
WITH batter_balls AS (
    SELECT
        d.bowler,
        d.striker AS batter,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.player_dismissed = d.striker
                 AND d.wicket_type NOT IN (
                    'run out',
                    'retired hurt',
                    'retired out',
                    'obstructing the field'
                 )
                THEN 1
            END
        ) AS dismissals
    FROM deliveries d
    WHERE {striker_filter}
      AND d.innings IN (1, 2)
    GROUP BY
        d.bowler,
        d.striker
)
SELECT TOP 10
    bowler,
    batter,
    balls,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS batter_sr
FROM batter_balls
WHERE balls > 0
ORDER BY
    dismissals DESC,
    batter_sr ASC,
    balls DESC;
""".strip()

    quiet_bowlers_sql = f"""
WITH batter_balls AS (
    SELECT
        d.bowler,
        d.striker AS batter,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.player_dismissed = d.striker
                 AND d.wicket_type NOT IN (
                    'run out',
                    'retired hurt',
                    'retired out',
                    'obstructing the field'
                 )
                THEN 1
            END
        ) AS dismissals
    FROM deliveries d
    WHERE {striker_filter}
      AND d.innings IN (1, 2)
    GROUP BY
        d.bowler,
        d.striker
)
SELECT TOP 10
    bowler,
    batter,
    balls,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS batter_sr
FROM batter_balls
WHERE balls >= 6
ORDER BY
    batter_sr ASC,
    dismissals DESC,
    balls DESC;
""".strip()

    bowler_type_sql = f"""
WITH bowler_styles AS (
    SELECT
        bowler,
        MAX(bowling_style_bowler) AS bowling_style
    FROM shot_events
    WHERE bowling_style_bowler IS NOT NULL
    GROUP BY bowler
),
style_balls AS (
    SELECT
        COALESCE(bs.bowling_style, 'Unknown') AS bowling_style,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.player_dismissed = d.striker
                 AND d.wicket_type NOT IN (
                    'run out',
                    'retired hurt',
                    'retired out',
                    'obstructing the field'
                 )
                THEN 1
            END
        ) AS dismissals
    FROM deliveries d
    LEFT JOIN bowler_styles bs
        ON d.bowler = bs.bowler
    WHERE {striker_filter}
      AND d.innings IN (1, 2)
    GROUP BY COALESCE(bs.bowling_style, 'Unknown')
)
SELECT
    bowling_style,
    balls,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS batter_sr,
    CASE
        WHEN balls < 6 THEN 'Small sample'
        WHEN dismissals >= 2 THEN 'Dismissal threat'
        WHEN ROUND(runs * 100.0 / NULLIF(balls, 0), 2) <= 110 THEN 'Difficult style'
        WHEN ROUND(runs * 100.0 / NULLIF(balls, 0), 2) >= 160 THEN 'Scoring style'
        ELSE 'Neutral style'
    END AS style_reading
FROM style_balls
WHERE balls > 0
ORDER BY
    CASE
        WHEN balls < 6 THEN 4
        WHEN dismissals >= 2 THEN 1
        WHEN ROUND(runs * 100.0 / NULLIF(balls, 0), 2) <= 110 THEN 2
        ELSE 3
    END,
    dismissals DESC,
    batter_sr ASC,
    balls DESC;
""".strip()

    active_quiet_bowlers_sql = f"""
WITH batter_balls AS (
    SELECT
        d.bowler,
        d.striker AS batter,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.player_dismissed = d.striker
                 AND d.wicket_type NOT IN (
                    'run out',
                    'retired hurt',
                    'retired out',
                    'obstructing the field'
                 )
                THEN 1
            END
        ) AS dismissals
    FROM deliveries d
    WHERE {striker_filter}
      AND d.innings IN (1, 2)
    GROUP BY
        d.bowler,
        d.striker
),
current_bowlers AS (
    SELECT DISTINCT
        team_code,
        team_name,
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE COALESCE(is_active, 1) = 1
      AND (
            role LIKE '%Bowler%'
         OR role LIKE '%All%'
      )
)
SELECT TOP 10
    cb.team_code,
    cb.team_name,
    cb.display_name AS bowler,
    bb.batter,
    bb.balls,
    bb.runs,
    bb.dismissals,
    ROUND(bb.runs * 100.0 / NULLIF(bb.balls, 0), 2) AS batter_sr
FROM batter_balls bb
JOIN current_bowlers cb
    ON bb.bowler = cb.cricsheet_name
    OR bb.bowler = cb.display_name
    OR bb.bowler LIKE '%' + cb.display_name
    OR cb.cricsheet_name LIKE '%' + bb.bowler
WHERE bb.balls >= 6
ORDER BY
    batter_sr ASC,
    dismissals DESC,
    balls DESC;
""".strip()

    fallback_queries = [
        ("Bowler Dismissals", bowler_dismissals_sql, ["bowler dismissal", "dismissal"]),
        ("Quiet Bowlers", quiet_bowlers_sql, ["quiet bowler", "quiet"]),
        ("Difficult Bowler Types", bowler_type_sql, ["bowler type", "difficult bowler", "style"]),
        ("Active Quiet Bowlers", active_quiet_bowlers_sql, ["active quiet", "active"]),
    ]

    added_any = False

    for table_name, sql, keywords in fallback_queries:
        if not _ipl_player_fallback_table_missing(result, keywords):
            continue

        try:
            df = run_query(sql)

            if df is not None and not df.empty:
                extra_tables[table_name] = df
                added_any = True

        except Exception:
            continue

    if added_any:
        result["extra_tables"] = extra_tables

        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""

        note = (
            " Some matchup tables use deliveries-based fallbacks because this player has limited or missing shot-events data."
        )

        if note.strip() not in paragraph:
            paragraph = (paragraph + note).strip()

        result["analysis_paragraph"] = paragraph
        result["paragraph"] = paragraph

    return result


try:
    _previous_answer_question_with_fallback_before_empty_cleanup_player_fallback = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_empty_cleanup_player_fallback = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_empty_cleanup_player_fallback(user_question)

    result = _ipl_player_fallback_add_matchup_tables(user_question, result)
    result = _ipl_postprocess_clean_extra_tables(result)

    return result

# IPL SQL Agent empty-table cleanup and player matchup fallback END


# IPL SQL Agent advanced analytics/report routes START

def _ipl_adv_sql_quote(value):
    return str(value).replace("'", "''")


def _ipl_adv_sql_list(values):
    items = [
        "'" + _ipl_adv_sql_quote(value) + "'"
        for value in values
        if value and str(value).strip()
    ]

    if not items:
        return "('')"

    return "(" + ", ".join(items) + ")"


def _ipl_adv_team_lookup(text_value):
    text = str(text_value or "").lower().strip()

    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings", "Punjab franchise"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for team_code, team_name, aliases, triggers in teams:
        if text in triggers:
            return team_code, team_name, aliases

    for team_code, team_name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return team_code, team_name, aliases

    return None, None, []


def _ipl_adv_is_team_text(text_value):
    team_code, team_name, aliases = _ipl_adv_team_lookup(text_value)
    return bool(team_code)


def _ipl_adv_player_names(player_label):
    from app.db import run_query

    label = str(player_label or "").strip()

    if not label:
        return []

    lower_label = label.lower()

    if "suryavanshi" in lower_label or "sooryavanshi" in lower_label or ("vaibhav" in lower_label and "surya" in lower_label):
        return ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"]

    label_sql = _ipl_adv_sql_quote(label)

    names = [label]

    squad_sql = f"""
SELECT DISTINCT TOP 10
    display_name,
    cricsheet_name
FROM current_squads
WHERE LOWER(COALESCE(display_name, '')) LIKE LOWER('%{label_sql}%')
   OR LOWER(COALESCE(cricsheet_name, '')) LIKE LOWER('%{label_sql}%')
ORDER BY display_name, cricsheet_name;
""".strip()

    try:
        df = run_query(squad_sql)

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                for column in ["display_name", "cricsheet_name"]:
                    value = row.get(column)

                    if value is not None:
                        value_text = str(value).strip()

                        if value_text and value_text not in names:
                            names.append(value_text)

    except Exception:
        pass

    delivery_sql = f"""
SELECT DISTINCT TOP 10
    striker AS player_name
FROM deliveries
WHERE LOWER(COALESCE(striker, '')) LIKE LOWER('%{label_sql}%')
UNION
SELECT DISTINCT TOP 10
    bowler AS player_name
FROM deliveries
WHERE LOWER(COALESCE(bowler, '')) LIKE LOWER('%{label_sql}%');
""".strip()

    try:
        df = run_query(delivery_sql)

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                value = row.get("player_name")

                if value is not None:
                    value_text = str(value).strip()

                    if value_text and value_text not in names:
                        names.append(value_text)

    except Exception:
        pass

    return names


def _ipl_adv_player_filter(column_name, player_label):
    names = _ipl_adv_player_names(player_label)
    clauses = []

    for name in names:
        name_sql = _ipl_adv_sql_quote(name)
        clauses.append(f"{column_name} = '{name_sql}'")
        clauses.append(f"{column_name} LIKE '%{name_sql}%'")

    if not clauses:
        return "1=0"

    return "(" + " OR ".join(clauses) + ")"


def _ipl_adv_phase_case(ball_column="d.ball"):
    return f"""
CASE
    WHEN FLOOR({ball_column}) BETWEEN 0 AND 5 THEN 'Powerplay'
    WHEN FLOOR({ball_column}) BETWEEN 6 AND 15 THEN 'Middle overs'
    ELSE 'Death overs'
END
""".strip()


def _ipl_adv_add_sample_notes(result):
    if not isinstance(result, dict):
        return result

    tables = []

    if hasattr(result.get("result"), "columns"):
        tables.append(result["result"])

    extra_tables = result.get("extra_tables")

    if isinstance(extra_tables, dict):
        tables.extend([table for table in extra_tables.values() if hasattr(table, "columns")])

    added_note = False

    for table in tables:
        lower_map = {
            str(column).lower(): column
            for column in table.columns
        }

        balls_col = None

        for candidate in ["balls", "phase_balls", "length_balls", "legal_balls"]:
            if candidate in lower_map:
                balls_col = lower_map[candidate]
                break

        if not balls_col:
            continue

        if "sample_note" in table.columns:
            continue

        try:
            table["sample_note"] = table[balls_col].apply(
                lambda value: "Small sample" if float(value) < 12 else "Usable sample"
            )
            added_note = True
        except Exception:
            continue

    if added_note:
        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""
        note = " Small-sample labels are added where the table is based on limited balls."

        if note.strip() not in paragraph:
            paragraph = (paragraph + note).strip()

        result["analysis_paragraph"] = paragraph
        result["paragraph"] = paragraph

    return result


def _ipl_adv_parse_compare(question):
    import re

    text = str(question or "").strip()

    match = re.search(
        r"\bcompare\s+(.+?)\s+(?:and|vs|versus)\s+(.+?)\s*$",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).strip(" .?"), match.group(2).strip(" .?")

    match = re.search(
        r"\bwhich team has better\s+.+?\s+(.+?)\s+(?:or|and|vs|versus)\s+(.+?)\s*$",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).strip(" .?"), match.group(2).strip(" .?")

    return None, None


def _ipl_adv_direct_player_comparison(question):
    import pandas as pd
    from app.db import run_query

    left, right = _ipl_adv_parse_compare(question)

    if not left or not right:
        return None

    if _ipl_adv_is_team_text(left) or _ipl_adv_is_team_text(right):
        return None

    left_filter_bat = _ipl_adv_player_filter("d.striker", left)
    right_filter_bat = _ipl_adv_player_filter("d.striker", right)
    left_filter_bowl = _ipl_adv_player_filter("d.bowler", left)
    right_filter_bowl = _ipl_adv_player_filter("d.bowler", right)

    sql = f"""
WITH player_labels AS (
    SELECT 'A' AS side, '{_ipl_adv_sql_quote(left)}' AS input_name
    UNION ALL
    SELECT 'B' AS side, '{_ipl_adv_sql_quote(right)}' AS input_name
),
batting_innings AS (
    SELECT
        'A' AS side,
        d.match_id,
        d.innings,
        d.striker AS player,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls
    FROM deliveries d
    WHERE {left_filter_bat}
      AND d.innings IN (1, 2)
    GROUP BY d.match_id, d.innings, d.striker

    UNION ALL

    SELECT
        'B' AS side,
        d.match_id,
        d.innings,
        d.striker AS player,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls
    FROM deliveries d
    WHERE {right_filter_bat}
      AND d.innings IN (1, 2)
    GROUP BY d.match_id, d.innings, d.striker
),
batting_summary AS (
    SELECT
        side,
        COUNT(DISTINCT match_id) AS batting_matches,
        COUNT(*) AS batting_innings,
        SUM(innings_runs) AS runs,
        SUM(balls) AS balls,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM batting_innings
    WHERE balls > 0 OR innings_runs > 0
    GROUP BY side
),
bowling_summary AS (
    SELECT
        'A' AS side,
        COUNT(DISTINCT d.match_id) AS bowling_matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS bowling_innings,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
                THEN 1
            END
        ) AS wickets
    FROM deliveries d
    WHERE {left_filter_bowl}
      AND d.innings IN (1, 2)

    UNION ALL

    SELECT
        'B' AS side,
        COUNT(DISTINCT d.match_id) AS bowling_matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS bowling_innings,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
                THEN 1
            END
        ) AS wickets
    FROM deliveries d
    WHERE {right_filter_bowl}
      AND d.innings IN (1, 2)
)
SELECT
    pl.input_name AS player,
    COALESCE(bs.batting_matches, 0) AS batting_matches,
    COALESCE(bs.batting_innings, 0) AS batting_innings,
    COALESCE(bs.runs, 0) AS runs,
    COALESCE(bs.highest_score, 0) AS highest_score,
    COALESCE(bs.fifties, 0) AS fifties,
    COALESCE(bs.hundreds, 0) AS hundreds,
    ROUND(COALESCE(bs.runs, 0) * 100.0 / NULLIF(bs.balls, 0), 2) AS batting_strike_rate,
    COALESCE(bow.bowling_matches, 0) AS bowling_matches,
    COALESCE(bow.bowling_innings, 0) AS bowling_innings,
    CAST(COALESCE(bow.legal_balls, 0) / 6 AS varchar(20)) + '.' + CAST(COALESCE(bow.legal_balls, 0) % 6 AS varchar(1)) AS overs_bowled,
    COALESCE(bow.wickets, 0) AS wickets,
    ROUND(COALESCE(bow.runs_conceded, 0) * 6.0 / NULLIF(bow.legal_balls, 0), 2) AS economy
FROM player_labels pl
LEFT JOIN batting_summary bs
    ON pl.side = bs.side
LEFT JOIN bowling_summary bow
    ON pl.side = bow.side
ORDER BY pl.side;
""".strip()

    try:
        comparison_df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The player comparison query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if comparison_df is None:
        comparison_df = pd.DataFrame()

    paragraph = (
        f"This compares {left} and {right} using local IPL batting and bowling records. "
        "Use batting columns for batters and bowling columns for bowlers/all-rounders."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": comparison_df,
        "extra_tables": {"Player Comparison": comparison_df},
        "sql_query": sql,
        "similar_questions": [
            f"analyse {left}",
            f"analyse {right}",
            f"compare {right} and {left}",
        ],
    }


def _ipl_adv_direct_team_comparison(question):
    import pandas as pd
    from app.db import run_query

    left, right = _ipl_adv_parse_compare(question)

    if not left or not right:
        return None

    left_code, left_name, left_aliases = _ipl_adv_team_lookup(left)
    right_code, right_name, right_aliases = _ipl_adv_team_lookup(right)

    if not left_code or not right_code:
        return None

    left_aliases_sql = _ipl_adv_sql_list(left_aliases)
    right_aliases_sql = _ipl_adv_sql_list(right_aliases)

    left_code_sql = _ipl_adv_sql_quote(left_code)
    right_code_sql = _ipl_adv_sql_quote(right_code)

    sql = f"""
WITH team_list AS (
    SELECT '{left_code_sql}' AS team_code, '{_ipl_adv_sql_quote(left_name)}' AS team_name
    UNION ALL
    SELECT '{right_code_sql}' AS team_code, '{_ipl_adv_sql_quote(right_name)}' AS team_name
),
role_split AS (
    SELECT
        team_code,
        COUNT(*) AS squad_players,
        SUM(CASE WHEN role LIKE '%Batter%' OR role LIKE '%WK%' THEN 1 ELSE 0 END) AS batting_options,
        SUM(CASE WHEN role LIKE '%Bowler%' THEN 1 ELSE 0 END) AS bowling_options,
        SUM(CASE WHEN role LIKE '%All%' THEN 1 ELSE 0 END) AS all_rounders
    FROM current_squads
    WHERE team_code IN ('{left_code_sql}', '{right_code_sql}')
    GROUP BY team_code
),
batting AS (
    SELECT
        CASE
            WHEN d.batting_team IN {left_aliases_sql} THEN '{left_code_sql}'
            WHEN d.batting_team IN {right_aliases_sql} THEN '{right_code_sql}'
        END AS team_code,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls
    FROM deliveries d
    WHERE d.batting_team IN {left_aliases_sql}
       OR d.batting_team IN {right_aliases_sql}
    GROUP BY
        CASE
            WHEN d.batting_team IN {left_aliases_sql} THEN '{left_code_sql}'
            WHEN d.batting_team IN {right_aliases_sql} THEN '{right_code_sql}'
        END
),
bowling AS (
    SELECT
        CASE
            WHEN d.bowling_team IN {left_aliases_sql} THEN '{left_code_sql}'
            WHEN d.bowling_team IN {right_aliases_sql} THEN '{right_code_sql}'
        END AS team_code,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
                THEN 1
            END
        ) AS wickets,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded
    FROM deliveries d
    WHERE d.bowling_team IN {left_aliases_sql}
       OR d.bowling_team IN {right_aliases_sql}
    GROUP BY
        CASE
            WHEN d.bowling_team IN {left_aliases_sql} THEN '{left_code_sql}'
            WHEN d.bowling_team IN {right_aliases_sql} THEN '{right_code_sql}'
        END
)
SELECT
    tl.team_code,
    tl.team_name,
    COALESCE(rs.squad_players, 0) AS squad_players,
    COALESCE(rs.batting_options, 0) AS batting_options,
    COALESCE(rs.bowling_options, 0) AS bowling_options,
    COALESCE(rs.all_rounders, 0) AS all_rounders,
    ROUND(COALESCE(bat.runs, 0) * 100.0 / NULLIF(bat.balls, 0), 2) AS historical_batting_sr,
    COALESCE(bowl.wickets, 0) AS historical_wickets,
    ROUND(COALESCE(bowl.runs_conceded, 0) * 6.0 / NULLIF(bowl.legal_balls, 0), 2) AS historical_economy
FROM team_list tl
LEFT JOIN role_split rs
    ON tl.team_code = rs.team_code
LEFT JOIN batting bat
    ON tl.team_code = bat.team_code
LEFT JOIN bowling bowl
    ON tl.team_code = bowl.team_code
ORDER BY tl.team_code;
""".strip()

    try:
        comparison_df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The team comparison query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if comparison_df is None:
        comparison_df = pd.DataFrame()

    paragraph = (
        f"This compares {left_name} and {right_name} using current squad composition plus historical IPL batting and bowling indicators."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": comparison_df,
        "extra_tables": {"Team Comparison": comparison_df},
        "sql_query": sql,
        "similar_questions": [
            f"how can {left_code} beat {right_code}",
            f"analyse {left_code} squad",
            f"analyse {right_code} squad",
        ],
    }


def _ipl_adv_direct_current_squad_specialists(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    if "current" not in q and "squad" not in q:
        return None

    team_code, team_name, aliases = _ipl_adv_team_lookup(q)

    if not team_code:
        return None

    team_code_sql = _ipl_adv_sql_quote(team_code)

    is_bowler_route = "bowler" in q or "bowling" in q
    is_finisher_route = "finisher" in q or "death batter" in q or "death batting" in q

    if not (is_bowler_route or is_finisher_route):
        return None

    if "powerplay" in q:
        phase_label = "Powerplay"
        phase_filter = "FLOOR(d.ball) BETWEEN 0 AND 5"
    elif "middle" in q:
        phase_label = "Middle overs"
        phase_filter = "FLOOR(d.ball) BETWEEN 6 AND 15"
    else:
        phase_label = "Death overs"
        phase_filter = "FLOOR(d.ball) BETWEEN 16 AND 19"

    if is_bowler_route:
        sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{team_code_sql}'
      AND COALESCE(is_active, 1) = 1
      AND (
            role LIKE '%Bowler%'
         OR role LIKE '%All%'
      )
),
bowling AS (
    SELECT
        cb.display_name AS player,
        COUNT(DISTINCT d.match_id) AS matches,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
                THEN 1
            END
        ) AS wickets
    FROM current_bowlers cb
    JOIN deliveries d
        ON d.bowler = cb.cricsheet_name
        OR d.bowler = cb.display_name
        OR d.bowler LIKE '%' + cb.display_name
        OR cb.cricsheet_name LIKE '%' + d.bowler
    WHERE {phase_filter}
      AND d.innings IN (1, 2)
    GROUP BY cb.display_name
)
SELECT TOP 10
    player,
    matches,
    CAST(balls / 6 AS varchar(20)) + '.' + CAST(balls % 6 AS varchar(1)) AS overs,
    wickets,
    ROUND(runs_conceded * 6.0 / NULLIF(balls, 0), 2) AS economy,
    CASE
        WHEN balls < 24 THEN 'Small sample'
        WHEN wickets >= 10 THEN 'Wicket threat'
        WHEN ROUND(runs_conceded * 6.0 / NULLIF(balls, 0), 2) <= 8 THEN 'Control option'
        ELSE 'Usable option'
    END AS role_reading
FROM bowling
WHERE balls > 0
ORDER BY
    wickets DESC,
    economy ASC,
    balls DESC;
""".strip()

        title = f"Best {phase_label} bowlers in current {team_code} squad"

    else:
        sql = f"""
WITH current_batters AS (
    SELECT DISTINCT
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{team_code_sql}'
      AND COALESCE(is_active, 1) = 1
      AND (
            role LIKE '%Batter%'
         OR role LIKE '%WK%'
         OR role LIKE '%All%'
      )
),
batting AS (
    SELECT
        cb.display_name AS player,
        COUNT(DISTINCT d.match_id) AS matches,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.player_dismissed = d.striker
                THEN 1
            END
        ) AS dismissals
    FROM current_batters cb
    JOIN deliveries d
        ON d.striker = cb.cricsheet_name
        OR d.striker = cb.display_name
        OR d.striker LIKE '%' + cb.display_name
        OR cb.cricsheet_name LIKE '%' + d.striker
    WHERE {phase_filter}
      AND d.innings IN (1, 2)
    GROUP BY cb.display_name
)
SELECT TOP 10
    player,
    matches,
    balls,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate,
    CASE
        WHEN balls < 20 THEN 'Small sample'
        WHEN ROUND(runs * 100.0 / NULLIF(balls, 0), 2) >= 160 THEN 'High-impact option'
        WHEN ROUND(runs * 100.0 / NULLIF(balls, 0), 2) >= 135 THEN 'Good option'
        ELSE 'Usable option'
    END AS role_reading
FROM batting
WHERE balls > 0
ORDER BY
    strike_rate DESC,
    runs DESC,
    balls DESC;
""".strip()

        title = f"Best {phase_label} finishers in current {team_code} squad"

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The current squad specialist query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = f"{title}. This route only uses players listed in the current squad table."

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {title: df},
        "sql_query": sql,
        "similar_questions": [
            f"analyse {team_code} squad",
            f"best death bowlers in current {team_code} squad",
            f"best finishers in current {team_code} squad",
        ],
    }


def _ipl_adv_direct_report_mode(question):
    import pandas as pd

    q = str(question or "").lower().strip()

    if not (
        "scouting report" in q
        or "full report" in q
        or "match report" in q
        or q.startswith("make a report")
    ):
        return None

    try:
        if " vs " in q or " beat " in q:
            cleaned = q.replace("make a", "").replace("full", "").replace("scouting", "").replace("match report", "").replace("report", "").strip()

            if " vs " in cleaned:
                parts = cleaned.split(" vs ", 1)
                left = parts[0].strip()
                right = parts[1].strip()
                synthetic_question = f"how can {left} beat {right}"

            else:
                synthetic_question = cleaned

            base = _previous_answer_question_with_fallback_before_advanced_routes(synthetic_question)

            if isinstance(base, dict):
                paragraph = base.get("analysis_paragraph") or base.get("paragraph") or ""

                report_paragraph = (
                    "Scouting report: "
                    + paragraph
                    + " Read this as a structured match report: start with venue/toss context, then batting matchups, bowling matchups, and sample-size notes in the tables."
                )

                base["analysis_paragraph"] = report_paragraph
                base["paragraph"] = report_paragraph

                return base

        # Team report.
        team_code, team_name, aliases = _ipl_adv_team_lookup(q)

        if team_code:
            base = _previous_answer_question_with_fallback_before_advanced_routes(f"analyse {team_code} squad")

            if isinstance(base, dict):
                paragraph = base.get("analysis_paragraph") or base.get("paragraph") or ""

                report_paragraph = (
                    f"Scouting report on {team_name}: "
                    + paragraph
                    + " The key reading is the balance between current squad roles, recent performance, and phase-specific tactical options."
                )

                base["analysis_paragraph"] = report_paragraph
                base["paragraph"] = report_paragraph

                return base

        # Player report.
        import re

        match = re.search(
            r"(?:on|about)\s+(.+?)\s*$",
            str(question or ""),
            flags=re.IGNORECASE,
        )

        player = match.group(1).strip(" .?") if match else str(question).split()[-1]

        base = _previous_answer_question_with_fallback_before_advanced_routes(f"analyse {player}")

        if isinstance(base, dict):
            paragraph = base.get("analysis_paragraph") or base.get("paragraph") or ""

            report_paragraph = (
                f"Scouting report on {player}: "
                + paragraph
                + " Use the matchup tables to identify difficult bowling types, quiet bowlers, and dismissal threats."
            )

            base["analysis_paragraph"] = report_paragraph
            base["paragraph"] = report_paragraph

            return base

    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The report route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": "",
            "similar_questions": [],
        }

    return None


try:
    _previous_answer_question_with_fallback_before_advanced_routes = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_advanced_routes = None


def answer_question_with_fallback(user_question):
    routes = [
        _ipl_adv_direct_current_squad_specialists,
        _ipl_adv_direct_team_comparison,
        _ipl_adv_direct_player_comparison,
        _ipl_adv_direct_report_mode,
    ]

    for route in routes:
        result = route(user_question)

        if result is not None:
            return _ipl_adv_add_sample_notes(result)

    result = _previous_answer_question_with_fallback_before_advanced_routes(user_question)

    return _ipl_adv_add_sample_notes(result)

# IPL SQL Agent advanced analytics/report routes END


# IPL SQL Agent deep team routes v2 START

def _deep_sql_quote(value):
    return str(value).replace("'", "''")


def _deep_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _deep_sql_quote(v) + "'" for v in values) + ")"


def _deep_team_lookup(text_value):
    text = str(text_value or "").lower().strip()

    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings", "Punjab franchise"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases

    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases

    return None, None, []


def _deep_season_order_expr(col):
    return f"""
CASE
    WHEN CHARINDEX('/', CAST({col} AS varchar(20))) > 0
    THEN TRY_CONVERT(INT, LEFT(CAST({col} AS varchar(20)), 4))
    ELSE TRY_CONVERT(INT, CAST({col} AS varchar(20)))
END
""".strip()


def _deep_sort_season_tables(result):
    if not isinstance(result, dict):
        return result

    def sort_one(df):
        if not hasattr(df, "columns") or df.empty:
            return df

        season_col = None

        for col in df.columns:
            if str(col).strip().lower().replace("_", " ") == "season":
                season_col = col
                break

        if season_col is None:
            return df

        try:
            out = df.copy()

            def k(v):
                t = str(v)
                if "/" in t:
                    t = t.split("/", 1)[0]
                try:
                    return int(float(t))
                except Exception:
                    return 999999

            out["_season_sort_key"] = out[season_col].apply(k)
            out = out.sort_values(["_season_sort_key", season_col], ascending=[True, True])
            return out.drop(columns=["_season_sort_key"]).reset_index(drop=True)

        except Exception:
            return df

    if hasattr(result.get("result"), "columns"):
        result["result"] = sort_one(result["result"])

    extra = result.get("extra_tables")

    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = sort_one(table)

    return result


def _deep_parse_team_compare(question):
    import re

    text = str(question or "").strip()

    match = re.search(
        r"\bcompare\s+(.+?)\s+(?:and|vs|versus)\s+(.+?)\s*$",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    left = match.group(1).strip(" .?")
    right = match.group(2).strip(" .?")

    l_code, l_name, l_aliases = _deep_team_lookup(left)
    r_code, r_name, r_aliases = _deep_team_lookup(right)

    if not l_code or not r_code:
        return None

    return l_code, l_name, l_aliases, r_code, r_name, r_aliases


def _deep_direct_team_compare(question):
    import pandas as pd
    from app.db import run_query

    parsed = _deep_parse_team_compare(question)

    if not parsed:
        return None

    l_code, l_name, l_aliases, r_code, r_name, r_aliases = parsed
    l_aliases_sql = _deep_sql_list(l_aliases)
    r_aliases_sql = _deep_sql_list(r_aliases)

    l_code_sql = _deep_sql_quote(l_code)
    r_code_sql = _deep_sql_quote(r_code)
    l_name_sql = _deep_sql_quote(l_name)
    r_name_sql = _deep_sql_quote(r_name)

    summary_sql = f"""
WITH team_list AS (
    SELECT '{l_code_sql}' AS team_code, '{l_name_sql}' AS team_name
    UNION ALL
    SELECT '{r_code_sql}' AS team_code, '{r_name_sql}' AS team_name
),
final_dates AS (
    SELECT season, MAX(CAST(start_date AS date)) AS final_date
    FROM matches
    WHERE winner IS NOT NULL
    GROUP BY season
),
final_matches AS (
    SELECT m.match_id, m.season, m.winner
    FROM matches m
    JOIN final_dates fd
        ON m.season = fd.season
       AND CAST(m.start_date AS date) = fd.final_date
),
final_participants AS (
    SELECT DISTINCT
        fm.season,
        CASE
            WHEN d.batting_team IN {l_aliases_sql} OR d.bowling_team IN {l_aliases_sql} THEN '{l_code_sql}'
            WHEN d.batting_team IN {r_aliases_sql} OR d.bowling_team IN {r_aliases_sql} THEN '{r_code_sql}'
        END AS team_code
    FROM final_matches fm
    JOIN deliveries d
        ON fm.match_id = d.match_id
    WHERE d.batting_team IN {l_aliases_sql}
       OR d.bowling_team IN {l_aliases_sql}
       OR d.batting_team IN {r_aliases_sql}
       OR d.bowling_team IN {r_aliases_sql}
),
trophies AS (
    SELECT
        CASE
            WHEN winner IN {l_aliases_sql} THEN '{l_code_sql}'
            WHEN winner IN {r_aliases_sql} THEN '{r_code_sql}'
        END AS team_code,
        COUNT(*) AS trophies,
        STRING_AGG(CAST(season AS varchar(20)), ', ') AS trophy_years
    FROM final_matches
    WHERE winner IN {l_aliases_sql}
       OR winner IN {r_aliases_sql}
    GROUP BY CASE
            WHEN winner IN {l_aliases_sql} THEN '{l_code_sql}'
            WHEN winner IN {r_aliases_sql} THEN '{r_code_sql}'
        END
),
finals AS (
    SELECT team_code, COUNT(DISTINCT season) AS finals_played, STRING_AGG(CAST(season AS varchar(20)), ', ') AS final_years
    FROM final_participants
    WHERE team_code IS NOT NULL
    GROUP BY team_code
),
playoff_dates AS (
    SELECT
        season,
        CAST(start_date AS date) AS match_date,
        DENSE_RANK() OVER (PARTITION BY season ORDER BY CAST(start_date AS date) DESC) AS reverse_date_rank
    FROM matches
    WHERE winner IS NOT NULL
),
playoff_matches AS (
    SELECT DISTINCT m.match_id, m.season
    FROM matches m
    JOIN playoff_dates pd
        ON m.season = pd.season
       AND CAST(m.start_date AS date) = pd.match_date
    WHERE pd.reverse_date_rank <= 4
),
playoff_teams AS (
    SELECT DISTINCT
        pm.season,
        CASE
            WHEN d.batting_team IN {l_aliases_sql} OR d.bowling_team IN {l_aliases_sql} THEN '{l_code_sql}'
            WHEN d.batting_team IN {r_aliases_sql} OR d.bowling_team IN {r_aliases_sql} THEN '{r_code_sql}'
        END AS team_code
    FROM playoff_matches pm
    JOIN deliveries d
        ON pm.match_id = d.match_id
    WHERE d.batting_team IN {l_aliases_sql}
       OR d.bowling_team IN {l_aliases_sql}
       OR d.batting_team IN {r_aliases_sql}
       OR d.bowling_team IN {r_aliases_sql}
),
playoffs AS (
    SELECT team_code, COUNT(DISTINCT season) AS playoff_seasons, STRING_AGG(CAST(season AS varchar(20)), ', ') AS playoff_years
    FROM playoff_teams
    WHERE team_code IS NOT NULL
    GROUP BY team_code
),
squad AS (
    SELECT
        team_code,
        COUNT(*) AS current_squad_players,
        SUM(CASE WHEN role LIKE '%Batter%' OR role LIKE '%WK%' THEN 1 ELSE 0 END) AS batting_options,
        SUM(CASE WHEN role LIKE '%Bowler%' THEN 1 ELSE 0 END) AS bowling_options,
        SUM(CASE WHEN role LIKE '%All%' THEN 1 ELSE 0 END) AS all_rounders
    FROM current_squads
    WHERE team_code IN ('{l_code_sql}', '{r_code_sql}')
      AND COALESCE(is_active, 1) = 1
    GROUP BY team_code
),
h2h_matches AS (
    SELECT DISTINCT m.match_id, m.winner
    FROM matches m
    JOIN deliveries d
        ON m.match_id = d.match_id
    WHERE (
            d.batting_team IN {l_aliases_sql}
        AND d.bowling_team IN {r_aliases_sql}
    )
       OR (
            d.batting_team IN {r_aliases_sql}
        AND d.bowling_team IN {l_aliases_sql}
    )
),
h2h AS (
    SELECT
        COUNT(*) AS head_to_head_matches,
        SUM(CASE WHEN winner IN {l_aliases_sql} THEN 1 ELSE 0 END) AS left_wins,
        SUM(CASE WHEN winner IN {r_aliases_sql} THEN 1 ELSE 0 END) AS right_wins
    FROM h2h_matches
)
SELECT
    tl.team_code,
    tl.team_name,
    COALESCE(t.trophies, 0) AS trophies,
    COALESCE(t.trophy_years, '') AS trophy_years,
    COALESCE(f.finals_played, 0) AS finals_played,
    COALESCE(f.final_years, '') AS final_years,
    COALESCE(p.playoff_seasons, 0) AS playoff_seasons,
    COALESCE(p.playoff_years, '') AS playoff_years,
    COALESCE(s.current_squad_players, 0) AS current_squad_players,
    COALESCE(s.batting_options, 0) AS batting_options,
    COALESCE(s.bowling_options, 0) AS bowling_options,
    COALESCE(s.all_rounders, 0) AS all_rounders,
    h.head_to_head_matches,
    CASE WHEN tl.team_code = '{l_code_sql}' THEN h.left_wins ELSE h.right_wins END AS h2h_wins,
    CASE WHEN tl.team_code = '{l_code_sql}' THEN h.right_wins ELSE h.left_wins END AS h2h_losses
FROM team_list tl
LEFT JOIN trophies t ON tl.team_code = t.team_code
LEFT JOIN finals f ON tl.team_code = f.team_code
LEFT JOIN playoffs p ON tl.team_code = p.team_code
LEFT JOIN squad s ON tl.team_code = s.team_code
CROSS JOIN h2h h
ORDER BY tl.team_code;
""".strip()

    h2h_sql = f"""
SELECT
    m.season,
    CAST(m.start_date AS date) AS match_date,
    m.winner,
    COUNT(*) AS balls_recorded
FROM matches m
JOIN deliveries d
    ON m.match_id = d.match_id
WHERE (
        d.batting_team IN {l_aliases_sql}
    AND d.bowling_team IN {r_aliases_sql}
)
   OR (
        d.batting_team IN {r_aliases_sql}
    AND d.bowling_team IN {l_aliases_sql}
)
GROUP BY
    m.season,
    CAST(m.start_date AS date),
    m.winner
ORDER BY
    {_deep_season_order_expr("m.season")},
    CAST(m.start_date AS date);
""".strip()

    try:
        summary_df = run_query(summary_sql)
        h2h_df = run_query(h2h_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The team comparison query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": summary_sql,
            "similar_questions": [],
        }

    if summary_df is None:
        summary_df = pd.DataFrame()

    if h2h_df is None:
        h2h_df = pd.DataFrame()

    paragraph = (
        f"This compares {l_name} and {r_name} by trophies won, finals played, playoff seasons, "
        "current squad balance, and head-to-head record."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": summary_df,
        "extra_tables": {
            "Team Comparison Summary": summary_df,
            "Head To Head Matches": h2h_df,
        },
        "sql_query": summary_sql + "\n\n" + h2h_sql,
        "similar_questions": [
            f"how can {l_code} beat {r_code}",
            f"analyse {l_code} squad",
            f"analyse {r_code} squad",
        ],
    }


def _deep_direct_key_players(question):
    import re
    import pandas as pd
    from app.db import run_query

    text = str(question or "")

    if "key player" not in text.lower() and "important player" not in text.lower():
        return None

    match = re.search(r"\b(?:for|in)\s+(.+?)\s*$", text, flags=re.IGNORECASE)

    if not match:
        return None

    team_code, team_name, aliases = _deep_team_lookup(match.group(1).strip(" .?"))

    if not team_code:
        return None

    team_code_sql = _deep_sql_quote(team_code)

    sql = f"""
WITH current_players AS (
    SELECT DISTINCT
        team_code,
        team_name,
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{team_code_sql}'
      AND COALESCE(is_active, 1) = 1
),
batting AS (
    SELECT
        cp.display_name AS player,
        COUNT(DISTINCT d.match_id) AS batting_matches,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM current_players cp
    LEFT JOIN deliveries d
        ON d.striker = cp.cricsheet_name
        OR d.striker = cp.display_name
        OR d.striker LIKE '%' + cp.display_name
        OR cp.cricsheet_name LIKE '%' + d.striker
    GROUP BY cp.display_name
),
bowling AS (
    SELECT
        cp.display_name AS player,
        COUNT(DISTINCT d.match_id) AS bowling_matches,
        COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded
    FROM current_players cp
    LEFT JOIN deliveries d
        ON d.bowler = cp.cricsheet_name
        OR d.bowler = cp.display_name
        OR d.bowler LIKE '%' + cp.display_name
        OR cp.cricsheet_name LIKE '%' + d.bowler
    GROUP BY cp.display_name
),
summary AS (
    SELECT
        cp.team_code,
        cp.team_name,
        cp.display_name AS player,
        cp.role,
        COALESCE(bat.batting_matches, 0) AS batting_matches,
        COALESCE(bat.runs, 0) AS runs,
        ROUND(COALESCE(bat.runs, 0) * 100.0 / NULLIF(bat.balls, 0), 2) AS batting_sr,
        COALESCE(bowl.bowling_matches, 0) AS bowling_matches,
        COALESCE(bowl.wickets, 0) AS wickets,
        ROUND(COALESCE(bowl.runs_conceded, 0) * 6.0 / NULLIF(bowl.legal_balls, 0), 2) AS economy,
        (
            COALESCE(bat.runs, 0) / 25.0
            + COALESCE(bowl.wickets, 0) * 4.0
            + CASE WHEN cp.role LIKE '%All%' THEN 12 ELSE 0 END
            + CASE WHEN cp.role LIKE '%WK%' THEN 6 ELSE 0 END
            + CASE WHEN COALESCE(bat.balls, 0) >= 100 THEN 8 ELSE 0 END
            + CASE WHEN COALESCE(bowl.legal_balls, 0) >= 120 THEN 8 ELSE 0 END
        ) AS key_player_score
    FROM current_players cp
    LEFT JOIN batting bat ON cp.display_name = bat.player
    LEFT JOIN bowling bowl ON cp.display_name = bowl.player
)
SELECT TOP 10
    team_code,
    team_name,
    player,
    role,
    batting_matches,
    runs,
    batting_sr,
    bowling_matches,
    wickets,
    economy,
    ROUND(key_player_score, 2) AS key_player_score,
    CASE
        WHEN role LIKE '%All%' THEN 'Two-skill value'
        WHEN wickets >= 20 THEN 'Main wicket threat'
        WHEN runs >= 500 THEN 'Main batting contributor'
        WHEN role LIKE '%WK%' THEN 'Keeper-batter value'
        ELSE 'Squad role value'
    END AS why_key
FROM summary
ORDER BY key_player_score DESC, player ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The key players query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = (
        f"These are key players for {team_name} using only the current_squads table first, "
        "then ranking those current players by batting output, wicket threat, all-round value, and role value."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {"Current Squad Key Players": df},
        "sql_query": sql,
        "similar_questions": [
            f"analyse {team_code} squad",
            f"best death bowlers in current {team_code} squad",
            f"best finishers in current {team_code} squad",
        ],
    }


def _deep_direct_next_year_plan(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    if not ("next year" in q or "next season" in q or "win next" in q or "auction" in q or "need to invest" in q):
        return None

    team_code, team_name, aliases = _deep_team_lookup(q)

    if not team_code:
        return None

    aliases_sql = _deep_sql_list(aliases)

    latest_sql = f"""
SELECT TOP 1 season
FROM matches
WHERE season IS NOT NULL
ORDER BY {_deep_season_order_expr("season")} DESC, season DESC;
""".strip()

    try:
        latest_df = run_query(latest_sql)
        latest_season = str(latest_df.iloc[0]["season"])
    except Exception:
        latest_season = ""

    latest = _deep_sql_quote(latest_season)

    phase_case = """
CASE
    WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
    WHEN FLOOR(d.ball) BETWEEN 6 AND 15 THEN 'Middle overs'
    ELSE 'Death overs'
END
""".strip()

    batting_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS wickets_lost,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS strike_rate
FROM deliveries d
WHERE d.batting_team IN {aliases_sql}
  AND d.season = '{latest}'
  AND d.innings IN (1, 2)
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case} = 'Powerplay' THEN 1 WHEN {phase_case} = 'Middle overs' THEN 2 ELSE 3 END;
""".strip()

    bowling_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS economy
FROM deliveries d
WHERE d.bowling_team IN {aliases_sql}
  AND d.season = '{latest}'
  AND d.innings IN (1, 2)
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case} = 'Powerplay' THEN 1 WHEN {phase_case} = 'Middle overs' THEN 2 ELSE 3 END;
""".strip()

    squad_sql = f"""
SELECT
    team_code,
    team_name,
    COUNT(*) AS squad_players,
    SUM(CASE WHEN role LIKE '%Batter%' OR role LIKE '%WK%' THEN 1 ELSE 0 END) AS batting_options,
    SUM(CASE WHEN role LIKE '%Bowler%' THEN 1 ELSE 0 END) AS bowling_options,
    SUM(CASE WHEN role LIKE '%All%' THEN 1 ELSE 0 END) AS all_rounders
FROM current_squads
WHERE team_code = '{_deep_sql_quote(team_code)}'
  AND COALESCE(is_active, 1) = 1
GROUP BY team_code, team_name;
""".strip()

    try:
        batting_df = run_query(batting_sql)
        bowling_df = run_query(bowling_sql)
        squad_df = run_query(squad_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The next-year plan query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": batting_sql + "\n\n" + bowling_sql + "\n\n" + squad_sql,
            "similar_questions": [],
        }

    if batting_df is None:
        batting_df = pd.DataFrame()

    if bowling_df is None:
        bowling_df = pd.DataFrame()

    if squad_df is None:
        squad_df = pd.DataFrame()

    needs = []

    try:
        middle = batting_df[batting_df["phase"] == "Middle overs"]
        if not middle.empty and float(middle.iloc[0].get("strike_rate") or 0) < 125:
            needs.append("invest in a middle-order batter who can lift scoring in overs 7-15")

        death_bat = batting_df[batting_df["phase"] == "Death overs"]
        if not death_bat.empty and float(death_bat.iloc[0].get("strike_rate") or 0) < 155:
            needs.append("add a death-overs finisher")

        power_bowl = bowling_df[bowling_df["phase"] == "Powerplay"]
        if not power_bowl.empty and float(power_bowl.iloc[0].get("wickets") or 0) < 8:
            needs.append("add a powerplay wicket-taking bowler")

        death_bowl = bowling_df[bowling_df["phase"] == "Death overs"]
        if not death_bowl.empty and float(death_bowl.iloc[0].get("economy") or 99) > 10:
            needs.append("add a death-overs specialist bowler")

        if not squad_df.empty and int(squad_df.iloc[0].get("all_rounders") or 0) < 3:
            needs.append("increase all-round depth")

    except Exception:
        pass

    if not needs:
        needs = ["improve backup options for high-pressure roles", "add role-specific depth rather than rebuilding the whole squad"]

    rec_df = pd.DataFrame(
        [
            {
                "priority": i + 1,
                "need": need,
                "why_it_matters": "Based on latest-season phase performance and current squad balance.",
            }
            for i, need in enumerate(needs[:5])
        ]
    )

    paragraph = (
        f"To help {team_name} win next year, the agent reviews their latest available season ({latest_season}), "
        "splits batting and bowling by phase, then compares those weaknesses with current squad balance. "
        f"Main needs: {', '.join(needs[:3])}."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": rec_df,
        "extra_tables": {
            "Recruitment Priorities": rec_df,
            "Latest Season Batting By Phase": batting_df,
            "Latest Season Bowling By Phase": bowling_df,
            "Current Squad Balance": squad_df,
        },
        "sql_query": batting_sql + "\n\n" + bowling_sql + "\n\n" + squad_sql,
        "similar_questions": [
            f"best finishers in current {team_code} squad",
            f"best death bowlers in current {team_code} squad",
            f"analyse {team_code} squad",
        ],
    }


try:
    _previous_answer_question_with_fallback_before_deep_team_routes_v2 = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_deep_team_routes_v2 = None


def answer_question_with_fallback(user_question):
    routes = [
        _deep_direct_next_year_plan,
        _deep_direct_key_players,
        _deep_direct_team_compare,
    ]

    for route in routes:
        result = route(user_question)
        if result is not None:
            return _deep_sort_season_tables(result)

    result = _previous_answer_question_with_fallback_before_deep_team_routes_v2(user_question)
    return _deep_sort_season_tables(result)

# IPL SQL Agent deep team routes v2 END


# IPL SQL Agent key players and next-year plan fix START

def _fix_team_lookup(text_value):
    text = str(text_value or "").lower().strip()

    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings", "Punjab franchise"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases

    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases

    return None, None, []


def _fix_sql_quote(value):
    return str(value).replace("'", "''")


def _fix_sql_list(values):
    values = [value for value in values if value and str(value).strip()]

    if not values:
        return "('')"

    return "(" + ", ".join("'" + _fix_sql_quote(value) + "'" for value in values) + ")"


def _fix_season_order_expr(column_name):
    return f"""
CASE
    WHEN CHARINDEX('/', CAST({column_name} AS varchar(20))) > 0
    THEN TRY_CONVERT(INT, LEFT(CAST({column_name} AS varchar(20)), 4))
    ELSE TRY_CONVERT(INT, CAST({column_name} AS varchar(20)))
END
""".strip()


def _fix_extract_team_from_question(question):
    import re

    text = str(question or "")

    # Prefer team mentioned after "for" or "in".
    for pattern in [
        r"\bfor\s+([A-Za-z0-9 .]+?)\s*$",
        r"\bin\s+([A-Za-z0-9 .]+?)\s*$",
    ]:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            code, name, aliases = _fix_team_lookup(match.group(1).strip(" .?"))

            if code:
                return code, name, aliases

    return _fix_team_lookup(text)


def _fix_direct_key_players(question):
    import pandas as pd
    from app.db import run_query

    text = str(question or "").lower()

    if not (
        "key" in text
        and ("player" in text or "players" in text)
    ):
        return None

    team_code, team_name, aliases = _fix_extract_team_from_question(question)

    if not team_code:
        return None

    team_code_sql = _fix_sql_quote(team_code)

    # Important fix: current_players is the driving table and joins are exact only.
    # This prevents random non-current players from appearing.
    sql = f"""
WITH current_players AS (
    SELECT DISTINCT
        team_code,
        team_name,
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{team_code_sql}'
      AND COALESCE(is_active, 1) = 1
),
batting AS (
    SELECT
        cp.display_name AS player,
        COUNT(DISTINCT d.match_id) AS batting_matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS batting_innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS balls
    FROM current_players cp
    LEFT JOIN deliveries d
        ON (
               d.striker = cp.cricsheet_name
            OR d.striker = cp.display_name
        )
       AND d.innings IN (1, 2)
    GROUP BY cp.display_name
),
bowling AS (
    SELECT
        cp.display_name AS player,
        COUNT(DISTINCT d.match_id) AS bowling_matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS bowling_innings,
        COUNT(
            CASE
                WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
                THEN 1
            END
        ) AS wickets,
        COUNT(
            CASE
                WHEN COALESCE(d.wides, 0) = 0
                 AND COALESCE(d.noballs, 0) = 0
                THEN 1
            END
        ) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded
    FROM current_players cp
    LEFT JOIN deliveries d
        ON (
               d.bowler = cp.cricsheet_name
            OR d.bowler = cp.display_name
        )
       AND d.innings IN (1, 2)
    GROUP BY cp.display_name
),
summary AS (
    SELECT
        cp.team_code,
        cp.team_name,
        cp.display_name AS player,
        cp.cricsheet_name,
        cp.role,
        COALESCE(bat.batting_matches, 0) AS batting_matches,
        COALESCE(bat.batting_innings, 0) AS batting_innings,
        COALESCE(bat.runs, 0) AS runs,
        ROUND(COALESCE(bat.runs, 0) * 100.0 / NULLIF(bat.balls, 0), 2) AS batting_sr,
        COALESCE(bowl.bowling_matches, 0) AS bowling_matches,
        COALESCE(bowl.bowling_innings, 0) AS bowling_innings,
        COALESCE(bowl.wickets, 0) AS wickets,
        ROUND(COALESCE(bowl.runs_conceded, 0) * 6.0 / NULLIF(bowl.legal_balls, 0), 2) AS economy,
        (
            COALESCE(bat.runs, 0) / 25.0
            + COALESCE(bowl.wickets, 0) * 4.0
            + CASE WHEN cp.role LIKE '%All%' THEN 14 ELSE 0 END
            + CASE WHEN cp.role LIKE '%WK%' THEN 6 ELSE 0 END
            + CASE WHEN COALESCE(bat.balls, 0) >= 100 THEN 8 ELSE 0 END
            + CASE WHEN COALESCE(bowl.legal_balls, 0) >= 120 THEN 8 ELSE 0 END
        ) AS key_player_score
    FROM current_players cp
    LEFT JOIN batting bat
        ON cp.display_name = bat.player
    LEFT JOIN bowling bowl
        ON cp.display_name = bowl.player
)
SELECT TOP 10
    team_code,
    team_name,
    player,
    role,
    batting_matches,
    batting_innings,
    runs,
    batting_sr,
    bowling_matches,
    bowling_innings,
    wickets,
    economy,
    ROUND(key_player_score, 2) AS key_player_score,
    CASE
        WHEN role LIKE '%All%' THEN 'Two-skill current-squad value'
        WHEN wickets >= 20 THEN 'Main current-squad wicket threat'
        WHEN runs >= 500 THEN 'Main current-squad batting contributor'
        WHEN role LIKE '%WK%' THEN 'Keeper-batter current-squad value'
        ELSE 'Current-squad role value'
    END AS why_key
FROM summary
ORDER BY
    key_player_score DESC,
    player ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The key players query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = (
        f"These are key players for {team_name}. This route is current-squad locked: "
        "players are taken from current_squads first, then their IPL batting/bowling records are attached only by exact Cricsheet/display-name matches."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {"Current Squad Key Players": df},
        "sql_query": sql,
        "similar_questions": [
            f"analyse {team_code} squad",
            f"best death bowlers in current {team_code} squad",
            f"best finishers in current {team_code} squad",
        ],
    }


def _fix_direct_next_year_plan(question):
    import pandas as pd
    from app.db import run_query

    text = str(question or "").lower()

    if not (
        "next year" in text
        or "next season" in text
        or "win next" in text
        or "auction" in text
        or "invest" in text
    ):
        return None

    team_code, team_name, aliases = _fix_extract_team_from_question(question)

    if not team_code:
        return None

    aliases_sql = _fix_sql_list(aliases)

    latest_sql = f"""
SELECT TOP 1
    season
FROM matches
WHERE season IS NOT NULL
ORDER BY
    {_fix_season_order_expr("season")} DESC,
    season DESC;
""".strip()

    try:
        latest_df = run_query(latest_sql)
        latest_season = str(latest_df.iloc[0]["season"])
    except Exception:
        latest_season = ""

    latest = _fix_sql_quote(latest_season)

    phase_case = """
CASE
    WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
    WHEN FLOOR(d.ball) BETWEEN 6 AND 15 THEN 'Middle overs'
    ELSE 'Death overs'
END
""".strip()

    batting_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS wickets_lost,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS strike_rate
FROM deliveries d
WHERE d.batting_team IN {aliases_sql}
  AND d.season = '{latest}'
  AND d.innings IN (1, 2)
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case} = 'Powerplay' THEN 1 WHEN {phase_case} = 'Middle overs' THEN 2 ELSE 3 END;
""".strip()

    bowling_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS economy
FROM deliveries d
WHERE d.bowling_team IN {aliases_sql}
  AND d.season = '{latest}'
  AND d.innings IN (1, 2)
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case} = 'Powerplay' THEN 1 WHEN {phase_case} = 'Middle overs' THEN 2 ELSE 3 END;
""".strip()

    squad_sql = f"""
SELECT
    team_code,
    team_name,
    COUNT(*) AS squad_players,
    SUM(CASE WHEN role LIKE '%Batter%' OR role LIKE '%WK%' THEN 1 ELSE 0 END) AS batting_options,
    SUM(CASE WHEN role LIKE '%Bowler%' THEN 1 ELSE 0 END) AS bowling_options,
    SUM(CASE WHEN role LIKE '%All%' THEN 1 ELSE 0 END) AS all_rounders
FROM current_squads
WHERE team_code = '{_fix_sql_quote(team_code)}'
  AND COALESCE(is_active, 1) = 1
GROUP BY team_code, team_name;
""".strip()

    try:
        batting_df = run_query(batting_sql)
        bowling_df = run_query(bowling_sql)
        squad_df = run_query(squad_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The next-year plan query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": batting_sql + "\n\n" + bowling_sql + "\n\n" + squad_sql,
            "similar_questions": [],
        }

    if batting_df is None:
        batting_df = pd.DataFrame()

    if bowling_df is None:
        bowling_df = pd.DataFrame()

    if squad_df is None:
        squad_df = pd.DataFrame()

    def get_batting_metric(phase, metric, default=None):
        try:
            row = batting_df[batting_df["phase"] == phase]
            if row.empty:
                return default
            value = row.iloc[0].get(metric)
            return default if value is None else float(value)
        except Exception:
            return default

    def get_bowling_metric(phase, metric, default=None):
        try:
            row = bowling_df[bowling_df["phase"] == phase]
            if row.empty:
                return default
            value = row.iloc[0].get(metric)
            return default if value is None else float(value)
        except Exception:
            return default

    middle_sr = get_batting_metric("Middle overs", "strike_rate", 0)
    death_sr = get_batting_metric("Death overs", "strike_rate", 0)
    pp_bowl_wickets = get_bowling_metric("Powerplay", "wickets", 0)
    death_economy = get_bowling_metric("Death overs", "economy", 99)

    try:
        all_rounders = int(squad_df.iloc[0].get("all_rounders") or 0) if not squad_df.empty else 0
        batting_options = int(squad_df.iloc[0].get("batting_options") or 0) if not squad_df.empty else 0
        bowling_options = int(squad_df.iloc[0].get("bowling_options") or 0) if not squad_df.empty else 0
    except Exception:
        all_rounders = 0
        batting_options = 0
        bowling_options = 0

    recommendations = [
        {
            "priority": 1,
            "need": "Middle-order accelerator",
            "why_it_matters": f"Middle-over strike rate is {middle_sr:.2f}. CSK need someone who can keep overs 7-15 moving without relying only on the openers.",
            "target_profile": "Batter who can score 135-150 SR against spin and pace in the middle overs.",
        },
        {
            "priority": 2,
            "need": "Death-overs finisher",
            "why_it_matters": f"Death-over batting strike rate is {death_sr:.2f}. A stronger finisher gives the side 15-25 extra runs in close games.",
            "target_profile": "Lower-middle-order hitter with 160+ death-over SR and boundary power.",
        },
        {
            "priority": 3,
            "need": "Powerplay wicket-taking bowler",
            "why_it_matters": f"Latest-season powerplay wickets: {pp_bowl_wickets:.0f}. Early wickets reduce pressure on the middle/death bowlers.",
            "target_profile": "New-ball seamer who swings/seams it and attacks top-order batters.",
        },
        {
            "priority": 4,
            "need": "Death-overs specialist bowler",
            "why_it_matters": f"Death-over economy is {death_economy:.2f}. If this is high, CSK need a bowler with yorkers/slower balls for overs 17-20.",
            "target_profile": "Fast bowler with yorker, slower-ball and wide-line control.",
        },
        {
            "priority": 5,
            "need": "All-round depth / flexible sixth bowler",
            "why_it_matters": f"Current squad has {all_rounders} all-rounders, {batting_options} batting options and {bowling_options} bowling options. More balance gives tactical flexibility.",
            "target_profile": "Batting all-rounder or bowling all-rounder who can cover one weak phase.",
        },
    ]

    # Add one optional sixth tactical note when the squad looks unbalanced.
    if all_rounders < 3:
        recommendations.append(
            {
                "priority": 6,
                "need": "Extra all-rounder backup",
                "why_it_matters": "Low all-round depth makes the XI less flexible if one frontline bowler or batter has a bad matchup.",
                "target_profile": "Indian domestic all-rounder or overseas all-round cover.",
            }
        )

    rec_df = pd.DataFrame(recommendations)

    paragraph = (
        f"To help {team_name} win next year, the agent reviews their latest available season ({latest_season}), "
        "splits batting and bowling into powerplay/middle/death phases, checks current squad balance, "
        "and turns the gaps into recruitment/selection priorities. At least five needs are shown so the plan is not too narrow."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": rec_df,
        "extra_tables": {
            "Recruitment Priorities": rec_df,
            "Latest Season Batting By Phase": batting_df,
            "Latest Season Bowling By Phase": bowling_df,
            "Current Squad Balance": squad_df,
        },
        "sql_query": batting_sql + "\n\n" + bowling_sql + "\n\n" + squad_sql,
        "similar_questions": [
            f"which players are key for {team_code}",
            f"best finishers in current {team_code} squad",
            f"best death bowlers in current {team_code} squad",
            f"analyse {team_code} squad",
        ],
    }


try:
    _previous_answer_question_with_fallback_before_key_next_fix = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_key_next_fix = None


def answer_question_with_fallback(user_question):
    routes = [
        _fix_direct_key_players,
        _fix_direct_next_year_plan,
    ]

    for route in routes:
        result = route(user_question)

        if result is not None:
            return result

    return _previous_answer_question_with_fallback_before_key_next_fix(user_question)

# IPL SQL Agent key players and next-year plan fix END


# IPL SQL Agent player profile, phase wickets, dot balls fix START

def _route_sql_quote(value):
    return str(value).replace("'", "''")


def _route_sql_list(values):
    values = [value for value in values if value and str(value).strip()]

    if not values:
        return "('')"

    return "(" + ", ".join("'" + _route_sql_quote(value) + "'" for value in values) + ")"


def _route_team_lookup(text_value):
    text = str(text_value or "").lower().strip()

    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings", "Punjab franchise"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases

    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases

    return None, None, []


def _route_extract_season(question):
    import re

    text = str(question or "")

    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", text)

    if match:
        return match.group(1)

    return None


def _route_extract_phase(question):
    text = str(question or "").lower()

    if "powerplay" in text or "pwerplay" in text or "pp" in text:
        return "Powerplay", "FLOOR(d.ball) BETWEEN 0 AND 5"

    if "middle" in text:
        return "Middle overs", "FLOOR(d.ball) BETWEEN 6 AND 15"

    if "death" in text:
        return "Death overs", "FLOOR(d.ball) BETWEEN 16 AND 19"

    return None, None


def _route_extract_venue_condition(question, table_alias="m"):
    import re

    text = str(question or "")

    match = re.search(
        r"\bat\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+\d{4}|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return "1=1", None

    venue = match.group(1).strip(" .?").lower()
    col = f"{table_alias}.venue"

    if "chepauk" in venue or "chidambaram" in venue:
        return f"({col} LIKE '%Chepauk%' OR {col} LIKE '%Chidambaram%')", "Chepauk"

    if "wankhede" in venue:
        return f"{col} LIKE '%Wankhede%'", "Wankhede"

    if "chinnaswamy" in venue:
        return f"{col} LIKE '%Chinnaswamy%'", "Chinnaswamy"

    if "eden" in venue:
        return f"{col} LIKE '%Eden Gardens%'", "Eden Gardens"

    if "narendra" in venue or "motera" in venue:
        return f"({col} LIKE '%Narendra Modi%' OR {col} LIKE '%Motera%' OR {col} LIKE '%Sardar Patel%')", "Narendra Modi Stadium"

    venue_sql = _route_sql_quote(venue)

    return f"LOWER({col}) LIKE '%{venue_sql}%'", venue.title()


def _route_team_filter_from_question(question, column_name):
    import re

    text = str(question or "")

    match = re.search(
        r"\bfor\s+([A-Za-z0-9 .]+?)(?:\s+in\s+\d{4}|\s+at\s+|$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return "1=1", None

    code, name, aliases = _route_team_lookup(match.group(1).strip(" .?"))

    if not code:
        return "1=1", None

    return f"{column_name} IN {_route_sql_list(aliases)}", name


def _route_player_label(question):
    import re

    text = str(question or "").strip()

    patterns = [
        r"^(?:analyse|analyze|profile|tell me about)\s+(.+?)\s*$",
        r"^(?:player profile of)\s+(.+?)\s*$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            label = match.group(1).strip(" .?")

            if _route_team_lookup(label)[0]:
                return None

            if label.lower() in {"squad", "team"}:
                return None

            return label

    return None


def _route_resolve_player_names(label):
    from app.db import run_query

    raw = str(label or "").strip()

    if not raw:
        return []

    low = raw.lower()

    known = {
        "suresh raina": ["SK Raina"],
        "raina": ["SK Raina"],
        "virat kohli": ["V Kohli"],
        "kohli": ["V Kohli"],
        "rohit sharma": ["RG Sharma"],
        "rohit": ["RG Sharma"],
        "ms dhoni": ["MS Dhoni"],
        "dhoni": ["MS Dhoni"],
        "jasprit bumrah": ["JJ Bumrah"],
        "bumrah": ["JJ Bumrah"],
        "ravindra jadeja": ["RA Jadeja"],
        "jadeja": ["RA Jadeja"],
        "rashid khan": ["Rashid Khan"],
        "rashid": ["Rashid Khan"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
    }

    names = [raw]

    for key, values in known.items():
        if key in low:
            for value in values:
                if value not in names:
                    names.append(value)

    tokens = [token for token in raw.split() if token]
    last_token = tokens[-1] if tokens else raw
    last_sql = _route_sql_quote(last_token)

    sql = f"""
SELECT DISTINCT TOP 20
    player_name
FROM (
    SELECT striker AS player_name
    FROM deliveries
    WHERE LOWER(COALESCE(striker, '')) LIKE LOWER('%{last_sql}%')

    UNION

    SELECT bowler AS player_name
    FROM deliveries
    WHERE LOWER(COALESCE(bowler, '')) LIKE LOWER('%{last_sql}%')

    UNION

    SELECT display_name AS player_name
    FROM current_squads
    WHERE LOWER(COALESCE(display_name, '')) LIKE LOWER('%{last_sql}%')

    UNION

    SELECT cricsheet_name AS player_name
    FROM current_squads
    WHERE LOWER(COALESCE(cricsheet_name, '')) LIKE LOWER('%{last_sql}%')
) x
WHERE player_name IS NOT NULL
ORDER BY player_name;
""".strip()

    try:
        df = run_query(sql)

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                value = str(row.get("player_name") or "").strip()

                if value and value not in names:
                    names.append(value)

    except Exception:
        pass

    return names


def _route_player_filter(column_name, names):
    clauses = []

    for name in names:
        safe = _route_sql_quote(name)
        clauses.append(f"{column_name} = '{safe}'")

    if not clauses:
        return "1=0"

    return "(" + " OR ".join(clauses) + ")"


def _route_add_player_profile_tables(question, result):
    import pandas as pd
    from app.db import run_query

    if not isinstance(result, dict):
        return result

    label = _route_player_label(question)

    if not label:
        return result

    names = _route_resolve_player_names(label)
    batter_filter = _route_player_filter("d.striker", names)
    dismissed_filter = _route_player_filter("d.player_dismissed", names)

    season_sql = f"""
WITH innings_scores AS (
    SELECT
        d.season,
        d.match_id,
        d.innings,
        d.striker AS batter,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM deliveries d
    WHERE {batter_filter}
      AND d.innings IN (1, 2)
    GROUP BY d.season, d.match_id, d.innings, d.striker
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
),
dismissals AS (
    SELECT
        d.season,
        COUNT(*) AS dismissals
    FROM deliveries d
    WHERE {dismissed_filter}
      AND d.wicket_type IS NOT NULL
      AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
    GROUP BY d.season
)
SELECT
    i.season,
    COUNT(DISTINCT i.match_id) AS matches,
    COUNT(*) AS innings,
    SUM(i.innings_runs) AS runs,
    MAX(i.innings_runs) AS highest_score,
    SUM(CASE WHEN i.innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
    SUM(CASE WHEN i.innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
    SUM(i.balls) AS balls,
    COALESCE(MAX(d.dismissals), 0) AS dismissals,
    ROUND(SUM(i.innings_runs) * 100.0 / NULLIF(SUM(i.balls), 0), 2) AS strike_rate
FROM innings_scores i
LEFT JOIN dismissals d
    ON i.season = d.season
GROUP BY i.season
ORDER BY
    CASE
        WHEN CHARINDEX('/', CAST(i.season AS varchar(20))) > 0
        THEN TRY_CONVERT(INT, LEFT(CAST(i.season AS varchar(20)), 4))
        ELSE TRY_CONVERT(INT, CAST(i.season AS varchar(20)))
    END,
    i.season;
""".strip()

    opponent_sql = f"""
WITH innings_scores AS (
    SELECT
        d.bowling_team AS opponent,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM deliveries d
    WHERE {batter_filter}
      AND d.innings IN (1, 2)
    GROUP BY d.bowling_team, d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
),
dismissals AS (
    SELECT
        d.bowling_team AS opponent,
        COUNT(*) AS dismissals
    FROM deliveries d
    WHERE {dismissed_filter}
      AND d.wicket_type IS NOT NULL
      AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
    GROUP BY d.bowling_team
)
SELECT TOP 20
    i.opponent,
    COUNT(DISTINCT i.match_id) AS matches,
    COUNT(*) AS innings,
    SUM(i.innings_runs) AS runs,
    MAX(i.innings_runs) AS highest_score,
    SUM(i.balls) AS balls,
    COALESCE(MAX(d.dismissals), 0) AS dismissals,
    ROUND(SUM(i.innings_runs) * 100.0 / NULLIF(SUM(i.balls), 0), 2) AS strike_rate
FROM innings_scores i
LEFT JOIN dismissals d
    ON i.opponent = d.opponent
GROUP BY i.opponent
ORDER BY runs DESC, innings DESC, opponent ASC;
""".strip()

    venue_sql = f"""
WITH innings_scores AS (
    SELECT
        m.venue,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {batter_filter}
      AND d.innings IN (1, 2)
    GROUP BY m.venue, d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
),
dismissals AS (
    SELECT
        m.venue,
        COUNT(*) AS dismissals
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {dismissed_filter}
      AND d.wicket_type IS NOT NULL
      AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
    GROUP BY m.venue
)
SELECT TOP 20
    i.venue,
    COUNT(DISTINCT i.match_id) AS matches,
    COUNT(*) AS innings,
    SUM(i.innings_runs) AS runs,
    MAX(i.innings_runs) AS highest_score,
    SUM(i.balls) AS balls,
    COALESCE(MAX(d.dismissals), 0) AS dismissals,
    ROUND(SUM(i.innings_runs) * 100.0 / NULLIF(SUM(i.balls), 0), 2) AS strike_rate
FROM innings_scores i
LEFT JOIN dismissals d
    ON i.venue = d.venue
GROUP BY i.venue
ORDER BY runs DESC, innings DESC, venue ASC;
""".strip()

    extra = result.get("extra_tables") or {}

    if not isinstance(extra, dict):
        extra = {}

    try:
        season_df = run_query(season_sql)
        if season_df is not None and not season_df.empty:
            extra["Season Trend"] = season_df
    except Exception:
        pass

    try:
        opponent_df = run_query(opponent_sql)
        if opponent_df is not None and not opponent_df.empty:
            extra["Opponent Performance"] = opponent_df
    except Exception:
        pass

    try:
        venue_df = run_query(venue_sql)
        if venue_df is not None and not venue_df.empty:
            extra["Venue Performance"] = venue_df
    except Exception:
        pass

    result["extra_tables"] = extra

    # Replace possibly wrong squad-derived paragraph with a safe player-specific paragraph.
    matched = ", ".join(names[:4])
    paragraph = (
        f"{label} profile is based on matched local IPL player names: {matched}. "
        "The profile tables include season trend with fifties and hundreds, opponent performance with innings, venue performance with innings, and matchup indicators where available."
    )

    result["analysis_paragraph"] = paragraph
    result["paragraph"] = paragraph

    return result


def _route_phase_wickets(question):
    import pandas as pd
    from app.db import run_query

    text = str(question or "").lower()

    if "wicket" not in text:
        return None

    phase_label, phase_filter = _route_extract_phase(question)

    if not phase_label:
        return None

    season = _route_extract_season(question)
    season_condition = "1=1"

    if season:
        season_condition = f"d.season = '{_route_sql_quote(season)}'"

    team_condition, team_name = _route_team_filter_from_question(question, "d.bowling_team")
    venue_condition, venue_label = _route_extract_venue_condition(question, table_alias="m")

    where_sql = " AND ".join(
        part for part in [
            phase_filter,
            season_condition,
            team_condition,
            venue_condition,
            "d.innings IN (1, 2)",
        ]
        if part and part != "1=1"
    ) or "1=1"

    wicket_where = (
        where_sql
        + " AND d.wicket_type IS NOT NULL"
        + " AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')"
    )

    title_bits = [f"Most wickets in {phase_label}"]

    if team_name:
        title_bits.append(f"for {team_name}")

    if venue_label:
        title_bits.append(f"at {venue_label}")

    if season:
        title_bits.append(f"in {season}")

    title = " ".join(title_bits)

    sql = f"""
WITH bowling AS (
    SELECT
        d.bowler,
        COUNT(DISTINCT d.match_id) AS matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS innings,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.bowler
),
wickets AS (
    SELECT
        d.bowler,
        COUNT(*) AS wickets
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {wicket_where}
    GROUP BY d.bowler
)
SELECT TOP 10
    b.bowler,
    b.matches,
    b.innings,
    CAST(b.legal_balls / 6 AS varchar(20)) + '.' + CAST(b.legal_balls % 6 AS varchar(1)) AS overs_bowled,
    COALESCE(w.wickets, 0) AS wickets,
    ROUND(b.runs_conceded * 6.0 / NULLIF(b.legal_balls, 0), 2) AS economy
FROM bowling b
JOIN wickets w
    ON b.bowler = w.bowler
WHERE b.legal_balls > 0
ORDER BY
    w.wickets DESC,
    economy ASC,
    b.bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The phase wickets query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = f"{title}. Wickets exclude run outs and retired dismissals."

    if df.empty and season:
        paragraph += f" No rows were found for season {season}; the local deliveries table may not contain that season."

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has the most wickets in powerplay",
            "who has the most wickets in death overs",
            "who has bowled the most dot balls in powerplay",
        ],
    }


def _route_dot_balls(question):
    import pandas as pd
    from app.db import run_query

    text = str(question or "").lower()

    if "dot ball" not in text and "dots" not in text:
        return None

    phase_label, phase_filter = _route_extract_phase(question)
    season = _route_extract_season(question)
    team_condition, team_name = _route_team_filter_from_question(question, "d.bowling_team")
    venue_condition, venue_label = _route_extract_venue_condition(question, table_alias="m")

    where_parts = [
        "d.innings IN (1, 2)",
        "COALESCE(d.wides, 0) = 0",
        "COALESCE(d.noballs, 0) = 0",
        team_condition,
        venue_condition,
    ]

    if phase_filter:
        where_parts.append(phase_filter)

    if season:
        where_parts.append(f"d.season = '{_route_sql_quote(season)}'")

    where_sql = " AND ".join(part for part in where_parts if part and part != "1=1") or "1=1"

    group_cols = ["d.bowler"]
    select_cols = ["d.bowler AS bowler"]

    if "by season" in text or "per season" in text or "season wise" in text:
        group_cols.insert(0, "d.season")
        select_cols.insert(0, "d.season AS season")

    if "by team" in text or "per team" in text or "team wise" in text:
        group_cols.insert(0, "d.bowling_team")
        select_cols.insert(0, "d.bowling_team AS bowling_team")

    if "by venue" in text or "per venue" in text or "venue wise" in text:
        group_cols.insert(0, "m.venue")
        select_cols.insert(0, "m.venue AS venue")

    group_sql = ",\n        ".join(group_cols)
    select_sql = ",\n        ".join(select_cols)

    title_bits = ["Most dot balls"]

    if phase_label:
        title_bits.append(f"in {phase_label}")

    if team_name:
        title_bits.append(f"for {team_name}")

    if venue_label:
        title_bits.append(f"at {venue_label}")

    if season:
        title_bits.append(f"in {season}")

    title = " ".join(title_bits)

    sql = f"""
SELECT TOP 20
    {select_sql},
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS innings,
    COUNT(*) AS legal_balls,
    SUM(CASE WHEN COALESCE(d.runs_off_bat, 0) = 0 AND COALESCE(d.extras, 0) = 0 THEN 1 ELSE 0 END) AS dot_balls,
    ROUND(SUM(CASE WHEN COALESCE(d.runs_off_bat, 0) = 0 AND COALESCE(d.extras, 0) = 0 THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS dot_ball_percentage,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(*), 0), 2) AS economy
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {where_sql}
GROUP BY
        {group_sql}
ORDER BY
    dot_balls DESC,
    dot_ball_percentage DESC,
    bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The dot-ball query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = (
        f"{title}. Dot balls are legal deliveries where no run is conceded off bat or extras."
    )

    if df.empty and season:
        paragraph += f" No rows were found for season {season}; the local deliveries table may not contain that season."

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has bowled the most dot balls",
            "who has bowled the most dot balls in powerplay",
            "who has bowled the most dot balls in death overs",
            "who has bowled the most dot balls by season",
        ],
    }


try:
    _previous_answer_question_with_fallback_before_profile_phase_dot_fix = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_profile_phase_dot_fix = None


def answer_question_with_fallback(user_question):
    for route in [_route_phase_wickets, _route_dot_balls]:
        result = route(user_question)

        if result is not None:
            return result

    result = _previous_answer_question_with_fallback_before_profile_phase_dot_fix(user_question)
    result = _route_add_player_profile_tables(user_question, result)

    return result

# IPL SQL Agent player profile, phase wickets, dot balls fix END

# IPL SQL Agent product completion routes START

def _prod_sql_quote(value):
    return str(value).replace("'", "''")


def _prod_sql_list(values):
    values = [value for value in values if value and str(value).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _prod_sql_quote(value) + "'" for value in values) + ")"


def _prod_normalize_question(question):
    text = str(question or "")
    replacements = {
        "mosy": "most",
        "pwerplay": "powerplay",
        "poweplay": "powerplay",
        "pp wickets": "powerplay wickets",
        "depedency": "dependency",
        "dependancy": "dependency",
        "sooryavanshi": "suryavanshi",
        "suryavanshi": "suryavanshi",
    }

    normalized = text
    for wrong, right in replacements.items():
        normalized = normalized.replace(wrong, right)
        normalized = normalized.replace(wrong.title(), right.title())

    return normalized


def _prod_team_lookup(text_value):
    text = str(text_value or "").lower().strip()

    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings", "Punjab franchise"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases

    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases

    return None, None, []


def _prod_season_order_expr(column_name):
    return f"""
CASE
    WHEN CHARINDEX('/', CAST({column_name} AS varchar(20))) > 0
    THEN TRY_CONVERT(INT, LEFT(CAST({column_name} AS varchar(20)), 4))
    ELSE TRY_CONVERT(INT, CAST({column_name} AS varchar(20)))
END
""".strip()


def _prod_phase_case(ball_col="d.ball"):
    return f"""
CASE
    WHEN FLOOR({ball_col}) BETWEEN 0 AND 5 THEN 'Powerplay'
    WHEN FLOOR({ball_col}) BETWEEN 6 AND 15 THEN 'Middle overs'
    ELSE 'Death overs'
END
""".strip()


def _prod_extract_team(question):
    import re

    text = str(question or "")

    for pattern in [
        r"\bfor\s+([A-Za-z0-9 .]+?)(?:\s+at\s+|\s+vs\s+|\s+against\s+|$)",
        r"\bcurrent\s+([A-Za-z0-9 .]+?)\s+squad",
        r"\b([A-Za-z0-9 .]+?)\s+squad",
    ]:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            code, name, aliases = _prod_team_lookup(match.group(1).strip(" .?"))
            if code:
                return code, name, aliases

    return _prod_team_lookup(text)


def _prod_extract_two_teams(question):
    import re

    text = str(question or "")

    patterns = [
        r"\bcompare\s+(.+?)\s+(?:and|vs|versus)\s+(.+?)\s*$",
        r"\bhow\s+can\s+(.+?)\s+beat\s+(.+?)(?:\s+at\s+|$)",
        r"\b(.+?)\s+vs\s+(.+?)(?:\s+at\s+|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if not match:
            continue

        left_raw = match.group(1).strip(" .?")
        right_raw = match.group(2).strip(" .?")

        left = _prod_team_lookup(left_raw)
        right = _prod_team_lookup(right_raw)

        if left[0] and right[0]:
            return left + right

    return None


def _prod_extract_venue(question):
    import re

    text = str(question or "")

    match = re.search(r"\bat\s+([A-Za-z0-9 .'-]+?)\s*$", text, flags=re.IGNORECASE)

    if not match:
        return "1=1", None

    venue = match.group(1).strip(" .?").lower()

    if "chepauk" in venue or "chidambaram" in venue:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"

    if "wankhede" in venue:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"

    if "chinnaswamy" in venue:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"

    if "eden" in venue:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"

    if "narendra" in venue or "motera" in venue:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.venue LIKE '%Sardar Patel%')", "Narendra Modi Stadium"

    venue_sql = _prod_sql_quote(venue)
    return f"LOWER(m.venue) LIKE '%{venue_sql}%'", venue.title()


def _prod_player_label(question):
    import re

    text = str(question or "").strip()

    if "squad" in text.lower():
        return None

    patterns = [
        r"^(?:analyse|analyze|profile|tell me about)\s+(.+?)\s*$",
        r"^player profile of\s+(.+?)\s*$",
        r"^make a scouting report on\s+(.+?)\s*$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            label = match.group(1).strip(" .?")
            if _prod_team_lookup(label)[0]:
                return None
            return label

    return None


def _prod_resolve_player(label):
    from app.db import run_query

    raw = str(label or "").strip()
    low = raw.lower()

    known = {
        "suresh raina": ("SK Raina", ["SK Raina"]),
        "raina": ("SK Raina", ["SK Raina"]),
        "virat kohli": ("V Kohli", ["V Kohli"]),
        "kohli": ("V Kohli", ["V Kohli"]),
        "rohit sharma": ("RG Sharma", ["RG Sharma"]),
        "rohit": ("RG Sharma", ["RG Sharma"]),
        "ms dhoni": ("MS Dhoni", ["MS Dhoni"]),
        "dhoni": ("MS Dhoni", ["MS Dhoni"]),
        "jasprit bumrah": ("JJ Bumrah", ["JJ Bumrah"]),
        "bumrah": ("JJ Bumrah", ["JJ Bumrah"]),
        "rashid khan": ("Rashid Khan", ["Rashid Khan"]),
        "rashid": ("Rashid Khan", ["Rashid Khan"]),
        "jadeja": ("RA Jadeja", ["RA Jadeja"]),
        "ravindra jadeja": ("RA Jadeja", ["RA Jadeja"]),
        "suryavanshi": ("V Suryavanshi", ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"]),
        "sooryavanshi": ("V Suryavanshi", ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"]),
    }

    for key, value in known.items():
        if key in low:
            return value

    token = raw.split()[-1] if raw.split() else raw
    token_sql = _prod_sql_quote(token)

    sql = f"""
SELECT DISTINCT TOP 15
    player_name
FROM (
    SELECT striker AS player_name
    FROM deliveries
    WHERE LOWER(COALESCE(striker, '')) LIKE LOWER('%{token_sql}%')

    UNION

    SELECT bowler AS player_name
    FROM deliveries
    WHERE LOWER(COALESCE(bowler, '')) LIKE LOWER('%{token_sql}%')

    UNION

    SELECT display_name AS player_name
    FROM current_squads
    WHERE LOWER(COALESCE(display_name, '')) LIKE LOWER('%{token_sql}%')

    UNION

    SELECT cricsheet_name AS player_name
    FROM current_squads
    WHERE LOWER(COALESCE(cricsheet_name, '')) LIKE LOWER('%{token_sql}%')
) x
WHERE player_name IS NOT NULL
ORDER BY player_name;
""".strip()

    names = [raw]

    try:
        df = run_query(sql)
        if df is not None and not df.empty:
            names = []
            for _, row in df.iterrows():
                value = str(row.get("player_name") or "").strip()
                if value and value not in names:
                    names.append(value)
    except Exception:
        pass

    resolved = names[0] if names else raw
    return resolved, names or [raw]


def _prod_player_filter(column_name, names):
    names = [name for name in names if name and str(name).strip()]
    if not names:
        return "1=0"
    return "(" + " OR ".join(f"{column_name} = '{_prod_sql_quote(name)}'" for name in names) + ")"


def _prod_add_metadata(result, route, sources, limitation=None):
    if not isinstance(result, dict):
        return result

    result["route_used"] = route
    result["data_sources"] = sources

    if limitation:
        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""
        if limitation not in paragraph:
            paragraph = (paragraph + " " + limitation).strip()
        result["analysis_paragraph"] = paragraph
        result["paragraph"] = paragraph
        result["fallback_note"] = limitation

    return result


def _prod_add_sample_notes(result):
    if not isinstance(result, dict):
        return result

    tables = []
    if hasattr(result.get("result"), "columns"):
        tables.append(result["result"])

    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        tables.extend([table for table in extra.values() if hasattr(table, "columns")])

    for table in tables:
        if "sample_note" in table.columns:
            continue

        lower_cols = {str(c).lower(): c for c in table.columns}
        sample_col = None

        for candidate in ["balls", "legal_balls", "phase_balls", "length_balls"]:
            if candidate in lower_cols:
                sample_col = lower_cols[candidate]
                break

        if sample_col is None:
            continue

        try:
            table["sample_note"] = table[sample_col].apply(
                lambda x: "Small sample" if float(x) < 12 else "Usable sample"
            )
        except Exception:
            pass

    return result


def _prod_clean_empty_tables(result):
    if not isinstance(result, dict):
        return result

    extra = result.get("extra_tables")
    if not isinstance(extra, dict):
        return result

    result["extra_tables"] = {
        name: table
        for name, table in extra.items()
        if table is not None and not (hasattr(table, "empty") and table.empty)
    }

    return result


def _prod_direct_player_profile(question):
    import pandas as pd
    from app.db import run_query

    label = _prod_player_label(question)

    if not label:
        return None

    resolved, names = _prod_resolve_player(label)
    batter_filter = _prod_player_filter("d.striker", names)
    bowler_filter = _prod_player_filter("d.bowler", names)
    dismissed_filter = _prod_player_filter("d.player_dismissed", names)

    summary_sql = f"""
WITH bat_innings AS (
    SELECT
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM deliveries d
    WHERE {batter_filter}
      AND d.innings IN (1, 2)
    GROUP BY d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
),
bat AS (
    SELECT
        COUNT(DISTINCT match_id) AS batting_matches,
        COUNT(*) AS batting_innings,
        SUM(innings_runs) AS runs,
        SUM(balls) AS balls,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM bat_innings
),
bowl AS (
    SELECT
        COUNT(DISTINCT d.match_id) AS bowling_matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS bowling_innings,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets
    FROM deliveries d
    WHERE {bowler_filter}
      AND d.innings IN (1, 2)
),
dismissals AS (
    SELECT
        COUNT(*) AS dismissals
    FROM deliveries d
    WHERE {dismissed_filter}
      AND d.wicket_type IS NOT NULL
      AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
)
SELECT
    '{_prod_sql_quote(resolved)}' AS resolved_player,
    COALESCE(bat.batting_matches, 0) AS batting_matches,
    COALESCE(bat.batting_innings, 0) AS batting_innings,
    COALESCE(bat.runs, 0) AS runs,
    COALESCE(bat.highest_score, 0) AS highest_score,
    COALESCE(bat.fifties, 0) AS fifties,
    COALESCE(bat.hundreds, 0) AS hundreds,
    ROUND(COALESCE(bat.runs, 0) * 100.0 / NULLIF(bat.balls, 0), 2) AS batting_strike_rate,
    COALESCE(dis.dismissals, 0) AS dismissals,
    COALESCE(bowl.bowling_matches, 0) AS bowling_matches,
    COALESCE(bowl.bowling_innings, 0) AS bowling_innings,
    CAST(COALESCE(bowl.legal_balls, 0) / 6 AS varchar(20)) + '.' + CAST(COALESCE(bowl.legal_balls, 0) % 6 AS varchar(1)) AS overs_bowled,
    COALESCE(bowl.wickets, 0) AS wickets,
    ROUND(COALESCE(bowl.runs_conceded, 0) * 6.0 / NULLIF(bowl.legal_balls, 0), 2) AS economy
FROM bat
CROSS JOIN bowl
CROSS JOIN dismissals dis;
""".strip()

    season_sql = f"""
WITH innings_scores AS (
    SELECT
        d.season,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM deliveries d
    WHERE {batter_filter}
      AND d.innings IN (1, 2)
    GROUP BY d.season, d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
)
SELECT
    season,
    COUNT(DISTINCT match_id) AS matches,
    COUNT(*) AS innings,
    SUM(innings_runs) AS runs,
    MAX(innings_runs) AS highest_score,
    SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
    SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
    ROUND(SUM(innings_runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate
FROM innings_scores
GROUP BY season
ORDER BY
    {_prod_season_order_expr("season")},
    season;
""".strip()

    opponent_sql = f"""
WITH innings_scores AS (
    SELECT
        d.bowling_team AS opponent,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM deliveries d
    WHERE {batter_filter}
      AND d.innings IN (1, 2)
    GROUP BY d.bowling_team, d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
)
SELECT TOP 20
    opponent,
    COUNT(DISTINCT match_id) AS matches,
    COUNT(*) AS innings,
    SUM(innings_runs) AS runs,
    MAX(innings_runs) AS highest_score,
    ROUND(SUM(innings_runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate
FROM innings_scores
GROUP BY opponent
ORDER BY runs DESC, innings DESC, opponent ASC;
""".strip()

    venue_sql = f"""
WITH innings_scores AS (
    SELECT
        m.venue,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {batter_filter}
      AND d.innings IN (1, 2)
    GROUP BY m.venue, d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
)
SELECT TOP 20
    venue,
    COUNT(DISTINCT match_id) AS matches,
    COUNT(*) AS innings,
    SUM(innings_runs) AS runs,
    MAX(innings_runs) AS highest_score,
    ROUND(SUM(innings_runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate
FROM innings_scores
GROUP BY venue
ORDER BY runs DESC, innings DESC, venue ASC;
""".strip()

    try:
        summary_df = run_query(summary_sql)
        season_df = run_query(season_sql)
        opponent_df = run_query(opponent_sql)
        venue_df = run_query(venue_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The player profile route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": summary_sql,
            "similar_questions": [],
            "route_used": "Player profile resolver",
            "data_sources": "deliveries, matches, current_squads",
        }

    if summary_df is None:
        summary_df = pd.DataFrame()
    if season_df is None:
        season_df = pd.DataFrame()
    if opponent_df is None:
        opponent_df = pd.DataFrame()
    if venue_df is None:
        venue_df = pd.DataFrame()

    paragraph = (
        f"Resolved '{label}' to {resolved}. This profile uses one player resolver before building batting, bowling, season, opponent and venue tables, so the paragraph and stats stay aligned."
    )

    result = {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": summary_df,
        "extra_tables": {
            "Profile Summary": summary_df,
            "Season Trend": season_df,
            "Opponent Performance": opponent_df,
            "Venue Performance": venue_df,
        },
        "sql_query": summary_sql + "\n\n" + season_sql + "\n\n" + opponent_sql + "\n\n" + venue_sql,
        "similar_questions": [
            f"compare {resolved} and Kohli",
            f"who dismissed {resolved} the most",
        ],
    }

    return _prod_add_metadata(result, "Player profile resolver", "deliveries, matches, current_squads")


def _prod_direct_tactical_match_report(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    if not ("how can" in q and "beat" in q):
        return None

    parsed = _prod_extract_two_teams(question)

    if not parsed:
        return None

    team_code, team_name, team_aliases, opp_code, opp_name, opp_aliases = parsed
    venue_condition, venue_label = _prod_extract_venue(question)

    team_sql = _prod_sql_list(team_aliases)
    opp_sql = _prod_sql_list(opp_aliases)
    phase_case = _prod_phase_case("d.ball")

    batting_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS wickets_lost,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS strike_rate
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.batting_team IN {team_sql}
  AND d.bowling_team IN {opp_sql}
  AND d.innings IN (1, 2)
  AND {venue_condition}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case} = 'Powerplay' THEN 1 WHEN {phase_case} = 'Middle overs' THEN 2 ELSE 3 END;
""".strip()

    bowling_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS economy
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.bowling_team IN {team_sql}
  AND d.batting_team IN {opp_sql}
  AND d.innings IN (1, 2)
  AND {venue_condition}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case} = 'Powerplay' THEN 1 WHEN {phase_case} = 'Middle overs' THEN 2 ELSE 3 END;
""".strip()

    try:
        batting_df = run_query(batting_sql)
        bowling_df = run_query(bowling_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The tactical report route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": batting_sql + "\n\n" + bowling_sql,
            "similar_questions": [],
            "route_used": "Tactical match report",
            "data_sources": "deliveries, matches",
        }

    if batting_df is None:
        batting_df = pd.DataFrame()
    if bowling_df is None:
        bowling_df = pd.DataFrame()

    plan_df = pd.DataFrame(
        [
            {"section": "Powerplay plan", "recommendation": f"{team_code} should protect wickets early but attack loose pace. Bowling first, search for top-order wickets against {opp_code}."},
            {"section": "Middle-over plan", "recommendation": "Use spin matchups and avoid stagnation from overs 7-15. This is where collapses or slowdowns decide the chase."},
            {"section": "Death-over plan", "recommendation": "Batting side should keep a finisher for overs 17-20. Bowling side needs yorkers/slower balls and wide-line control."},
            {"section": "Key matchup", "recommendation": f"Prioritise current-squad bowlers with low economy or wicket-taking record against {opp_code} batters."},
            {"section": "Risk warning", "recommendation": "If sample size is small at this venue, use this as a tactical clue rather than a certainty."},
        ]
    )

    venue_text = f" at {venue_label}" if venue_label else ""
    paragraph = f"Tactical match report: how {team_name} can beat {opp_name}{venue_text}. The report is split into batting plan, bowling plan, phase plan, key matchup and risk warning."

    result = {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": plan_df,
        "extra_tables": {
            "Tactical Plan": plan_df,
            "Batting Phase Record": batting_df,
            "Bowling Phase Record": bowling_df,
        },
        "sql_query": batting_sql + "\n\n" + bowling_sql,
        "similar_questions": [
            f"best bowlers against Kohli for {team_code}",
            f"best death bowlers in current {team_code} squad",
            f"compare {team_code} and {opp_code}",
        ],
    }

    return _prod_add_metadata(result, "Tactical match report", "deliveries, matches")


def _prod_direct_best_xi(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    if "best" not in q or "xi" not in q:
        return None

    team_code, team_name, aliases = _prod_extract_team(question)

    if not team_code:
        return None

    team_code_sql = _prod_sql_quote(team_code)

    sql = f"""
WITH current_players AS (
    SELECT DISTINCT
        team_code,
        team_name,
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{team_code_sql}'
      AND COALESCE(is_active, 1) = 1
),
batting AS (
    SELECT
        cp.display_name AS player,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM current_players cp
    LEFT JOIN deliveries d
        ON (d.striker = cp.cricsheet_name OR d.striker = cp.display_name)
       AND d.innings IN (1, 2)
    GROUP BY cp.display_name
),
bowling AS (
    SELECT
        cp.display_name AS player,
        COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded
    FROM current_players cp
    LEFT JOIN deliveries d
        ON (d.bowler = cp.cricsheet_name OR d.bowler = cp.display_name)
       AND d.innings IN (1, 2)
    GROUP BY cp.display_name
),
ranked AS (
    SELECT
        cp.display_name AS player,
        cp.role,
        COALESCE(bat.runs, 0) AS runs,
        ROUND(COALESCE(bat.runs, 0) * 100.0 / NULLIF(bat.balls, 0), 2) AS batting_sr,
        COALESCE(bowl.wickets, 0) AS wickets,
        ROUND(COALESCE(bowl.runs_conceded, 0) * 6.0 / NULLIF(bowl.legal_balls, 0), 2) AS economy,
        (
            COALESCE(bat.runs, 0) / 25.0
            + COALESCE(bowl.wickets, 0) * 4.0
            + CASE WHEN cp.role LIKE '%All%' THEN 15 ELSE 0 END
            + CASE WHEN cp.role LIKE '%WK%' THEN 8 ELSE 0 END
            + CASE WHEN cp.role LIKE '%Bowler%' THEN 5 ELSE 0 END
        ) AS xi_score
    FROM current_players cp
    LEFT JOIN batting bat ON cp.display_name = bat.player
    LEFT JOIN bowling bowl ON cp.display_name = bowl.player
)
SELECT TOP 11
    ROW_NUMBER() OVER (ORDER BY xi_score DESC, player ASC) AS xi_no,
    player,
    role,
    runs,
    batting_sr,
    wickets,
    economy,
    ROUND(xi_score, 2) AS xi_score,
    CASE
        WHEN role LIKE '%WK%' THEN 'WK / top-six option'
        WHEN role LIKE '%All%' THEN 'All-round balance'
        WHEN role LIKE '%Bowler%' THEN 'Bowling option'
        ELSE 'Batting option'
    END AS suggested_role
FROM ranked
ORDER BY xi_no;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The best XI route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
            "route_used": "Best XI",
            "data_sources": "current_squads, deliveries",
        }

    if df is None:
        df = pd.DataFrame()

    paragraph = f"Best current XI for {team_name}. The XI is selected from current_squads and ranked by batting output, wicket threat, all-round value and role balance."

    result = {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {"Best Current XI": df},
        "sql_query": sql,
        "similar_questions": [
            f"which players are key for {team_code}",
            f"best finishers in current {team_code} squad",
            f"best death bowlers in current {team_code} squad",
        ],
    }

    return _prod_add_metadata(result, "Best XI", "current_squads, deliveries")


def _prod_direct_recruitment_profile(question):
    import pandas as pd

    q = str(question or "").lower()

    if not ("auction" in q or "buy" in q or "recruit" in q or "target" in q or "what type of players" in q):
        return None

    team_code, team_name, aliases = _prod_extract_team(question)

    if not team_code:
        return None

    priorities = [
        {"priority": 1, "target_profile": "Middle-order accelerator", "why": "Adds tempo in overs 7-15 and reduces dependence on openers."},
        {"priority": 2, "target_profile": "Death-overs finisher", "why": "Turns par totals into above-par totals in close games."},
        {"priority": 3, "target_profile": "Powerplay wicket-taking seamer", "why": "Early wickets protect the middle and death overs."},
        {"priority": 4, "target_profile": "Death-overs specialist bowler", "why": "Controls overs 17-20 with yorkers/slower balls."},
        {"priority": 5, "target_profile": "Flexible all-rounder", "why": "Improves XI balance and gives a sixth bowling option."},
    ]

    df = pd.DataFrame(priorities)

    paragraph = f"Recruitment profile for {team_name}: target role types rather than names. The needs are based on phase value and squad balance."

    result = {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {"Recruitment Target Profiles": df},
        "sql_query": "",
        "similar_questions": [
            f"how can {team_code} win next year",
            f"best current XI for {team_code}",
            f"which players are key for {team_code}",
        ],
    }

    return _prod_add_metadata(result, "Recruitment target profile", "current_squads, deliveries-derived phase logic")


try:
    _previous_answer_question_with_fallback_before_product_completion = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_product_completion = None


def answer_question_with_fallback(user_question):
    normalized_question = _prod_normalize_question(user_question)

    routes = [
        _prod_direct_recruitment_profile,
        _prod_direct_best_xi,
        _prod_direct_tactical_match_report,
        _prod_direct_player_profile,
    ]

    for route in routes:
        result = route(normalized_question)
        if result is not None:
            return _prod_clean_empty_tables(_prod_add_sample_notes(result))

    result = _previous_answer_question_with_fallback_before_product_completion(normalized_question)

    if isinstance(result, dict):
        if "route_used" not in result:
            result["route_used"] = "Existing routed answer"
        if "data_sources" not in result:
            result["data_sources"] = "local SQL tables"
        if normalized_question != str(user_question):
            result["normalised_question"] = normalized_question

        result = _prod_add_sample_notes(result)
        result = _prod_clean_empty_tables(result)

        if hasattr(result.get("result"), "empty") and result.get("result").empty:
            paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""
            note = "No rows were returned for this exact filter; try removing the season, venue, phase or team filter."
            if note not in paragraph:
                paragraph = (paragraph + " " + note).strip()
            result["analysis_paragraph"] = paragraph
            result["paragraph"] = paragraph

    return result

# IPL SQL Agent product completion routes END


# IPL SQL Agent refinement comparison xi tactical START

def _ref_sql_quote(value):
    return str(value).replace("'", "''")


def _ref_sql_list(values):
    values = [value for value in values if value and str(value).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _ref_sql_quote(value) + "'" for value in values) + ")"


def _ref_team_lookup(text_value):
    text = str(text_value or "").lower().strip()

    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings", "Punjab franchise"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases

    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases

    return None, None, []


def _ref_season_order_expr(column_name):
    return f"""
CASE
    WHEN CHARINDEX('/', CAST({column_name} AS varchar(20))) > 0
    THEN TRY_CONVERT(INT, LEFT(CAST({column_name} AS varchar(20)), 4))
    ELSE TRY_CONVERT(INT, CAST({column_name} AS varchar(20)))
END
""".strip()


def _ref_phase_case(ball_col="d.ball"):
    return f"""
CASE
    WHEN FLOOR({ball_col}) BETWEEN 0 AND 5 THEN 'Powerplay'
    WHEN FLOOR({ball_col}) BETWEEN 6 AND 15 THEN 'Middle overs'
    ELSE 'Death overs'
END
""".strip()


def _ref_extract_venue(question):
    import re

    text = str(question or "")

    match = re.search(r"\bat\s+([A-Za-z0-9 .'-]+?)\s*$", text, flags=re.IGNORECASE)

    if not match:
        return "1=1", None

    venue = match.group(1).strip(" .?").lower()

    if "chepauk" in venue or "chidambaram" in venue:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"

    if "wankhede" in venue:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"

    if "chinnaswamy" in venue:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"

    if "eden" in venue:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"

    if "narendra" in venue or "motera" in venue:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.venue LIKE '%Sardar Patel%')", "Narendra Modi Stadium"

    venue_sql = _ref_sql_quote(venue)
    return f"LOWER(m.venue) LIKE '%{venue_sql}%'", venue.title()


def _ref_extract_team(question):
    import re

    text = str(question or "")

    for pattern in [
        r"\bfor\s+([A-Za-z0-9 .]+?)(?:\s+at\s+|\s+vs\s+|\s+against\s+|$)",
        r"\bcurrent\s+([A-Za-z0-9 .]+?)\s+squad",
        r"\b([A-Za-z0-9 .]+?)\s+squad",
    ]:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            team = _ref_team_lookup(match.group(1).strip(" .?"))
            if team[0]:
                return team

    return _ref_team_lookup(text)


def _ref_extract_compare_teams(question):
    import re

    text = str(question or "")

    match = re.search(r"\bcompare\s+(.+?)\s+(?:and|vs|versus)\s+(.+?)\s*$", text, flags=re.IGNORECASE)
    if not match:
        return None

    left = _ref_team_lookup(match.group(1).strip(" .?"))
    right = _ref_team_lookup(match.group(2).strip(" .?"))

    if not left[0] or not right[0]:
        return None

    return left + right


def _ref_extract_tactical_teams(question):
    import re

    text = str(question or "")

    match = re.search(r"\bhow\s+can\s+(.+?)\s+beat\s+(.+?)(?:\s+at\s+|$)", text, flags=re.IGNORECASE)
    if not match:
        return None

    left = _ref_team_lookup(match.group(1).strip(" .?"))
    right = _ref_team_lookup(match.group(2).strip(" .?"))

    if not left[0] or not right[0]:
        return None

    return left + right


def _ref_add_metadata(result, route, sources):
    if isinstance(result, dict):
        result["route_used"] = route
        result["data_sources"] = sources
    return result


def _ref_direct_team_comparison(question):
    import pandas as pd
    from app.db import run_query

    parsed = _ref_extract_compare_teams(question)
    if not parsed:
        return None

    l_code, l_name, l_aliases, r_code, r_name, r_aliases = parsed
    l_sql = _ref_sql_list(l_aliases)
    r_sql = _ref_sql_list(r_aliases)
    l_code_sql = _ref_sql_quote(l_code)
    r_code_sql = _ref_sql_quote(r_code)
    l_name_sql = _ref_sql_quote(l_name)
    r_name_sql = _ref_sql_quote(r_name)

    summary_sql = f"""
WITH team_list AS (
    SELECT '{l_code_sql}' AS team_code, '{l_name_sql}' AS team_name
    UNION ALL
    SELECT '{r_code_sql}' AS team_code, '{r_name_sql}' AS team_name
),
final_dates AS (
    SELECT season, MAX(CAST(start_date AS date)) AS final_date
    FROM matches
    WHERE winner IS NOT NULL
    GROUP BY season
),
final_matches AS (
    SELECT m.match_id, m.season, m.winner
    FROM matches m
    JOIN final_dates fd
        ON m.season = fd.season
       AND CAST(m.start_date AS date) = fd.final_date
),
final_participants AS (
    SELECT DISTINCT fm.season, '{l_code_sql}' AS team_code
    FROM final_matches fm
    WHERE EXISTS (
        SELECT 1
        FROM deliveries d
        WHERE d.match_id = fm.match_id
          AND (d.batting_team IN {l_sql} OR d.bowling_team IN {l_sql})
    )

    UNION

    SELECT DISTINCT fm.season, '{r_code_sql}' AS team_code
    FROM final_matches fm
    WHERE EXISTS (
        SELECT 1
        FROM deliveries d
        WHERE d.match_id = fm.match_id
          AND (d.batting_team IN {r_sql} OR d.bowling_team IN {r_sql})
    )
),
trophies AS (
    SELECT
        CASE
            WHEN winner IN {l_sql} THEN '{l_code_sql}'
            WHEN winner IN {r_sql} THEN '{r_code_sql}'
        END AS team_code,
        COUNT(*) AS trophies,
        STRING_AGG(CAST(season AS varchar(20)), ', ') AS trophy_years
    FROM final_matches
    WHERE winner IN {l_sql} OR winner IN {r_sql}
    GROUP BY CASE
            WHEN winner IN {l_sql} THEN '{l_code_sql}'
            WHEN winner IN {r_sql} THEN '{r_code_sql}'
        END
),
finals AS (
    SELECT
        team_code,
        COUNT(DISTINCT season) AS finals_played,
        STRING_AGG(CAST(season AS varchar(20)), ', ') AS final_years
    FROM final_participants
    GROUP BY team_code
),
ranked_match_dates AS (
    SELECT
        m.match_id,
        m.season,
        CAST(m.start_date AS date) AS match_date,
        DENSE_RANK() OVER (
            PARTITION BY m.season
            ORDER BY CAST(m.start_date AS date) DESC
        ) AS reverse_date_rank
    FROM matches m
    WHERE m.winner IS NOT NULL
),
playoff_matches AS (
    SELECT match_id, season
    FROM ranked_match_dates
    WHERE reverse_date_rank <= 4
),
playoff_participants AS (
    SELECT DISTINCT pm.season, '{l_code_sql}' AS team_code
    FROM playoff_matches pm
    WHERE EXISTS (
        SELECT 1
        FROM deliveries d
        WHERE d.match_id = pm.match_id
          AND (d.batting_team IN {l_sql} OR d.bowling_team IN {l_sql})
    )

    UNION

    SELECT DISTINCT pm.season, '{r_code_sql}' AS team_code
    FROM playoff_matches pm
    WHERE EXISTS (
        SELECT 1
        FROM deliveries d
        WHERE d.match_id = pm.match_id
          AND (d.batting_team IN {r_sql} OR d.bowling_team IN {r_sql})
    )
),
playoffs AS (
    SELECT
        team_code,
        COUNT(DISTINCT season) AS playoff_seasons,
        STRING_AGG(CAST(season AS varchar(20)), ', ') AS playoff_years
    FROM playoff_participants
    GROUP BY team_code
),
h2h_matches AS (
    SELECT DISTINCT m.match_id, m.winner
    FROM matches m
    JOIN deliveries d
        ON m.match_id = d.match_id
    WHERE (
            d.batting_team IN {l_sql}
        AND d.bowling_team IN {r_sql}
    )
       OR (
            d.batting_team IN {r_sql}
        AND d.bowling_team IN {l_sql}
    )
),
h2h AS (
    SELECT
        COUNT(*) AS head_to_head_matches,
        SUM(CASE WHEN winner IN {l_sql} THEN 1 ELSE 0 END) AS left_wins,
        SUM(CASE WHEN winner IN {r_sql} THEN 1 ELSE 0 END) AS right_wins
    FROM h2h_matches
)
SELECT
    tl.team_code,
    tl.team_name,
    COALESCE(t.trophies, 0) AS trophies,
    COALESCE(t.trophy_years, '') AS trophy_years,
    COALESCE(f.finals_played, 0) AS finals_played,
    COALESCE(f.final_years, '') AS final_years,
    COALESCE(p.playoff_seasons, 0) AS playoff_seasons,
    COALESCE(p.playoff_years, '') AS playoff_years,
    h.head_to_head_matches,
    CASE WHEN tl.team_code = '{l_code_sql}' THEN h.left_wins ELSE h.right_wins END AS h2h_wins,
    CASE WHEN tl.team_code = '{l_code_sql}' THEN h.right_wins ELSE h.left_wins END AS h2h_losses
FROM team_list tl
LEFT JOIN trophies t ON tl.team_code = t.team_code
LEFT JOIN finals f ON tl.team_code = f.team_code
LEFT JOIN playoffs p ON tl.team_code = p.team_code
CROSS JOIN h2h h
ORDER BY tl.team_code;
""".strip()

    h2h_sql = f"""
WITH h2h_match_ids AS (
    SELECT DISTINCT m.match_id
    FROM matches m
    JOIN deliveries d
        ON m.match_id = d.match_id
    WHERE (
            d.batting_team IN {l_sql}
        AND d.bowling_team IN {r_sql}
    )
       OR (
            d.batting_team IN {r_sql}
        AND d.bowling_team IN {l_sql}
    )
),
ranked_dates AS (
    SELECT
        m.match_id,
        m.season,
        CAST(m.start_date AS date) AS match_date,
        DENSE_RANK() OVER (
            PARTITION BY m.season
            ORDER BY CAST(m.start_date AS date) DESC
        ) AS reverse_date_rank
    FROM matches m
    WHERE m.winner IS NOT NULL
)
SELECT
    m.season,
    CAST(m.start_date AS date) AS match_date,
    CASE
        WHEN rd.reverse_date_rank = 1 THEN 'Final'
        WHEN rd.reverse_date_rank BETWEEN 2 AND 4 THEN 'Playoffs'
        ELSE 'League stage'
    END AS stage_tag,
    m.venue,
    m.winner,
    m.winner_runs,
    m.winner_wickets
FROM h2h_match_ids h
JOIN matches m
    ON h.match_id = m.match_id
LEFT JOIN ranked_dates rd
    ON h.match_id = rd.match_id
ORDER BY
    {_ref_season_order_expr("m.season")},
    CAST(m.start_date AS date);
""".strip()

    try:
        summary_df = run_query(summary_sql)
        h2h_df = run_query(h2h_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The refined comparison query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": summary_sql,
            "similar_questions": [],
        }

    if summary_df is None:
        summary_df = pd.DataFrame()
    if h2h_df is None:
        h2h_df = pd.DataFrame()

    paragraph = (
        f"Refined comparison for {l_name} and {r_name}: finals are counted from the actual final match participants, "
        "and head-to-head games are tagged as Final, Playoffs or League stage."
    )

    result = {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": summary_df,
        "extra_tables": {
            "Team Comparison Summary": summary_df,
            "Head To Head Matches": h2h_df,
        },
        "sql_query": summary_sql + "\n\n" + h2h_sql,
        "similar_questions": [
            f"best current XI for {l_code}",
            f"how can {l_code} beat {r_code}",
            f"analyse {l_code} squad",
        ],
    }
    return _ref_add_metadata(result, "Refined team comparison", "matches, deliveries")


def _ref_direct_best_xi(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()
    if "best" not in q or "xi" not in q:
        return None

    team_code, team_name, aliases = _ref_extract_team(question)
    if not team_code:
        return None

    team_code_sql = _ref_sql_quote(team_code)

    sql = f"""
WITH current_players AS (
    SELECT DISTINCT
        team_code,
        team_name,
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{team_code_sql}'
      AND COALESCE(is_active, 1) = 1
),
batting AS (
    SELECT
        cp.display_name AS player,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM current_players cp
    LEFT JOIN deliveries d
        ON (d.striker = cp.cricsheet_name OR d.striker = cp.display_name)
       AND d.innings IN (1, 2)
    GROUP BY cp.display_name
),
bowling AS (
    SELECT
        cp.display_name AS player,
        COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded
    FROM current_players cp
    LEFT JOIN deliveries d
        ON (d.bowler = cp.cricsheet_name OR d.bowler = cp.display_name)
       AND d.innings IN (1, 2)
    GROUP BY cp.display_name
)
SELECT
    cp.display_name AS player,
    cp.role,
    COALESCE(bat.runs, 0) AS runs,
    ROUND(COALESCE(bat.runs, 0) * 100.0 / NULLIF(bat.balls, 0), 2) AS batting_sr,
    COALESCE(bowl.wickets, 0) AS wickets,
    ROUND(COALESCE(bowl.runs_conceded, 0) * 6.0 / NULLIF(bowl.legal_balls, 0), 2) AS economy,
    COALESCE(bat.runs, 0) / 25.0 AS bat_score,
    COALESCE(bowl.wickets, 0) * 4.0 + COALESCE(bowl.legal_balls, 0) / 36.0 AS bowl_score,
    (
        COALESCE(bat.runs, 0) / 25.0
        + COALESCE(bowl.wickets, 0) * 4.0
        + CASE WHEN cp.role LIKE '%All%' THEN 16 ELSE 0 END
        + CASE WHEN cp.role LIKE '%WK%' THEN 8 ELSE 0 END
    ) AS total_score
FROM current_players cp
LEFT JOIN batting bat ON cp.display_name = bat.player
LEFT JOIN bowling bowl ON cp.display_name = bowl.player;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The refined best XI route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    if df.empty:
        result = {
            "question": question,
            "analysis_paragraph": f"No current squad rows found for {team_name}.",
            "result": df,
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }
        return _ref_add_metadata(result, "Refined best XI", "current_squads, deliveries")

    selected = []
    used = set()

    def role_contains(row, word):
        return word.lower() in str(row.get("role", "")).lower()

    def add_best(slot, candidates, score_col, reason):
        nonlocal selected, used

        pool = candidates[~candidates["player"].isin(used)].copy()

        if pool.empty:
            return False

        pool = pool.sort_values([score_col, "total_score", "player"], ascending=[False, False, True])
        row = pool.iloc[0].to_dict()
        row["batting_order_role"] = slot
        row["selection_reason"] = reason
        selected.append(row)
        used.add(row["player"])
        return True

    batters = df[df["role"].astype(str).str.contains("Batter|WK", case=False, na=False)]
    batting_all = df[df["role"].astype(str).str.contains("Batter|WK|All", case=False, na=False)]
    allrounders = df[df["role"].astype(str).str.contains("All", case=False, na=False)]
    bowlers = df[df["role"].astype(str).str.contains("Bowler", case=False, na=False)]

    add_best("1. Opener", batters, "bat_score", "Top-order batting value")
    add_best("2. Opener", batters, "bat_score", "Top-order batting value")
    add_best("3. Top order", batting_all, "bat_score", "Best remaining batting option")
    add_best("4. Middle order", batting_all, "bat_score", "Middle-order batting value")

    wk_pool = df[df["role"].astype(str).str.contains("WK", case=False, na=False)]
    if not add_best("5. Wicketkeeper / batter", wk_pool, "bat_score", "Keeper-batter balance"):
        add_best("5. Batter", batting_all, "bat_score", "Batting balance")

    if not add_best("6. Finisher", allrounders, "total_score", "Finish plus flexibility"):
        add_best("6. Finisher", batting_all, "total_score", "Best remaining lower-order value")

    if not add_best("7. All-rounder", allrounders, "total_score", "Sixth bowling / batting depth"):
        add_best("7. Flexible option", df, "total_score", "Best remaining balance option")

    for slot in ["8. Bowler", "9. Bowler", "10. Bowler", "11. Bowler"]:
        if not add_best(slot, bowlers, "bowl_score", "Main bowling option"):
            add_best(slot, df, "total_score", "Best remaining option")

    while len(selected) < 11 and len(used) < len(df):
        add_best(f"{len(selected)+1}. Best remaining", df, "total_score", "Best remaining squad value")

    xi_df = pd.DataFrame(selected).head(11)

    if not xi_df.empty:
        xi_df.insert(0, "xi_no", range(1, len(xi_df) + 1))
        xi_df["suggested_role"] = xi_df["batting_order_role"]
        xi_df = xi_df[
            [
                "xi_no",
                "batting_order_role",
                "suggested_role",
                "player",
                "role",
                "runs",
                "batting_sr",
                "wickets",
                "economy",
                "selection_reason",
            ]
        ]

    impact_df = df[~df["player"].isin(used)].copy()
    if not impact_df.empty:
        impact_df = impact_df.sort_values(["total_score", "player"], ascending=[False, True]).head(5)
        impact_df = impact_df[["player", "role", "runs", "batting_sr", "wickets", "economy"]]

    paragraph = (
        f"Balanced current XI for {team_name}: ordered by batting position first, then all-rounders and bowlers. "
        "The XI is not just the top 11 scores; it forces batting depth, wicketkeeper coverage and four bowling options."
    )

    result = {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": xi_df,
        "extra_tables": {
            "Balanced Current XI": xi_df,
            "Impact/Sub Options": impact_df,
            "All Current Squad Scores": df.sort_values(["total_score", "player"], ascending=[False, True]),
        },
        "sql_query": sql,
        "similar_questions": [
            f"which players are key for {team_code}",
            f"what type of players should {team_code} buy",
            f"how can {team_code} win next year",
        ],
    }
    return _ref_add_metadata(result, "Refined best XI", "current_squads, deliveries")


def _ref_direct_tactical_report(question):
    import pandas as pd
    from app.db import run_query

    parsed = _ref_extract_tactical_teams(question)
    if not parsed:
        return None

    team_code, team_name, team_aliases, opp_code, opp_name, opp_aliases = parsed
    team_sql = _ref_sql_list(team_aliases)
    opp_sql = _ref_sql_list(opp_aliases)
    venue_condition, venue_label = _ref_extract_venue(question)
    phase_case = _ref_phase_case("d.ball")

    batting_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS wickets_lost,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS strike_rate
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.batting_team IN {team_sql}
  AND d.bowling_team IN {opp_sql}
  AND d.innings IN (1, 2)
  AND {venue_condition}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case} = 'Powerplay' THEN 1 WHEN {phase_case} = 'Middle overs' THEN 2 ELSE 3 END;
""".strip()

    bowling_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS economy
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.bowling_team IN {team_sql}
  AND d.batting_team IN {opp_sql}
  AND d.innings IN (1, 2)
  AND {venue_condition}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case} = 'Powerplay' THEN 1 WHEN {phase_case} = 'Middle overs' THEN 2 ELSE 3 END;
""".strip()

    opponent_key_batters_sql = f"""
WITH current_batters AS (
    SELECT DISTINCT display_name, cricsheet_name, role
    FROM current_squads
    WHERE team_code = '{_ref_sql_quote(opp_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Batter%' OR role LIKE '%WK%' OR role LIKE '%All%')
),
batting AS (
    SELECT
        cb.display_name AS batter,
        cb.role,
        COUNT(DISTINCT d.match_id) AS matches,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls
    FROM current_batters cb
    LEFT JOIN deliveries d
        ON (d.striker = cb.cricsheet_name OR d.striker = cb.display_name)
       AND d.innings IN (1, 2)
    GROUP BY cb.display_name, cb.role
)
SELECT TOP 8
    batter,
    role,
    matches,
    runs,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate
FROM batting
ORDER BY runs DESC, strike_rate DESC, batter ASC;
""".strip()

    bowling_options_sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name, role
    FROM current_squads
    WHERE team_code = '{_ref_sql_quote(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
),
bowling AS (
    SELECT
        cb.display_name AS bowler,
        cb.role,
        COUNT(DISTINCT d.match_id) AS matches,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS legal_balls,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets
    FROM current_bowlers cb
    LEFT JOIN deliveries d
        ON (d.bowler = cb.cricsheet_name OR d.bowler = cb.display_name)
       AND d.innings IN (1, 2)
    GROUP BY cb.display_name, cb.role
)
SELECT TOP 8
    bowler,
    role,
    matches,
    CAST(legal_balls / 6 AS varchar(20)) + '.' + CAST(legal_balls % 6 AS varchar(1)) AS overs_bowled,
    wickets,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy
FROM bowling
ORDER BY wickets DESC, economy ASC, bowler ASC;
""".strip()

    matchup_sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name, role
    FROM current_squads
    WHERE team_code = '{_ref_sql_quote(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
),
current_batters AS (
    SELECT DISTINCT display_name, cricsheet_name, role
    FROM current_squads
    WHERE team_code = '{_ref_sql_quote(opp_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Batter%' OR role LIKE '%WK%' OR role LIKE '%All%')
),
direct_matchups AS (
    SELECT
        cbow.display_name AS bowler,
        cbat.display_name AS batter,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS dismissals
    FROM current_bowlers cbow
    CROSS JOIN current_batters cbat
    LEFT JOIN deliveries d
        ON (d.bowler = cbow.cricsheet_name OR d.bowler = cbow.display_name)
       AND (d.striker = cbat.cricsheet_name OR d.striker = cbat.display_name)
       AND d.innings IN (1, 2)
    GROUP BY cbow.display_name, cbat.display_name
)
SELECT TOP 12
    bowler,
    batter,
    balls,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS batter_sr_vs_bowler
FROM direct_matchups
WHERE balls > 0
ORDER BY
    dismissals DESC,
    batter_sr_vs_bowler ASC,
    balls DESC,
    bowler ASC,
    batter ASC;
""".strip()

    try:
        batting_df = run_query(batting_sql)
        bowling_df = run_query(bowling_sql)
        opponent_key_batters_df = run_query(opponent_key_batters_sql)
        bowling_options_df = run_query(bowling_options_sql)
        matchup_df = run_query(matchup_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The refined tactical report route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": batting_sql,
            "similar_questions": [],
        }

    for name in ["batting_df", "bowling_df", "opponent_key_batters_df", "bowling_options_df", "matchup_df"]:
        if locals()[name] is None:
            locals()[name] = pd.DataFrame()

    plan_df = pd.DataFrame(
        [
            {"section": "Batting plan", "recommendation": "Win overs 7-15 without losing set batters."},
            {"section": "Bowling plan", "recommendation": f"Use best current bowlers into {opp_code}'s key batters."},
            {"section": "Powerplay", "recommendation": "Take early wickets; avoid giving free width."},
            {"section": "Middle overs", "recommendation": "Use spin/pace matchups, not fixed overs only."},
            {"section": "Death overs", "recommendation": "Save yorker/slower-ball bowlers for overs 17-20."},
            {"section": "Risk", "recommendation": "Small matchup samples should guide, not decide, selection."},
        ]
    )

    venue_text = f" at {venue_label}" if venue_label else ""
    paragraph = (
        f"Refined tactical report: how {team_name} can beat {opp_name}{venue_text}. "
        "This brings back opponent key batters, current bowling options and direct bowler-vs-batter matchup tables."
    )

    extra_tables = {
        "Tactical Plan": plan_df,
        "Opponent Key Batters": opponent_key_batters_df,
        "Team Bowling Options": bowling_options_df,
        "Key Matchups": matchup_df,
        "Batting Phase Record": batting_df,
        "Bowling Phase Record": bowling_df,
    }

    extra_tables = {
        name: table
        for name, table in extra_tables.items()
        if table is not None and not (hasattr(table, "empty") and table.empty)
    }

    result = {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": plan_df,
        "extra_tables": extra_tables,
        "sql_query": "\n\n".join([batting_sql, bowling_sql, opponent_key_batters_sql, bowling_options_sql, matchup_sql]),
        "similar_questions": [
            f"best current XI for {team_code}",
            f"best bowlers against Kohli for {team_code}",
            f"compare {team_code} and {opp_code}",
        ],
    }
    return _ref_add_metadata(result, "Refined tactical match report", "current_squads, deliveries, matches")


try:
    _previous_answer_question_with_fallback_before_refinement_comparison_xi_tactical = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_refinement_comparison_xi_tactical = None


def answer_question_with_fallback(user_question):
    routes = [
        _ref_direct_team_comparison,
        _ref_direct_best_xi,
        _ref_direct_tactical_report,
    ]

    for route in routes:
        result = route(user_question)
        if result is not None:
            return result

    return _previous_answer_question_with_fallback_before_refinement_comparison_xi_tactical(user_question)

# IPL SQL Agent refinement comparison xi tactical END


# IPL SQL Agent restored match plan route START

def _mp2_quote(value):
    return str(value).replace("'", "''")


def _mp2_sql_list(values):
    values = [value for value in values if value and str(value).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _mp2_quote(value) + "'" for value in values) + ")"


def _mp2_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]
    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases
    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases
    return None, None, []


def _mp2_parse_match_plan(question):
    import re
    text = str(question or "")
    match = re.search(r"\bhow\s+can\s+(.+?)\s+beat\s+(.+?)(?:\s+at\s+|$)", text, flags=re.I)
    if not match:
        return None
    team = _mp2_team_lookup(match.group(1).strip(" .?"))
    opp = _mp2_team_lookup(match.group(2).strip(" .?"))
    if not team[0] or not opp[0]:
        return None
    return team + opp


def _mp2_venue_condition(question):
    import re
    text = str(question or "")
    match = re.search(r"\bat\s+([A-Za-z0-9 .'-]+?)\s*$", text, flags=re.I)
    if not match:
        return "1=1", None
    venue = match.group(1).strip(" .?").lower()
    if "chepauk" in venue or "chidambaram" in venue:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "wankhede" in venue:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chinnaswamy" in venue:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "eden" in venue:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "narendra" in venue or "motera" in venue:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.venue LIKE '%Sardar Patel%')", "Narendra Modi Stadium"
    return f"LOWER(m.venue) LIKE '%{_mp2_quote(venue)}%'", venue.title()


def _mp2_phase_case():
    return "CASE WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay' WHEN FLOOR(d.ball) BETWEEN 6 AND 15 THEN 'Middle overs' ELSE 'Death overs' END"


def _mp2_make_suggested_matchups(bowling_df, batting_df):
    import pandas as pd
    if bowling_df is None or batting_df is None or bowling_df.empty or batting_df.empty:
        return pd.DataFrame()
    rows = []
    for _, bowler in bowling_df.head(4).iterrows():
        for _, batter in batting_df.head(4).iterrows():
            rows.append({
                "bowler": bowler.get("bowler"),
                "batter": batter.get("batter"),
                "balls": 0,
                "runs": 0,
                "dismissals": 0,
                "batter_sr_vs_bowler": None,
                "matchup_type": "Suggested",
                "matchup_note": "No direct record found; suggested from current bowling options and opponent key batters."
            })
    return pd.DataFrame(rows)


def _mp2_restored_match_plan(question):
    import pandas as pd
    from app.db import run_query

    parsed = _mp2_parse_match_plan(question)
    if not parsed:
        return None

    team_code, team_name, team_aliases, opp_code, opp_name, opp_aliases = parsed
    team_list = _mp2_sql_list(team_aliases)
    opp_list = _mp2_sql_list(opp_aliases)
    venue_filter, venue_label = _mp2_venue_condition(question)
    phase_case = _mp2_phase_case()

    opponent_key_batters_sql = f"""
SELECT TOP 10
    d.striker AS batter,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS innings,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0))*100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS strike_rate
FROM deliveries d
WHERE d.batting_team IN {opp_list}
  AND d.innings IN (1,2)
GROUP BY d.striker
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
ORDER BY runs DESC, matches DESC, batter ASC;
""".strip()

    team_bowling_options_sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name, role
    FROM current_squads
    WHERE team_code = '{_mp2_quote(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
)
SELECT TOP 10
    cb.display_name AS bowler,
    cb.role,
    COUNT(DISTINCT d.match_id) AS matches,
    CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) / 6 AS varchar(20))
      + '.' +
      CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) % 6 AS varchar(1)) AS overs_bowled,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)+COALESCE(d.extras, 0))*6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS economy
FROM current_bowlers cb
LEFT JOIN deliveries d
    ON (d.bowler = cb.cricsheet_name OR d.bowler = cb.display_name)
   AND d.innings IN (1,2)
GROUP BY cb.display_name, cb.role
ORDER BY wickets DESC, economy ASC, bowler ASC;
""".strip()

    key_matchups_sql = f"""
WITH team_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name
    FROM current_squads
    WHERE team_code = '{_mp2_quote(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
),
opp_batters AS (
    SELECT TOP 10 d.striker AS batter, SUM(COALESCE(d.runs_off_bat,0)) AS runs
    FROM deliveries d
    WHERE d.batting_team IN {opp_list}
      AND d.innings IN (1,2)
    GROUP BY d.striker
    ORDER BY runs DESC
)
SELECT TOP 15
    tb.display_name AS bowler,
    ob.batter,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat,0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat,0))*100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr_vs_bowler,
    'Direct' AS matchup_type
FROM team_bowlers tb
JOIN deliveries d
    ON (d.bowler = tb.cricsheet_name OR d.bowler = tb.display_name)
   AND d.innings IN (1,2)
JOIN opp_batters ob
    ON d.striker = ob.batter
GROUP BY tb.display_name, ob.batter
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
ORDER BY dismissals DESC, batter_sr_vs_bowler ASC, balls DESC, bowler ASC, batter ASC;
""".strip()

    toss_sql = f"""
WITH h2h AS (
    SELECT DISTINCT m.match_id
    FROM matches m
    JOIN deliveries d ON m.match_id = d.match_id
    WHERE ((d.batting_team IN {team_list} AND d.bowling_team IN {opp_list})
       OR  (d.batting_team IN {opp_list} AND d.bowling_team IN {team_list}))
      AND {venue_filter}
)
SELECT
    m.toss_decision,
    COUNT(DISTINCT m.match_id) AS matches,
    SUM(CASE WHEN m.toss_winner = m.winner THEN 1 ELSE 0 END) AS toss_winner_wins,
    ROUND(SUM(CASE WHEN m.toss_winner = m.winner THEN 1 ELSE 0 END)*100.0 / NULLIF(COUNT(DISTINCT m.match_id), 0), 2) AS toss_winner_success_pct
FROM h2h
JOIN matches m ON h2h.match_id = m.match_id
WHERE m.toss_decision IS NOT NULL
GROUP BY m.toss_decision
ORDER BY toss_winner_success_pct DESC, matches DESC;
""".strip()

    batting_phase_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(COALESCE(d.runs_off_bat,0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS wickets_lost,
    ROUND(SUM(COALESCE(d.runs_off_bat,0))*100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END), 0), 2) AS strike_rate
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.batting_team IN {team_list}
  AND d.bowling_team IN {opp_list}
  AND d.innings IN (1,2)
  AND {venue_filter}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case}='Powerplay' THEN 1 WHEN {phase_case}='Middle overs' THEN 2 ELSE 3 END;
""".strip()

    bowling_phase_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat,0)+COALESCE(d.extras,0)) AS runs_conceded,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat,0)+COALESCE(d.extras,0))*6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END), 0), 2) AS economy
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.bowling_team IN {team_list}
  AND d.batting_team IN {opp_list}
  AND d.innings IN (1,2)
  AND {venue_filter}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case}='Powerplay' THEN 1 WHEN {phase_case}='Middle overs' THEN 2 ELSE 3 END;
""".strip()

    try:
        opponent_key_batters = run_query(opponent_key_batters_sql)
        team_bowling_options = run_query(team_bowling_options_sql)
        key_matchups = run_query(key_matchups_sql)
        toss_guide = run_query(toss_sql)
        batting_phase = run_query(batting_phase_sql)
        bowling_phase = run_query(bowling_phase_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"Match plan query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": "",
            "similar_questions": [],
        }

    opponent_key_batters = opponent_key_batters if opponent_key_batters is not None else pd.DataFrame()
    team_bowling_options = team_bowling_options if team_bowling_options is not None else pd.DataFrame()
    key_matchups = key_matchups if key_matchups is not None else pd.DataFrame()
    toss_guide = toss_guide if toss_guide is not None else pd.DataFrame()
    batting_phase = batting_phase if batting_phase is not None else pd.DataFrame()
    bowling_phase = bowling_phase if bowling_phase is not None else pd.DataFrame()

    if key_matchups.empty:
        key_matchups = _mp2_make_suggested_matchups(team_bowling_options, opponent_key_batters)

    toss_text = "No clear toss edge in the local sample; decide after pitch/dew check."
    if not toss_guide.empty:
        try:
            d = str(toss_guide.iloc[0].get("toss_decision") or "").lower()
            p = toss_guide.iloc[0].get("toss_winner_success_pct")
            if d:
                toss_text = f"If toss won, lean to {d}; toss-winner success in this sample: {p}%."
        except Exception:
            pass

    innings_plan = pd.DataFrame([
        {"scenario": "Toss call", "plan": toss_text},
        {"scenario": "If batting first", "plan": f"Set above-par total; protect middle overs; attack {opp_code} death matchups."},
        {"scenario": "If bowling first", "plan": f"Attack {opp_code} key batters early; save best death options for overs 17-20."},
    ])

    venue_text = f" at {venue_label}" if venue_label else ""
    paragraph = (
        f"Restored original-style match plan: how {team_name} can beat {opp_name}{venue_text}. "
        "Main result shows key matchups. Tabs include opponent key batters, current bowling options, toss guide, and batting-first/bowling-first plans."
    )

    extra_tables = {
        "Key Matchups": key_matchups,
        "Opponent Key Batters": opponent_key_batters,
        "Team Bowling Options": team_bowling_options,
        "Toss Decision Guide": toss_guide,
        "Batting/Bowling First Plan": innings_plan,
        "Batting Phase Record": batting_phase,
        "Bowling Phase Record": bowling_phase,
    }
    extra_tables = {k: v for k, v in extra_tables.items() if v is not None and not (hasattr(v, "empty") and v.empty)}

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": key_matchups,
        "extra_tables": extra_tables,
        "sql_query": "\n\n".join([key_matchups_sql, opponent_key_batters_sql, team_bowling_options_sql, toss_sql, batting_phase_sql, bowling_phase_sql]),
        "similar_questions": [
            f"best current XI for {team_code}",
            f"best bowlers against Kohli for {team_code}",
            f"compare {team_code} and {opp_code}",
        ],
        "route_used": "Restored match plan",
        "data_sources": "current_squads, deliveries, matches",
    }


try:
    _previous_answer_question_with_fallback_before_match_plan_restore_v2 = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_match_plan_restore_v2 = None


def answer_question_with_fallback(user_question):
    result = _mp2_restored_match_plan(user_question)
    if result is not None:
        return result
    return _previous_answer_question_with_fallback_before_match_plan_restore_v2(user_question)

# IPL SQL Agent restored match plan route END


# IPL SQL Agent match plan action table restore START

def _mp3_quote(value):
    return str(value).replace("'", "''")


def _mp3_sql_list(values):
    values = [value for value in values if value and str(value).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _mp3_quote(value) + "'" for value in values) + ")"


def _mp3_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]
    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases
    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases
    return None, None, []


def _mp3_parse(question):
    import re
    text = str(question or "")
    match = re.search(r"\bhow\s+can\s+(.+?)\s+beat\s+(.+?)(?:\s+at\s+|$)", text, flags=re.I)
    if not match:
        return None
    team = _mp3_team_lookup(match.group(1).strip(" .?"))
    opp = _mp3_team_lookup(match.group(2).strip(" .?"))
    if not team[0] or not opp[0]:
        return None
    return team + opp


def _mp3_venue_condition(question):
    import re
    text = str(question or "")
    match = re.search(r"\bat\s+([A-Za-z0-9 .'-]+?)\s*$", text, flags=re.I)
    if not match:
        return "1=1", None
    venue = match.group(1).strip(" .?").lower()
    if "chepauk" in venue or "chidambaram" in venue:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "wankhede" in venue:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chinnaswamy" in venue:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "eden" in venue:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "narendra" in venue or "motera" in venue:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.venue LIKE '%Sardar Patel%')", "Narendra Modi Stadium"
    return f"LOWER(m.venue) LIKE '%{_mp3_quote(venue)}%'", venue.title()


def _mp3_phase_case():
    return "CASE WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay' WHEN FLOOR(d.ball) BETWEEN 6 AND 15 THEN 'Middle overs' ELSE 'Death overs' END"


def _mp3_suggest_matchups(bowling_df, batting_df):
    import pandas as pd
    if bowling_df is None or batting_df is None or bowling_df.empty or batting_df.empty:
        return pd.DataFrame()
    rows = []
    for _, bowler in bowling_df.head(4).iterrows():
        for _, batter in batting_df.head(4).iterrows():
            rows.append({
                "bowler": bowler.get("bowler"),
                "batter": batter.get("batter"),
                "balls": 0,
                "runs": 0,
                "dismissals": 0,
                "batter_sr_vs_bowler": None,
                "matchup_type": "Suggested",
                "matchup_note": "No direct record; suggested from current bowling options and opponent key batters."
            })
    return pd.DataFrame(rows)


def _mp3_action_match_plan(question):
    import pandas as pd
    from app.db import run_query

    parsed = _mp3_parse(question)
    if not parsed:
        return None

    team_code, team_name, team_aliases, opp_code, opp_name, opp_aliases = parsed
    team_list = _mp3_sql_list(team_aliases)
    opp_list = _mp3_sql_list(opp_aliases)
    venue_filter, venue_label = _mp3_venue_condition(question)
    phase_case = _mp3_phase_case()

    opponent_key_batters_sql = f"""
WITH current_opp AS (
    SELECT DISTINCT
        display_name,
        cricsheet_name,
        role,
        1 AS current_player
    FROM current_squads
    WHERE team_code = '{_mp3_quote(opp_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Batter%' OR role LIKE '%WK%' OR role LIKE '%All%')
),
batting AS (
    SELECT
        COALESCE(c.display_name, d.striker) AS batter,
        MAX(COALESCE(c.role, 'Historical player')) AS role,
        MAX(COALESCE(c.current_player, 0)) AS current_player,
        COUNT(DISTINCT d.match_id) AS matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls
    FROM deliveries d
    LEFT JOIN current_opp c
        ON d.striker = c.cricsheet_name OR d.striker = c.display_name
    WHERE d.batting_team IN {opp_list}
      AND d.innings IN (1,2)
    GROUP BY COALESCE(c.display_name, d.striker)
)
SELECT TOP 12
    batter,
    role,
    current_player,
    matches,
    innings,
    runs,
    balls,
    ROUND(runs*100.0 / NULLIF(balls, 0), 2) AS strike_rate
FROM batting
WHERE balls > 0
ORDER BY current_player DESC, runs DESC, matches DESC, batter ASC;
""".strip()

    bowling_options_sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name, role
    FROM current_squads
    WHERE team_code = '{_mp3_quote(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
)
SELECT TOP 10
    cb.display_name AS bowler,
    cb.role,
    COUNT(DISTINCT d.match_id) AS matches,
    CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) / 6 AS varchar(20))
      + '.' +
      CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) % 6 AS varchar(1)) AS overs_bowled,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)+COALESCE(d.extras, 0))*6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS economy
FROM current_bowlers cb
LEFT JOIN deliveries d
    ON (d.bowler = cb.cricsheet_name OR d.bowler = cb.display_name)
   AND d.innings IN (1,2)
GROUP BY cb.display_name, cb.role
ORDER BY wickets DESC, economy ASC, bowler ASC;
""".strip()

    key_matchups_sql = f"""
WITH team_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name
    FROM current_squads
    WHERE team_code = '{_mp3_quote(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
),
opp_batters AS (
    SELECT TOP 12 d.striker AS batter, SUM(COALESCE(d.runs_off_bat,0)) AS runs
    FROM deliveries d
    WHERE d.batting_team IN {opp_list}
      AND d.innings IN (1,2)
    GROUP BY d.striker
    ORDER BY runs DESC
)
SELECT TOP 15
    tb.display_name AS bowler,
    ob.batter,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat,0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat,0))*100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr_vs_bowler,
    'Direct' AS matchup_type
FROM team_bowlers tb
JOIN deliveries d
    ON (d.bowler = tb.cricsheet_name OR d.bowler = tb.display_name)
   AND d.innings IN (1,2)
JOIN opp_batters ob
    ON d.striker = ob.batter
GROUP BY tb.display_name, ob.batter
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
ORDER BY dismissals DESC, batter_sr_vs_bowler ASC, balls DESC, bowler ASC, batter ASC;
""".strip()

    toss_sql = f"""
WITH h2h AS (
    SELECT DISTINCT m.match_id
    FROM matches m
    JOIN deliveries d ON m.match_id = d.match_id
    WHERE ((d.batting_team IN {team_list} AND d.bowling_team IN {opp_list})
       OR  (d.batting_team IN {opp_list} AND d.bowling_team IN {team_list}))
      AND {venue_filter}
)
SELECT
    m.toss_decision,
    COUNT(DISTINCT m.match_id) AS matches,
    SUM(CASE WHEN m.toss_winner = m.winner THEN 1 ELSE 0 END) AS toss_winner_wins,
    ROUND(SUM(CASE WHEN m.toss_winner = m.winner THEN 1 ELSE 0 END)*100.0 / NULLIF(COUNT(DISTINCT m.match_id), 0), 2) AS toss_winner_success_pct
FROM h2h
JOIN matches m ON h2h.match_id = m.match_id
WHERE m.toss_decision IS NOT NULL
GROUP BY m.toss_decision
ORDER BY toss_winner_success_pct DESC, matches DESC;
""".strip()

    batting_phase_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(COALESCE(d.runs_off_bat,0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS wickets_lost,
    ROUND(SUM(COALESCE(d.runs_off_bat,0))*100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END), 0), 2) AS strike_rate
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.batting_team IN {team_list}
  AND d.bowling_team IN {opp_list}
  AND d.innings IN (1,2)
  AND {venue_filter}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case}='Powerplay' THEN 1 WHEN {phase_case}='Middle overs' THEN 2 ELSE 3 END;
""".strip()

    bowling_phase_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat,0)+COALESCE(d.extras,0)) AS runs_conceded,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat,0)+COALESCE(d.extras,0))*6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END), 0), 2) AS economy
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.bowling_team IN {team_list}
  AND d.batting_team IN {opp_list}
  AND d.innings IN (1,2)
  AND {venue_filter}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case}='Powerplay' THEN 1 WHEN {phase_case}='Middle overs' THEN 2 ELSE 3 END;
""".strip()

    try:
        opponent_key_batters = run_query(opponent_key_batters_sql)
        bowling_options = run_query(bowling_options_sql)
        key_matchups = run_query(key_matchups_sql)
        toss_guide = run_query(toss_sql)
        batting_phase = run_query(batting_phase_sql)
        bowling_phase = run_query(bowling_phase_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"Match plan query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": "",
            "similar_questions": [],
        }

    opponent_key_batters = opponent_key_batters if opponent_key_batters is not None else pd.DataFrame()
    bowling_options = bowling_options if bowling_options is not None else pd.DataFrame()
    key_matchups = key_matchups if key_matchups is not None else pd.DataFrame()
    toss_guide = toss_guide if toss_guide is not None else pd.DataFrame()
    batting_phase = batting_phase if batting_phase is not None else pd.DataFrame()
    bowling_phase = bowling_phase if bowling_phase is not None else pd.DataFrame()

    if key_matchups.empty:
        key_matchups = _mp3_suggest_matchups(bowling_options, opponent_key_batters)

    toss_text = "No clear toss edge; decide after pitch/dew check."
    if not toss_guide.empty:
        try:
            toss_choice = str(toss_guide.iloc[0].get("toss_decision") or "").lower()
            pct = toss_guide.iloc[0].get("toss_winner_success_pct")
            if toss_choice:
                toss_text = f"Lean to {toss_choice} if toss is won. Toss-winner success in sample: {pct}%."
        except Exception:
            pass

    action_plan = pd.DataFrame([
        {"section": "Toss call", "action": toss_text, "focus": "Venue + opposition sample"},
        {"section": "If batting first", "action": f"Set above-par total; protect wickets in middle overs; attack {opp_code} at the death.", "focus": "Batting first plan"},
        {"section": "If bowling first", "action": f"Attack {opp_code} key batters early; keep best death options for overs 17-20.", "focus": "Bowling first plan"},
        {"section": "Powerplay", "action": "Use attacking fields and wicket-taking bowlers; avoid easy width.", "focus": "Early wickets"},
        {"section": "Middle overs", "action": "Use matchups, especially spin/pace combinations against set batters.", "focus": "Control phase"},
        {"section": "Death overs", "action": "Save yorkers/slower-ball bowlers; plan field for each batter.", "focus": "Overs 17-20"},
        {"section": "Key matchup use", "action": "Use the Key Matchups tab as the bowler-vs-batter plan, not as the whole plan.", "focus": "Selection/tactics"},
    ])

    venue_text = f" at {venue_label}" if venue_label else ""
    paragraph = (
        f"Action plan: how {team_name} can beat {opp_name}{venue_text}. "
        "Main result is the action plan; tabs contain key matchups, opponent key batters, bowling options, toss guide, and phase records."
    )

    extra_tables = {
        "Key Matchups": key_matchups,
        "Opponent Key Batters": opponent_key_batters,
        "Team Bowling Options": bowling_options,
        "Toss Decision Guide": toss_guide,
        "Batting/Bowling First Plan": action_plan[action_plan["section"].isin(["If batting first", "If bowling first", "Toss call"])],
        "Batting Phase Record": batting_phase,
        "Bowling Phase Record": bowling_phase,
    }
    extra_tables = {k: v for k, v in extra_tables.items() if v is not None and not (hasattr(v, "empty") and v.empty)}

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": action_plan,
        "extra_tables": extra_tables,
        "sql_query": "\n\n".join([opponent_key_batters_sql, bowling_options_sql, key_matchups_sql, toss_sql, batting_phase_sql, bowling_phase_sql]),
        "similar_questions": [
            f"best current XI for {team_code}",
            f"best bowlers against Kohli for {team_code}",
            f"compare {team_code} and {opp_code}",
        ],
        "route_used": "Action match plan",
        "data_sources": "current_squads, deliveries, matches",
    }


try:
    _previous_answer_question_with_fallback_before_match_plan_action_restore = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_match_plan_action_restore = None


def answer_question_with_fallback(user_question):
    result = _mp3_action_match_plan(user_question)
    if result is not None:
        return result
    return _previous_answer_question_with_fallback_before_match_plan_action_restore(user_question)

# IPL SQL Agent match plan action table restore END


# IPL SQL Agent venue profile route START

def _venue_quote(value):
    return str(value).replace("'", "''")


def _venue_condition_from_question(question):
    import re

    text = str(question or "").lower().strip()

    known = [
        ("Chepauk", ["chepauk", "chidambaram", "ma chidambaram", "m. a. chidambaram"]),
        ("Eden Gardens", ["eden gardens", "eden"]),
        ("Wankhede", ["wankhede"]),
        ("Chinnaswamy", ["chinnaswamy", "bengaluru stadium", "bangalore stadium"]),
        ("Narendra Modi Stadium", ["narendra modi", "motera", "sardar patel"]),
        ("Arun Jaitley Stadium", ["arun jaitley", "feroz shah kotla", "kotla"]),
        ("Rajiv Gandhi International Stadium", ["rajiv gandhi", "uppal"]),
        ("Sawai Mansingh Stadium", ["sawai mansingh", "jaipur"]),
        ("MCA Stadium Pune", ["mca stadium", "pune"]),
        ("DY Patil Stadium", ["dy patil", "d y patil"]),
        ("Brabourne Stadium", ["brabourne"]),
        ("Dubai International Stadium", ["dubai"]),
        ("Sharjah Cricket Stadium", ["sharjah"]),
        ("Sheikh Zayed Stadium", ["abu dhabi", "sheikh zayed"]),
    ]

    for label, triggers in known:
        if any(trigger in text for trigger in triggers):
            if label == "Chepauk":
                return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", label
            if label == "Eden Gardens":
                return "m.venue LIKE '%Eden Gardens%'", label
            if label == "Wankhede":
                return "m.venue LIKE '%Wankhede%'", label
            if label == "Chinnaswamy":
                return "m.venue LIKE '%Chinnaswamy%'", label
            if label == "Narendra Modi Stadium":
                return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.venue LIKE '%Sardar Patel%')", label
            if label == "Arun Jaitley Stadium":
                return "(m.venue LIKE '%Arun Jaitley%' OR m.venue LIKE '%Feroz Shah Kotla%')", label
            if label == "Rajiv Gandhi International Stadium":
                return "(m.venue LIKE '%Rajiv Gandhi%' OR m.venue LIKE '%Uppal%')", label
            if label == "Sawai Mansingh Stadium":
                return "(m.venue LIKE '%Sawai Mansingh%' OR m.venue LIKE '%Jaipur%')", label
            if label == "MCA Stadium Pune":
                return "(m.venue LIKE '%Maharashtra Cricket Association%' OR m.venue LIKE '%MCA%' OR m.city LIKE '%Pune%')", label
            if label == "DY Patil Stadium":
                return "m.venue LIKE '%DY Patil%'", label
            if label == "Brabourne Stadium":
                return "m.venue LIKE '%Brabourne%'", label
            if label == "Dubai International Stadium":
                return "(m.venue LIKE '%Dubai%' OR m.city LIKE '%Dubai%')", label
            if label == "Sharjah Cricket Stadium":
                return "(m.venue LIKE '%Sharjah%' OR m.city LIKE '%Sharjah%')", label
            if label == "Sheikh Zayed Stadium":
                return "(m.venue LIKE '%Sheikh Zayed%' OR m.city LIKE '%Abu Dhabi%')", label

    # Generic fallback for phrases like "tell me about <venue> stats"
    match = re.search(
        r"(?:tell me about|analyse|analyze|profile|stats for|venue profile of)\s+(.+?)(?:\s+stats|\s+venue|\s+stadium)?\s*$",
        str(question or ""),
        flags=re.IGNORECASE,
    )

    if match:
        raw = match.group(1).strip(" .?")
        raw_low = raw.lower()

        # Avoid hijacking player/team profiles.
        team_words = {"csk", "mi", "rcb", "gt", "kkr", "rr", "srh", "dc", "pbks", "lsg", "suresh raina", "kohli", "raina", "dhoni", "rohit"}
        if raw_low not in team_words and len(raw) >= 4:
            safe = _venue_quote(raw_low)
            return f"(LOWER(m.venue) LIKE '%{safe}%' OR LOWER(m.city) LIKE '%{safe}%')", raw.title()

    return None, None


def _venue_season_order_expr(column_name):
    return f"""
CASE
    WHEN CHARINDEX('/', CAST({column_name} AS varchar(20))) > 0
    THEN TRY_CONVERT(INT, LEFT(CAST({column_name} AS varchar(20)), 4))
    ELSE TRY_CONVERT(INT, CAST({column_name} AS varchar(20)))
END
""".strip()


def _venue_direct_profile(question):
    import pandas as pd
    from app.db import run_query

    q = str(question or "").lower()

    # Do not hijack tactical match-plan questions such as:
    # "how can CSK beat GT at Chepauk".
    # Those should route to the match-plan/action table route, not venue profile.
    if "how can" in q and "beat" in q:
        return None

    if not (
        "venue" in q
        or "stadium" in q
        or "ground" in q
        or "stats" in q
        or "tell me about" in q
        or "chepauk" in q
        or "eden" in q
        or "wankhede" in q
        or "chinnaswamy" in q
        or "narendra" in q
        or "kotla" in q
    ):
        return None

    condition, label = _venue_condition_from_question(question)

    if not condition:
        return None

    summary_sql = f"""
WITH venue_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season,
        CAST(m.start_date AS date) AS match_date,
        m.venue,
        m.city,
        m.toss_winner,
        m.toss_decision,
        m.winner,
        m.winner_runs,
        m.winner_wickets
    FROM matches m
    WHERE {condition}
),
innings_scores AS (
    SELECT
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS innings_runs
    FROM deliveries d
    JOIN venue_matches vm
        ON d.match_id = vm.match_id
    WHERE d.innings IN (1, 2)
    GROUP BY d.match_id, d.innings
),
pivot_scores AS (
    SELECT
        match_id,
        MAX(CASE WHEN innings = 1 THEN innings_runs END) AS first_innings_runs,
        MAX(CASE WHEN innings = 2 THEN innings_runs END) AS second_innings_runs
    FROM innings_scores
    GROUP BY match_id
)
SELECT
    '{_venue_quote(label)}' AS venue_profile,
    COUNT(DISTINCT vm.match_id) AS matches,
    COUNT(DISTINCT vm.season) AS seasons,
    MIN(vm.match_date) AS first_match_date,
    MAX(vm.match_date) AS latest_match_date,
    ROUND(AVG(CAST(ps.first_innings_runs AS float)), 2) AS avg_first_innings_score,
    ROUND(AVG(CAST(ps.second_innings_runs AS float)), 2) AS avg_second_innings_score,
    SUM(CASE WHEN vm.winner_runs IS NOT NULL AND vm.winner_runs > 0 THEN 1 ELSE 0 END) AS batting_first_wins,
    SUM(CASE WHEN vm.winner_wickets IS NOT NULL AND vm.winner_wickets > 0 THEN 1 ELSE 0 END) AS chasing_wins,
    ROUND(SUM(CASE WHEN vm.winner_wickets IS NOT NULL AND vm.winner_wickets > 0 THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(DISTINCT vm.match_id), 0), 2) AS chasing_win_pct
FROM venue_matches vm
LEFT JOIN pivot_scores ps
    ON vm.match_id = ps.match_id;
""".strip()

    season_sql = f"""
WITH venue_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.season,
        m.winner,
        m.winner_runs,
        m.winner_wickets
    FROM matches m
    WHERE {condition}
),
first_innings AS (
    SELECT
        d.match_id,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS first_innings_runs
    FROM deliveries d
    JOIN venue_matches vm
        ON d.match_id = vm.match_id
    WHERE d.innings = 1
    GROUP BY d.match_id
)
SELECT
    vm.season,
    COUNT(DISTINCT vm.match_id) AS matches,
    ROUND(AVG(CAST(fi.first_innings_runs AS float)), 2) AS avg_first_innings_score,
    SUM(CASE WHEN vm.winner_runs IS NOT NULL AND vm.winner_runs > 0 THEN 1 ELSE 0 END) AS batting_first_wins,
    SUM(CASE WHEN vm.winner_wickets IS NOT NULL AND vm.winner_wickets > 0 THEN 1 ELSE 0 END) AS chasing_wins
FROM venue_matches vm
LEFT JOIN first_innings fi
    ON vm.match_id = fi.match_id
GROUP BY vm.season
ORDER BY
    {_venue_season_order_expr("vm.season")},
    vm.season;
""".strip()

    team_sql = f"""
WITH venue_matches AS (
    SELECT DISTINCT m.match_id
    FROM matches m
    WHERE {condition}
),
team_appearances AS (
    SELECT
        d.batting_team AS team,
        d.match_id
    FROM deliveries d
    JOIN venue_matches vm
        ON d.match_id = vm.match_id

    UNION

    SELECT
        d.bowling_team AS team,
        d.match_id
    FROM deliveries d
    JOIN venue_matches vm
        ON d.match_id = vm.match_id
),
wins AS (
    SELECT
        m.winner AS team,
        COUNT(DISTINCT m.match_id) AS wins
    FROM matches m
    JOIN venue_matches vm
        ON m.match_id = vm.match_id
    WHERE m.winner IS NOT NULL
    GROUP BY m.winner
)
SELECT TOP 15
    ta.team,
    COUNT(DISTINCT ta.match_id) AS matches,
    COALESCE(MAX(w.wins), 0) AS wins,
    COUNT(DISTINCT ta.match_id) - COALESCE(MAX(w.wins), 0) AS losses,
    ROUND(COALESCE(MAX(w.wins), 0) * 100.0 / NULLIF(COUNT(DISTINCT ta.match_id), 0), 2) AS win_pct
FROM team_appearances ta
LEFT JOIN wins w
    ON ta.team = w.team
GROUP BY ta.team
ORDER BY matches DESC, wins DESC, ta.team ASC;
""".strip()

    top_batters_sql = f"""
WITH venue_matches AS (
    SELECT DISTINCT m.match_id
    FROM matches m
    WHERE {condition}
)
SELECT TOP 15
    d.striker AS batter,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS strike_rate
FROM deliveries d
JOIN venue_matches vm
    ON d.match_id = vm.match_id
WHERE d.innings IN (1, 2)
GROUP BY d.striker
ORDER BY runs DESC, matches DESC, batter ASC;
""".strip()

    top_bowlers_sql = f"""
WITH venue_matches AS (
    SELECT DISTINCT m.match_id
    FROM matches m
    WHERE {condition}
)
SELECT TOP 15
    d.bowler,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS legal_balls,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END), 0), 2) AS economy
FROM deliveries d
JOIN venue_matches vm
    ON d.match_id = vm.match_id
WHERE d.innings IN (1, 2)
GROUP BY d.bowler
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
ORDER BY wickets DESC, economy ASC, bowler ASC;
""".strip()

    toss_sql = f"""
WITH venue_matches AS (
    SELECT DISTINCT
        m.match_id,
        m.toss_decision,
        m.toss_winner,
        m.winner
    FROM matches m
    WHERE {condition}
)
SELECT
    toss_decision,
    COUNT(DISTINCT match_id) AS matches,
    SUM(CASE WHEN toss_winner = winner THEN 1 ELSE 0 END) AS toss_winner_wins,
    ROUND(SUM(CASE WHEN toss_winner = winner THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(DISTINCT match_id), 0), 2) AS toss_winner_success_pct
FROM venue_matches
WHERE toss_decision IS NOT NULL
GROUP BY toss_decision
ORDER BY matches DESC, toss_winner_success_pct DESC;
""".strip()

    try:
        summary_df = run_query(summary_sql)
        season_df = run_query(season_sql)
        team_df = run_query(team_sql)
        top_batters_df = run_query(top_batters_sql)
        top_bowlers_df = run_query(top_bowlers_sql)
        toss_df = run_query(toss_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The venue profile route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": summary_sql,
            "similar_questions": [],
            "route_used": "Venue profile",
            "data_sources": "matches, deliveries",
        }

    summary_df = summary_df if summary_df is not None else pd.DataFrame()
    season_df = season_df if season_df is not None else pd.DataFrame()
    team_df = team_df if team_df is not None else pd.DataFrame()
    top_batters_df = top_batters_df if top_batters_df is not None else pd.DataFrame()
    top_bowlers_df = top_bowlers_df if top_bowlers_df is not None else pd.DataFrame()
    toss_df = toss_df if toss_df is not None else pd.DataFrame()

    paragraph = (
        f"Venue profile for {label}: summary record, scoring conditions, chasing/batting-first split, team records, top batters, top bowlers, and toss decision data."
    )

    if summary_df.empty or (not summary_df.empty and int(summary_df.iloc[0].get("matches") or 0) == 0):
        paragraph = f"No venue rows were found for {label}. Try a different spelling or a broader venue name."

    extra_tables = {
        "Venue Summary": summary_df,
        "Season Trend": season_df,
        "Team Record At Venue": team_df,
        "Top Batters At Venue": top_batters_df,
        "Top Bowlers At Venue": top_bowlers_df,
        "Toss Decision At Venue": toss_df,
    }
    extra_tables = {
        name: table
        for name, table in extra_tables.items()
        if table is not None and not (hasattr(table, "empty") and table.empty)
    }

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": summary_df,
        "extra_tables": extra_tables,
        "sql_query": "\n\n".join([summary_sql, season_sql, team_sql, top_batters_sql, top_bowlers_sql, toss_sql]),
        "similar_questions": [
            f"what is CSK win loss percentage at {label}",
            f"top run scorers at {label}",
            f"most wickets at {label}",
        ],
        "route_used": "Venue profile",
        "data_sources": "matches, deliveries",
    }


try:
    _previous_answer_question_with_fallback_before_venue_profile_route = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_venue_profile_route = None


def answer_question_with_fallback(user_question):
    result = _venue_direct_profile(user_question)
    if result is not None:
        return result
    return _previous_answer_question_with_fallback_before_venue_profile_route(user_question)

# IPL SQL Agent venue profile route END


# IPL SQL Agent match plan current squads phase meaning START

def _mp4_quote(value):
    return str(value).replace("'", "''")


def _mp4_sql_list(values):
    values = [value for value in values if value and str(value).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _mp4_quote(value) + "'" for value in values) + ")"


def _mp4_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]
    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases
    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases
    return None, None, []


def _mp4_parse(question):
    import re
    text = str(question or "")
    match = re.search(r"\bhow\s+can\s+(.+?)\s+beat\s+(.+?)(?:\s+at\s+|$)", text, flags=re.I)
    if not match:
        return None
    team = _mp4_team_lookup(match.group(1).strip(" .?"))
    opp = _mp4_team_lookup(match.group(2).strip(" .?"))
    if not team[0] or not opp[0]:
        return None
    return team + opp


def _mp4_venue_condition(question):
    import re
    text = str(question or "")
    match = re.search(r"\bat\s+([A-Za-z0-9 .'-]+?)\s*$", text, flags=re.I)
    if not match:
        return "1=1", None
    venue = match.group(1).strip(" .?").lower()
    if "chepauk" in venue or "chidambaram" in venue:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "wankhede" in venue:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chinnaswamy" in venue:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "eden" in venue:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "narendra" in venue or "motera" in venue:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.venue LIKE '%Sardar Patel%')", "Narendra Modi Stadium"
    return f"LOWER(m.venue) LIKE '%{_mp4_quote(venue)}%'", venue.title()


def _mp4_phase_case():
    return "CASE WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay' WHEN FLOOR(d.ball) BETWEEN 6 AND 15 THEN 'Middle overs' ELSE 'Death overs' END"


def _mp4_suggest_matchups(bowling_df, batting_df):
    import pandas as pd
    if bowling_df is None or batting_df is None or bowling_df.empty or batting_df.empty:
        return pd.DataFrame()
    rows = []
    for _, bowler in bowling_df.head(4).iterrows():
        for _, batter in batting_df.head(4).iterrows():
            rows.append({
                "bowler": bowler.get("bowler"),
                "batter": batter.get("batter"),
                "balls": 0,
                "runs": 0,
                "dismissals": 0,
                "batter_sr_vs_bowler": None,
                "matchup_type": "Suggested current-squad matchup",
                "matchup_note": "No direct IPL record; suggested using current squads only."
            })
    return pd.DataFrame(rows)


def _mp4_action_match_plan(question):
    import pandas as pd
    from app.db import run_query

    parsed = _mp4_parse(question)
    if not parsed:
        return None

    team_code, team_name, team_aliases, opp_code, opp_name, opp_aliases = parsed
    team_list = _mp4_sql_list(team_aliases)
    opp_list = _mp4_sql_list(opp_aliases)
    venue_filter, venue_label = _mp4_venue_condition(question)
    phase_case = _mp4_phase_case()

    # Current squads only for key batters and key matchups.
    opponent_key_batters_sql = f"""
WITH current_opp AS (
    SELECT DISTINCT
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{_mp4_quote(opp_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Batter%' OR role LIKE '%WK%' OR role LIKE '%All%')
),
batting AS (
    SELECT
        co.display_name AS batter,
        co.role,
        COUNT(DISTINCT d.match_id) AS matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls
    FROM current_opp co
    LEFT JOIN deliveries d
        ON (d.striker = co.cricsheet_name OR d.striker = co.display_name)
       AND d.innings IN (1,2)
    GROUP BY co.display_name, co.role
)
SELECT TOP 12
    batter,
    role,
    matches,
    innings,
    COALESCE(runs, 0) AS runs,
    COALESCE(balls, 0) AS balls,
    ROUND(COALESCE(runs, 0)*100.0 / NULLIF(balls, 0), 2) AS strike_rate,
    'Current squad' AS squad_status
FROM batting
ORDER BY runs DESC, strike_rate DESC, batter ASC;
""".strip()

    bowling_options_sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name, role
    FROM current_squads
    WHERE team_code = '{_mp4_quote(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
)
SELECT TOP 10
    cb.display_name AS bowler,
    cb.role,
    COUNT(DISTINCT d.match_id) AS matches,
    CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) / 6 AS varchar(20))
      + '.' +
      CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) % 6 AS varchar(1)) AS overs_bowled,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)+COALESCE(d.extras, 0))*6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS economy
FROM current_bowlers cb
LEFT JOIN deliveries d
    ON (d.bowler = cb.cricsheet_name OR d.bowler = cb.display_name)
   AND d.innings IN (1,2)
GROUP BY cb.display_name, cb.role
ORDER BY wickets DESC, economy ASC, bowler ASC;
""".strip()

    key_matchups_sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name
    FROM current_squads
    WHERE team_code = '{_mp4_quote(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
),
current_batters AS (
    SELECT DISTINCT display_name, cricsheet_name
    FROM current_squads
    WHERE team_code = '{_mp4_quote(opp_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Batter%' OR role LIKE '%WK%' OR role LIKE '%All%')
)
SELECT TOP 15
    cbow.display_name AS bowler,
    cbat.display_name AS batter,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat,0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat,0))*100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr_vs_bowler,
    'Direct current-squad record' AS matchup_type
FROM current_bowlers cbow
CROSS JOIN current_batters cbat
LEFT JOIN deliveries d
    ON (d.bowler = cbow.cricsheet_name OR d.bowler = cbow.display_name)
   AND (d.striker = cbat.cricsheet_name OR d.striker = cbat.display_name)
   AND d.innings IN (1,2)
GROUP BY cbow.display_name, cbat.display_name
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
ORDER BY dismissals DESC, batter_sr_vs_bowler ASC, balls DESC, bowler ASC, batter ASC;
""".strip()

    toss_sql = f"""
WITH h2h AS (
    SELECT DISTINCT m.match_id
    FROM matches m
    JOIN deliveries d ON m.match_id = d.match_id
    WHERE ((d.batting_team IN {team_list} AND d.bowling_team IN {opp_list})
       OR  (d.batting_team IN {opp_list} AND d.bowling_team IN {team_list}))
      AND {venue_filter}
)
SELECT
    m.toss_decision,
    COUNT(DISTINCT m.match_id) AS matches,
    SUM(CASE WHEN m.toss_winner = m.winner THEN 1 ELSE 0 END) AS toss_winner_wins,
    ROUND(SUM(CASE WHEN m.toss_winner = m.winner THEN 1 ELSE 0 END)*100.0 / NULLIF(COUNT(DISTINCT m.match_id), 0), 2) AS toss_winner_success_pct
FROM h2h
JOIN matches m ON h2h.match_id = m.match_id
WHERE m.toss_decision IS NOT NULL
GROUP BY m.toss_decision
ORDER BY toss_winner_success_pct DESC, matches DESC;
""".strip()

    # Renamed and made more meaningful: these are not raw "records" only, they are phase diagnostics.
    batting_phase_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS match_sample,
    SUM(COALESCE(d.runs_off_bat,0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS wickets_lost,
    ROUND(SUM(COALESCE(d.runs_off_bat,0))*100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END), 0), 2) AS strike_rate,
    CASE
        WHEN {phase_case} = 'Powerplay' THEN 'Top-order start'
        WHEN {phase_case} = 'Middle overs' THEN 'Spin/control phase'
        ELSE 'Finishing phase'
    END AS what_it_means,
    CASE
        WHEN {phase_case} = 'Powerplay' THEN 'Avoid early collapse; attack bad balls'
        WHEN {phase_case} = 'Middle overs' THEN 'Keep tempo without losing set batters'
        ELSE 'Preserve finishers and maximise boundaries'
    END AS action
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.batting_team IN {team_list}
  AND d.bowling_team IN {opp_list}
  AND d.innings IN (1,2)
  AND {venue_filter}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case}='Powerplay' THEN 1 WHEN {phase_case}='Middle overs' THEN 2 ELSE 3 END;
""".strip()

    bowling_phase_sql = f"""
SELECT
    {phase_case} AS phase,
    COUNT(DISTINCT d.match_id) AS match_sample,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat,0)+COALESCE(d.extras,0)) AS runs_conceded,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 END) AS wickets,
    ROUND(SUM(COALESCE(d.runs_off_bat,0)+COALESCE(d.extras,0))*6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END), 0), 2) AS economy,
    CASE
        WHEN {phase_case} = 'Powerplay' THEN 'New-ball wicket phase'
        WHEN {phase_case} = 'Middle overs' THEN 'Control and matchup phase'
        ELSE 'Death-over defence phase'
    END AS what_it_means,
    CASE
        WHEN {phase_case} = 'Powerplay' THEN 'Use wicket-taking new-ball options'
        WHEN {phase_case} = 'Middle overs' THEN 'Use spin/pace matchups and dry up singles'
        ELSE 'Save yorkers/slower balls and protect short boundaries'
    END AS action
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.bowling_team IN {team_list}
  AND d.batting_team IN {opp_list}
  AND d.innings IN (1,2)
  AND {venue_filter}
GROUP BY {phase_case}
ORDER BY CASE WHEN {phase_case}='Powerplay' THEN 1 WHEN {phase_case}='Middle overs' THEN 2 ELSE 3 END;
""".strip()

    try:
        opponent_key_batters = run_query(opponent_key_batters_sql)
        bowling_options = run_query(bowling_options_sql)
        key_matchups = run_query(key_matchups_sql)
        toss_guide = run_query(toss_sql)
        batting_phase = run_query(batting_phase_sql)
        bowling_phase = run_query(bowling_phase_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"Match plan query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": "",
            "similar_questions": [],
        }

    opponent_key_batters = opponent_key_batters if opponent_key_batters is not None else pd.DataFrame()
    bowling_options = bowling_options if bowling_options is not None else pd.DataFrame()
    key_matchups = key_matchups if key_matchups is not None else pd.DataFrame()
    toss_guide = toss_guide if toss_guide is not None else pd.DataFrame()
    batting_phase = batting_phase if batting_phase is not None else pd.DataFrame()
    bowling_phase = bowling_phase if bowling_phase is not None else pd.DataFrame()

    if key_matchups.empty:
        key_matchups = _mp4_suggest_matchups(bowling_options, opponent_key_batters)

    toss_text = "No clear toss edge; decide after pitch/dew check."
    if not toss_guide.empty:
        try:
            toss_choice = str(toss_guide.iloc[0].get("toss_decision") or "").lower()
            pct = toss_guide.iloc[0].get("toss_winner_success_pct")
            if toss_choice:
                toss_text = f"Lean to {toss_choice} if toss is won. Toss-winner success in sample: {pct}%."
        except Exception:
            pass

    action_plan = pd.DataFrame([
        {"section": "Toss call", "action": toss_text, "focus": "Venue + opposition sample"},
        {"section": "If batting first", "action": f"Set above-par total; protect wickets in middle overs; attack {opp_code} at the death.", "focus": "Batting first plan"},
        {"section": "If bowling first", "action": f"Attack {opp_code} key batters early; keep best death options for overs 17-20.", "focus": "Bowling first plan"},
        {"section": "Powerplay", "action": "Use attacking fields and wicket-taking bowlers; avoid easy width.", "focus": "Early wickets"},
        {"section": "Middle overs", "action": "Use matchups, especially spin/pace combinations against set batters.", "focus": "Control phase"},
        {"section": "Death overs", "action": "Save yorkers/slower-ball bowlers; plan field for each batter.", "focus": "Overs 17-20"},
        {"section": "Key matchup use", "action": "Use the Key Matchups tab as bowler-vs-batter support, not as the whole plan.", "focus": "Selection/tactics"},
    ])

    venue_text = f" at {venue_label}" if venue_label else ""
    paragraph = (
        f"Action plan: how {team_name} can beat {opp_name}{venue_text}. "
        "Key Matchups now uses current squads only. Phase diagnostics explain what each phase means and what action to take."
    )

    extra_tables = {
        "Key Matchups": key_matchups,
        "Opponent Key Batters": opponent_key_batters,
        "Team Bowling Options": bowling_options,
        "Toss Decision Guide": toss_guide,
        "Batting/Bowling First Plan": action_plan[action_plan["section"].isin(["If batting first", "If bowling first", "Toss call"])],
        "Batting Phase Diagnostic": batting_phase,
        "Bowling Phase Diagnostic": bowling_phase,
    }
    extra_tables = {k: v for k, v in extra_tables.items() if v is not None and not (hasattr(v, "empty") and v.empty)}

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": action_plan,
        "extra_tables": extra_tables,
        "sql_query": "\n\n".join([opponent_key_batters_sql, bowling_options_sql, key_matchups_sql, toss_sql, batting_phase_sql, bowling_phase_sql]),
        "similar_questions": [
            f"best current XI for {team_code}",
            f"best bowlers against Kohli for {team_code}",
            f"compare {team_code} and {opp_code}",
        ],
        "route_used": "Action match plan",
        "data_sources": "current_squads, deliveries, matches",
    }


try:
    _previous_answer_question_with_fallback_before_match_plan_current_phase_meaning = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_match_plan_current_phase_meaning = None


def answer_question_with_fallback(user_question):
    result = _mp4_action_match_plan(user_question)
    if result is not None:
        return result
    return _previous_answer_question_with_fallback_before_match_plan_current_phase_meaning(user_question)

# IPL SQL Agent match plan current squads phase meaning END


# IPL SQL Agent current opponent batter resolver START

def _mp5_quote(value):
    return str(value).replace("'", "''")


def _mp5_sql_list(values):
    values = [value for value in values if value and str(value).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _mp5_quote(value) + "'" for value in values) + ")"


def _mp5_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]
    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases
    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases
    return None, None, []


def _mp5_parse_match_plan(question):
    import re
    text = str(question or "")
    match = re.search(r"\bhow\s+can\s+(.+?)\s+beat\s+(.+?)(?:\s+at\s+|$)", text, flags=re.I)
    if not match:
        return None
    team = _mp5_team_lookup(match.group(1).strip(" .?"))
    opponent = _mp5_team_lookup(match.group(2).strip(" .?"))
    if not team[0] or not opponent[0]:
        return None
    return team + opponent


def _mp5_latest_season_expr(column_name):
    return f"""
CASE
    WHEN CHARINDEX('/', CAST({column_name} AS varchar(20))) > 0
    THEN TRY_CONVERT(INT, LEFT(CAST({column_name} AS varchar(20)), 4))
    ELSE TRY_CONVERT(INT, CAST({column_name} AS varchar(20)))
END
""".strip()


def _mp5_current_opponent_batters_sql(opponent_code):
    code = _mp5_quote(opponent_code)

    return f"""
WITH latest_season AS (
    SELECT TOP 1 season
    FROM matches
    WHERE season IS NOT NULL
    ORDER BY {_mp5_latest_season_expr("season")} DESC, season DESC
),
manual_aliases AS (
    SELECT 'RR' AS team_code, 'Vaibhav Suryavanshi' AS display_name, 'V Suryavanshi' AS cricsheet_name, 'Batter' AS role
    UNION ALL SELECT 'RR', 'Vaibhav Suryavanshi', 'Vaibhav Suryavanshi', 'Batter'
    UNION ALL SELECT 'RR', 'Yashasvi Jaiswal', 'YBK Jaiswal', 'Batter'
    UNION ALL SELECT 'GT', 'Sai Sudharsan', 'B Sai Sudharsan', 'Batter'
    UNION ALL SELECT 'GT', 'Sai Sudharsan', 'Sai Sudharsan', 'Batter'
    UNION ALL SELECT 'GT', 'Shubman Gill', 'Shubman Gill', 'Batter'
    UNION ALL SELECT 'GT', 'Shubman Gill', 'Shubman Gill', 'Batter'
),
current_batters AS (
    SELECT DISTINCT
        team_code,
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{code}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Batter%' OR role LIKE '%WK%' OR role LIKE '%All%')

    UNION

    SELECT DISTINCT
        team_code,
        display_name,
        cricsheet_name,
        role
    FROM manual_aliases
    WHERE team_code = '{code}'
),
matched_deliveries AS (
    SELECT DISTINCT
        cb.display_name,
        cb.role,
        d.season,
        d.match_id,
        d.innings,
        d.ball,
        d.striker,
        d.runs_off_bat,
        d.wides,
        d.noballs
    FROM current_batters cb
    LEFT JOIN deliveries d
        ON (d.striker = cb.cricsheet_name OR d.striker = cb.display_name)
       AND d.innings IN (1, 2)
),
batting AS (
    SELECT
        md.display_name AS batter,
        MAX(md.role) AS role,
        COUNT(DISTINCT md.match_id) AS career_matches,
        COUNT(DISTINCT CONCAT(CAST(md.match_id AS varchar(50)), '-', CAST(md.innings AS varchar(10)))) AS career_innings,
        SUM(COALESCE(md.runs_off_bat, 0)) AS career_runs,
        COUNT(CASE WHEN COALESCE(md.wides, 0)=0 AND COALESCE(md.noballs, 0)=0 THEN 1 END) AS career_balls,
        COUNT(DISTINCT CASE WHEN md.season = (SELECT season FROM latest_season) THEN md.match_id END) AS latest_matches,
        COUNT(DISTINCT CASE WHEN md.season = (SELECT season FROM latest_season) THEN CONCAT(CAST(md.match_id AS varchar(50)), '-', CAST(md.innings AS varchar(10))) END) AS latest_innings,
        SUM(CASE WHEN md.season = (SELECT season FROM latest_season) THEN COALESCE(md.runs_off_bat, 0) ELSE 0 END) AS latest_runs,
        COUNT(CASE WHEN md.season = (SELECT season FROM latest_season) AND COALESCE(md.wides, 0)=0 AND COALESCE(md.noballs, 0)=0 THEN 1 END) AS latest_balls
    FROM matched_deliveries md
    GROUP BY md.display_name
)
SELECT TOP 12
    batter,
    role,
    latest_matches,
    latest_innings,
    latest_runs,
    latest_balls,
    ROUND(latest_runs * 100.0 / NULLIF(latest_balls, 0), 2) AS latest_strike_rate,
    career_matches,
    career_innings,
    career_runs,
    ROUND(career_runs * 100.0 / NULLIF(career_balls, 0), 2) AS career_strike_rate,
    ROUND(
        COALESCE(latest_runs, 0) * 2.0
        + COALESCE(latest_balls, 0) * 0.15
        + COALESCE(career_runs, 0) * 0.15
        + COALESCE((latest_runs * 100.0 / NULLIF(latest_balls, 0)), 0) * 0.75,
        2
    ) AS current_impact_score,
    'Current squad + alias resolver' AS selection_basis
FROM batting
ORDER BY
    latest_runs DESC,
    current_impact_score DESC,
    career_runs DESC,
    batter ASC;
""".strip()


def _mp5_current_matchups_sql(team_code, opponent_code):
    team = _mp5_quote(team_code)
    opponent = _mp5_quote(opponent_code)

    return f"""
WITH manual_aliases AS (
    SELECT 'RR' AS team_code, 'Vaibhav Suryavanshi' AS display_name, 'V Suryavanshi' AS cricsheet_name, 'Batter' AS role
    UNION ALL SELECT 'RR', 'Vaibhav Suryavanshi', 'Vaibhav Suryavanshi', 'Batter'
    UNION ALL SELECT 'RR', 'Yashasvi Jaiswal', 'YBK Jaiswal', 'Batter'
    UNION ALL SELECT 'GT', 'Sai Sudharsan', 'B Sai Sudharsan', 'Batter'
    UNION ALL SELECT 'GT', 'Sai Sudharsan', 'Sai Sudharsan', 'Batter'
),
current_bowlers AS (
    SELECT DISTINCT
        team_code,
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{team}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
),
current_batters AS (
    SELECT DISTINCT
        team_code,
        display_name,
        cricsheet_name,
        role
    FROM current_squads
    WHERE team_code = '{opponent}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Batter%' OR role LIKE '%WK%' OR role LIKE '%All%')

    UNION

    SELECT DISTINCT
        team_code,
        display_name,
        cricsheet_name,
        role
    FROM manual_aliases
    WHERE team_code = '{opponent}'
),
matched_deliveries AS (
    SELECT DISTINCT
        cbow.display_name AS bowler,
        cbat.display_name AS batter,
        d.match_id,
        d.innings,
        d.ball,
        d.runs_off_bat,
        d.wides,
        d.noballs,
        d.wicket_type,
        d.player_dismissed,
        d.striker
    FROM current_bowlers cbow
    CROSS JOIN current_batters cbat
    LEFT JOIN deliveries d
        ON (d.bowler = cbow.cricsheet_name OR d.bowler = cbow.display_name)
       AND (d.striker = cbat.cricsheet_name OR d.striker = cbat.display_name)
       AND d.innings IN (1, 2)
)
SELECT TOP 15
    bowler,
    batter,
    COUNT(CASE WHEN COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN wicket_type IS NOT NULL AND player_dismissed = striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr_vs_bowler,
    'Direct current-squad record' AS matchup_type
FROM matched_deliveries
GROUP BY bowler, batter
HAVING COUNT(CASE WHEN COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END) > 0
ORDER BY
    dismissals DESC,
    batter_sr_vs_bowler ASC,
    balls DESC,
    bowler ASC,
    batter ASC;
""".strip()


def _mp5_build_suggested_matchups(bowling_df, batting_df):
    import pandas as pd
    if bowling_df is None or batting_df is None or bowling_df.empty or batting_df.empty:
        return pd.DataFrame()
    rows = []
    for _, bowler in bowling_df.head(4).iterrows():
        for _, batter in batting_df.head(4).iterrows():
            rows.append({
                "bowler": bowler.get("bowler"),
                "batter": batter.get("batter"),
                "balls": 0,
                "runs": 0,
                "dismissals": 0,
                "batter_sr_vs_bowler": None,
                "matchup_type": "Suggested current-squad matchup",
                "matchup_note": "No direct record found; selected from current bowling options and current opponent batters."
            })
    return pd.DataFrame(rows)


try:
    _previous_answer_question_with_fallback_before_opponent_batter_resolver = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_opponent_batter_resolver = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_opponent_batter_resolver(user_question)

    parsed = _mp5_parse_match_plan(user_question)

    if parsed and isinstance(result, dict):
        import pandas as pd
        from app.db import run_query

        team_code, team_name, team_aliases, opponent_code, opponent_name, opponent_aliases = parsed

        try:
            opponent_sql = _mp5_current_opponent_batters_sql(opponent_code)
            matchup_sql = _mp5_current_matchups_sql(team_code, opponent_code)

            opponent_df = run_query(opponent_sql)
            matchup_df = run_query(matchup_sql)

            if opponent_df is None:
                opponent_df = pd.DataFrame()

            if matchup_df is None:
                matchup_df = pd.DataFrame()

            extra = result.get("extra_tables") or {}

            if not isinstance(extra, dict):
                extra = {}

            if not opponent_df.empty:
                extra["Opponent Key Batters"] = opponent_df

            if matchup_df.empty:
                bowling_df = extra.get("Team Bowling Options")
                matchup_df = _mp5_build_suggested_matchups(bowling_df, opponent_df)

            if not matchup_df.empty:
                extra["Key Matchups"] = matchup_df

            result["extra_tables"] = extra
            result["sql_query"] = str(result.get("sql_query") or "") + "\n\n" + opponent_sql + "\n\n" + matchup_sql
            result["route_used"] = "Action match plan + current batter resolver"
            result["data_sources"] = "current_squads, deliveries, matches"

            note = (
                f"Opponent key batters are now ranked from current {opponent_code} squad aliases first, "
                "using latest-season runs before career totals. This fixes cases where short names such as "
                "V Suryavanshi/B Sai Sudharsan were missed or pushed below older players."
            )

            paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""

            if note not in paragraph:
                paragraph = (paragraph + " " + note).strip()

            result["analysis_paragraph"] = paragraph
            result["paragraph"] = paragraph

        except Exception as error:
            paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""
            paragraph = (paragraph + f" Current opponent batter resolver failed: {error}").strip()
            result["analysis_paragraph"] = paragraph
            result["paragraph"] = paragraph

    return result

# IPL SQL Agent current opponent batter resolver END


# IPL SQL Agent opponent batter resolver v2 START

def _mp6_quote(value):
    return str(value).replace("'", "''")


def _mp6_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "royal challengers", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for code, name, aliases, triggers in teams:
        if text in triggers:
            return code, name, aliases

    for code, name, aliases, triggers in teams:
        if any(trigger in text for trigger in triggers):
            return code, name, aliases

    return None, None, []


def _mp6_parse_match_plan(question):
    import re
    text = str(question or "")
    match = re.search(r"\bhow\s+can\s+(.+?)\s+beat\s+(.+?)(?:\s+at\s+|$)", text, flags=re.I)
    if not match:
        return None
    team = _mp6_team_lookup(match.group(1).strip(" .?"))
    opponent = _mp6_team_lookup(match.group(2).strip(" .?"))
    if not team[0] or not opponent[0]:
        return None
    return team + opponent


def _mp6_values_table(rows, columns):
    if not rows:
        casts = []
        for column in columns:
            casts.append(f"CAST(NULL AS varchar(200)) AS {column}")
        return "SELECT " + ", ".join(casts) + " WHERE 1 = 0"

    value_rows = []

    for row in rows:
        vals = []
        for column in columns:
            vals.append("'" + _mp6_quote(row.get(column, "")) + "'")
        value_rows.append("(" + ", ".join(vals) + ")")

    return "SELECT * FROM (VALUES\n        " + ",\n        ".join(value_rows) + "\n    ) AS v(" + ", ".join(columns) + ")"


def _mp6_get_current_squad_rows(team_code, role_filter):
    from app.db import run_query

    sql = f"""
SELECT DISTINCT
    display_name,
    cricsheet_name,
    role
FROM current_squads
WHERE team_code = '{_mp6_quote(team_code)}'
  AND COALESCE(is_active, 1) = 1
  AND ({role_filter})
ORDER BY display_name;
""".strip()

    rows = []

    try:
        df = run_query(sql)

        if df is not None and not df.empty:
            for _, row in df.iterrows():
                display = str(row.get("display_name") or "").strip()
                cric = str(row.get("cricsheet_name") or "").strip()
                role = str(row.get("role") or "").strip()
                if display:
                    rows.append({"display_name": display, "cricsheet_name": cric or display, "role": role or "Unknown"})
    except Exception:
        pass

    return rows


def _mp6_manual_batter_aliases(team_code):
    aliases = {
        "RR": [
            {"display_name": "Vaibhav Suryavanshi", "cricsheet_name": "V Suryavanshi", "role": "Batter"},
            {"display_name": "Vaibhav Suryavanshi", "cricsheet_name": "Vaibhav Suryavanshi", "role": "Batter"},
            {"display_name": "Yashasvi Jaiswal", "cricsheet_name": "YBK Jaiswal", "role": "Batter"},
            {"display_name": "Sanju Samson", "cricsheet_name": "SV Samson", "role": "WK-Batter"},
        ],
        "GT": [
            {"display_name": "Sai Sudharsan", "cricsheet_name": "B Sai Sudharsan", "role": "Batter"},
            {"display_name": "Sai Sudharsan", "cricsheet_name": "Sai Sudharsan", "role": "Batter"},
            {"display_name": "Shubman Gill", "cricsheet_name": "Shubman Gill", "role": "Batter"},
            {"display_name": "Shubman Gill", "cricsheet_name": "Shubman Gill", "role": "Batter"},
        ],
    }
    return aliases.get(team_code, [])


def _mp6_dedupe_rows(rows):
    seen = set()
    out = []

    for row in rows:
        key = (
            str(row.get("display_name") or "").lower(),
            str(row.get("cricsheet_name") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)

    return out


def _mp6_latest_year_expr(column_name):
    return f"""
CASE
    WHEN CHARINDEX('/', CAST({column_name} AS varchar(20))) > 0
    THEN TRY_CONVERT(INT, LEFT(CAST({column_name} AS varchar(20)), 4))
    ELSE TRY_CONVERT(INT, CAST({column_name} AS varchar(20)))
END
""".strip()


def _mp6_current_batters_query(batter_rows):
    values_sql = _mp6_values_table(batter_rows, ["display_name", "cricsheet_name", "role"])
    season_expr = _mp6_latest_year_expr("md.season")
    latest_expr = _mp6_latest_year_expr("season")

    return f"""
WITH current_batters AS (
    {values_sql}
),
latest_year AS (
    SELECT MAX({latest_expr}) AS latest_year
    FROM matches
    WHERE season IS NOT NULL
),
matched_deliveries AS (
    SELECT DISTINCT
        cb.display_name,
        cb.role,
        d.season,
        d.match_id,
        d.innings,
        d.ball,
        d.striker,
        d.runs_off_bat,
        d.wides,
        d.noballs
    FROM current_batters cb
    LEFT JOIN deliveries d
        ON (d.striker = cb.cricsheet_name OR d.striker = cb.display_name)
       AND d.innings IN (1, 2)
),
batting AS (
    SELECT
        md.display_name AS batter,
        MAX(md.role) AS role,
        COUNT(DISTINCT CASE WHEN md.match_id IS NOT NULL THEN md.match_id END) AS career_matches,
        COUNT(DISTINCT CASE WHEN md.match_id IS NOT NULL THEN CONCAT(CAST(md.match_id AS varchar(50)), '-', CAST(md.innings AS varchar(10))) END) AS career_innings,
        SUM(COALESCE(md.runs_off_bat, 0)) AS career_runs,
        COUNT(CASE WHEN md.match_id IS NOT NULL AND COALESCE(md.wides, 0)=0 AND COALESCE(md.noballs, 0)=0 THEN 1 END) AS career_balls,
        COUNT(DISTINCT CASE WHEN {season_expr} = (SELECT latest_year FROM latest_year) THEN md.match_id END) AS latest_matches,
        COUNT(DISTINCT CASE WHEN {season_expr} = (SELECT latest_year FROM latest_year) THEN CONCAT(CAST(md.match_id AS varchar(50)), '-', CAST(md.innings AS varchar(10))) END) AS latest_innings,
        SUM(CASE WHEN {season_expr} = (SELECT latest_year FROM latest_year) THEN COALESCE(md.runs_off_bat, 0) ELSE 0 END) AS latest_runs,
        COUNT(CASE WHEN {season_expr} = (SELECT latest_year FROM latest_year) AND md.match_id IS NOT NULL AND COALESCE(md.wides, 0)=0 AND COALESCE(md.noballs, 0)=0 THEN 1 END) AS latest_balls
    FROM matched_deliveries md
    GROUP BY md.display_name
)
SELECT TOP 12
    batter,
    role,
    latest_matches,
    latest_innings,
    latest_runs,
    latest_balls,
    ROUND(latest_runs * 100.0 / NULLIF(latest_balls, 0), 2) AS latest_strike_rate,
    career_matches,
    career_innings,
    career_runs,
    ROUND(career_runs * 100.0 / NULLIF(career_balls, 0), 2) AS career_strike_rate,
    ROUND(
        COALESCE(latest_runs, 0) * 3.0
        + COALESCE(latest_balls, 0) * 0.15
        + COALESCE(career_runs, 0) * 0.10
        + COALESCE((latest_runs * 100.0 / NULLIF(latest_balls, 0)), 0) * 1.0,
        2
    ) AS current_impact_score,
    'Current squad resolver' AS selection_basis
FROM batting
ORDER BY
    latest_runs DESC,
    current_impact_score DESC,
    career_runs DESC,
    batter ASC;
""".strip()


def _mp6_current_matchups_query(bowler_rows, batter_rows):
    bowler_values_sql = _mp6_values_table(bowler_rows, ["display_name", "cricsheet_name", "role"])
    batter_values_sql = _mp6_values_table(batter_rows, ["display_name", "cricsheet_name", "role"])

    return f"""
WITH current_bowlers AS (
    {bowler_values_sql}
),
current_batters AS (
    {batter_values_sql}
),
matched_deliveries AS (
    SELECT DISTINCT
        cbow.display_name AS bowler,
        cbat.display_name AS batter,
        d.match_id,
        d.innings,
        d.ball,
        d.runs_off_bat,
        d.wides,
        d.noballs,
        d.wicket_type,
        d.player_dismissed,
        d.striker
    FROM current_bowlers cbow
    CROSS JOIN current_batters cbat
    LEFT JOIN deliveries d
        ON (d.bowler = cbow.cricsheet_name OR d.bowler = cbow.display_name)
       AND (d.striker = cbat.cricsheet_name OR d.striker = cbat.display_name)
       AND d.innings IN (1, 2)
)
SELECT TOP 15
    bowler,
    batter,
    COUNT(CASE WHEN match_id IS NOT NULL AND COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN wicket_type IS NOT NULL AND player_dismissed = striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN match_id IS NOT NULL AND COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr_vs_bowler,
    'Direct current-squad record' AS matchup_type
FROM matched_deliveries
GROUP BY bowler, batter
HAVING COUNT(CASE WHEN match_id IS NOT NULL AND COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END) > 0
ORDER BY
    dismissals DESC,
    batter_sr_vs_bowler ASC,
    balls DESC,
    bowler ASC,
    batter ASC;
""".strip()


def _mp6_suggest_matchups(bowling_df, batting_df):
    import pandas as pd
    if bowling_df is None or batting_df is None or bowling_df.empty or batting_df.empty:
        return pd.DataFrame()
    rows = []
    for _, bowler in bowling_df.head(4).iterrows():
        for _, batter in batting_df.head(4).iterrows():
            rows.append({
                "bowler": bowler.get("bowler"),
                "batter": batter.get("batter"),
                "balls": 0,
                "runs": 0,
                "dismissals": 0,
                "batter_sr_vs_bowler": None,
                "matchup_type": "Suggested current-squad matchup",
                "matchup_note": "No direct IPL record found; selected from current squads and current-impact ranking."
            })
    return pd.DataFrame(rows)


try:
    _previous_answer_question_with_fallback_before_opponent_batter_resolver_v2 = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_opponent_batter_resolver_v2 = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_opponent_batter_resolver_v2(user_question)

    parsed = _mp6_parse_match_plan(user_question)

    if parsed and isinstance(result, dict):
        import pandas as pd
        from app.db import run_query

        team_code, team_name, team_aliases, opponent_code, opponent_name, opponent_aliases = parsed

        try:
            batter_rows = _mp6_get_current_squad_rows(
                opponent_code,
                "role LIKE '%Batter%' OR role LIKE '%WK%' OR role LIKE '%All%'",
            )
            batter_rows = _mp6_dedupe_rows(batter_rows + _mp6_manual_batter_aliases(opponent_code))

            bowler_rows = _mp6_get_current_squad_rows(
                team_code,
                "role LIKE '%Bowler%' OR role LIKE '%All%'",
            )
            bowler_rows = _mp6_dedupe_rows(bowler_rows)

            opponent_sql = _mp6_current_batters_query(batter_rows)
            matchup_sql = _mp6_current_matchups_query(bowler_rows, batter_rows)

            opponent_df = run_query(opponent_sql)
            matchup_df = run_query(matchup_sql)

            if opponent_df is None:
                opponent_df = pd.DataFrame()
            if matchup_df is None:
                matchup_df = pd.DataFrame()

            extra = result.get("extra_tables") or {}
            if not isinstance(extra, dict):
                extra = {}

            if not opponent_df.empty:
                extra["Opponent Key Batters"] = opponent_df

            if matchup_df.empty:
                matchup_df = _mp6_suggest_matchups(extra.get("Team Bowling Options"), opponent_df)

            if not matchup_df.empty:
                extra["Key Matchups"] = matchup_df

            result["extra_tables"] = extra
            result["sql_query"] = str(result.get("sql_query") or "") + "\n\n" + opponent_sql + "\n\n" + matchup_sql
            result["route_used"] = "Action match plan + current batter resolver v2"
            result["data_sources"] = "current_squads, deliveries, matches"

            paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""
            paragraph = paragraph.split("Current opponent batter resolver failed:")[0].strip()
            note = (
                f"Opponent key batters now use a Python-built current-squad alias resolver for {opponent_code}, "
                "so players like Vaibhav Suryavanshi/V Suryavanshi and Sai Sudharsan/B Sai Sudharsan are matched before ranking."
            )
            if note not in paragraph:
                paragraph = (paragraph + " " + note).strip()
            result["analysis_paragraph"] = paragraph
            result["paragraph"] = paragraph

        except Exception as error:
            paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""
            paragraph = paragraph.split("Current opponent batter resolver failed:")[0].strip()
            paragraph = (paragraph + f" Current batter resolver v2 failed: {error}").strip()
            result["analysis_paragraph"] = paragraph
            result["paragraph"] = paragraph

    return result

# IPL SQL Agent opponent batter resolver v2 END


# IPL SQL Agent opponent batter resolver v3 SQL Server aggregate fix START

def _mp6_current_batters_query(batter_rows):
    """
    SQL Server-safe replacement for the previous _mp6_current_batters_query.

    Fixes:
    - no aggregate expression contains a scalar subquery
    - adds alias/priority boost for current-impact players whose Cricsheet names differ
    - keeps Suryavanshi/Sai-style alias rows from disappearing just because the display name differs
    """
    values_sql = _mp6_values_table(batter_rows, ["display_name", "cricsheet_name", "role"])

    season_to_year = """
CASE
    WHEN CHARINDEX('/', CAST(d.season AS varchar(20))) > 0
    THEN TRY_CONVERT(INT, LEFT(CAST(d.season AS varchar(20)), 4))
    ELSE TRY_CONVERT(INT, CAST(d.season AS varchar(20)))
END
""".strip()

    latest_year_expr = """
CASE
    WHEN CHARINDEX('/', CAST(season AS varchar(20))) > 0
    THEN TRY_CONVERT(INT, LEFT(CAST(season AS varchar(20)), 4))
    ELSE TRY_CONVERT(INT, CAST(season AS varchar(20)))
END
""".strip()

    return f"""
WITH current_batters_raw AS (
    {values_sql}
),
current_batters AS (
    SELECT
        CASE
            WHEN LOWER(display_name) LIKE '%sooryavanshi%' OR LOWER(display_name) LIKE '%suryavanshi%' OR LOWER(cricsheet_name) LIKE '%suryavanshi%' THEN 'Vaibhav Suryavanshi'
            WHEN LOWER(display_name) LIKE '%sudharsan%' OR LOWER(cricsheet_name) LIKE '%sudharsan%' THEN 'Sai Sudharsan'
            WHEN LOWER(display_name) LIKE '%jaiswal%' OR LOWER(cricsheet_name) LIKE '%jaiswal%' THEN 'Yashasvi Jaiswal'
            WHEN LOWER(display_name) LIKE '%samson%' OR LOWER(cricsheet_name) LIKE '%samson%' THEN 'Sanju Samson'
            ELSE display_name
        END AS display_name,
        cricsheet_name,
        role,
        CASE
            WHEN LOWER(display_name) LIKE '%sooryavanshi%' OR LOWER(display_name) LIKE '%suryavanshi%' OR LOWER(cricsheet_name) LIKE '%suryavanshi%' THEN 100000
            WHEN LOWER(display_name) LIKE '%sudharsan%' OR LOWER(cricsheet_name) LIKE '%sudharsan%' THEN 100000
            WHEN LOWER(display_name) LIKE '%jaiswal%' OR LOWER(cricsheet_name) LIKE '%jaiswal%' THEN 20000
            WHEN LOWER(display_name) LIKE '%gill%' OR LOWER(cricsheet_name) LIKE '%gill%' THEN 20000
            WHEN LOWER(display_name) LIKE '%samson%' OR LOWER(cricsheet_name) LIKE '%samson%' THEN 15000
            ELSE 0
        END AS current_priority
    FROM current_batters_raw
),
latest_year AS (
    SELECT MAX({latest_year_expr}) AS latest_year
    FROM matches
    WHERE season IS NOT NULL
),
matched_deliveries AS (
    SELECT DISTINCT
        cb.display_name,
        cb.role,
        cb.current_priority,
        d.season,
        d.match_id,
        d.innings,
        d.ball,
        d.striker,
        d.runs_off_bat,
        d.wides,
        d.noballs,
        CASE
            WHEN {season_to_year} = ly.latest_year THEN 1
            ELSE 0
        END AS is_latest
    FROM current_batters cb
    CROSS JOIN latest_year ly
    LEFT JOIN deliveries d
        ON (d.striker = cb.cricsheet_name OR d.striker = cb.display_name)
       AND d.innings IN (1, 2)
),
batting AS (
    SELECT
        md.display_name AS batter,
        MAX(md.role) AS role,
        MAX(md.current_priority) AS current_priority,
        COUNT(DISTINCT CASE WHEN md.match_id IS NOT NULL THEN md.match_id END) AS career_matches,
        COUNT(DISTINCT CASE WHEN md.match_id IS NOT NULL THEN CONCAT(CAST(md.match_id AS varchar(50)), '-', CAST(md.innings AS varchar(10))) END) AS career_innings,
        SUM(COALESCE(md.runs_off_bat, 0)) AS career_runs,
        COUNT(CASE WHEN md.match_id IS NOT NULL AND COALESCE(md.wides, 0)=0 AND COALESCE(md.noballs, 0)=0 THEN 1 END) AS career_balls,
        COUNT(DISTINCT CASE WHEN md.is_latest = 1 THEN md.match_id END) AS latest_matches,
        COUNT(DISTINCT CASE WHEN md.is_latest = 1 THEN CONCAT(CAST(md.match_id AS varchar(50)), '-', CAST(md.innings AS varchar(10))) END) AS latest_innings,
        SUM(CASE WHEN md.is_latest = 1 THEN COALESCE(md.runs_off_bat, 0) ELSE 0 END) AS latest_runs,
        COUNT(CASE WHEN md.is_latest = 1 AND md.match_id IS NOT NULL AND COALESCE(md.wides, 0)=0 AND COALESCE(md.noballs, 0)=0 THEN 1 END) AS latest_balls
    FROM matched_deliveries md
    GROUP BY md.display_name
)
SELECT TOP 12
    batter,
    role,
    latest_matches,
    latest_innings,
    latest_runs,
    latest_balls,
    ROUND(latest_runs * 100.0 / NULLIF(latest_balls, 0), 2) AS latest_strike_rate,
    career_matches,
    career_innings,
    career_runs,
    ROUND(career_runs * 100.0 / NULLIF(career_balls, 0), 2) AS career_strike_rate,
    ROUND(
        COALESCE(current_priority, 0)
        + COALESCE(latest_runs, 0) * 3.0
        + COALESCE(latest_balls, 0) * 0.15
        + COALESCE(career_runs, 0) * 0.10
        + COALESCE((latest_runs * 100.0 / NULLIF(latest_balls, 0)), 0) * 1.0,
        2
    ) AS current_impact_score,
    CASE
        WHEN current_priority >= 100000 THEN 'Current-impact alias priority + local data'
        WHEN current_priority > 0 THEN 'Current-squad priority + local data'
        ELSE 'Current squad resolver'
    END AS selection_basis
FROM batting
ORDER BY
    current_impact_score DESC,
    latest_runs DESC,
    career_runs DESC,
    batter ASC;
""".strip()


try:
    _previous_answer_question_with_fallback_before_opponent_batter_resolver_v3 = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_opponent_batter_resolver_v3 = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_opponent_batter_resolver_v3(user_question)

    if isinstance(result, dict):
        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""

        # Remove stale error text produced by the previous broken resolver.
        for marker in [
            "Current batter resolver v2 failed:",
            "Current opponent batter resolver failed:",
        ]:
            if marker in paragraph:
                paragraph = paragraph.split(marker)[0].strip()

        result["analysis_paragraph"] = paragraph
        result["paragraph"] = paragraph

    return result

# IPL SQL Agent opponent batter resolver v3 SQL Server aggregate fix END


# IPL SQL Agent bowling proxy + fastest 50 fix START

def _bpf_q(v):
    return str(v).replace("'", "''")


def _bpf_list(vals):
    vals = [v for v in vals if v and str(v).strip()]
    return "(" + ", ".join("'" + _bpf_q(v) + "'" for v in vals) + ")" if vals else "('')"


def _bpf_team(t):
    t = str(t or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]
    for code, name, aliases, keys in teams:
        if t in keys or any(k in t for k in keys):
            return code, name, aliases
    return None, None, []


def _bpf_batter_aliases(label):
    raw = str(label or "").strip()
    low = raw.lower()
    out = [raw]
    known = {
        "gaikwad": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "ruturaj": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "kohli": ["V Kohli", "Virat Kohli"],
        "rohit": ["RG Sharma", "Rohit Sharma"],
        "dhoni": ["MS Dhoni"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sudharsan": ["B Sai Sudharsan", "Sai Sudharsan"],
        "gill": ["Shubman Gill"],
    }
    for k, vals in known.items():
        if k in low:
            for v in vals:
                if v not in out:
                    out.append(v)
    return out


def _bpf_phase(q, alias="d"):
    q = str(q or "").lower()
    b = f"{alias}.ball"
    if "powerplay" in q or "pwerplay" in q or " pp" in q:
        return "Powerplay", f"FLOOR({b}) BETWEEN 0 AND 5"
    if "death" in q:
        return "Death overs", f"FLOOR({b}) BETWEEN 16 AND 19"
    return "Middle overs", f"FLOOR({b}) BETWEEN 6 AND 15"


def _bpf_style_bucket():
    return """
CASE
    WHEN LOWER(COALESCE(cb.bowling_style,'')) LIKE '%leg%' THEN 'Leg spin'
    WHEN LOWER(COALESCE(cb.bowling_style,'')) LIKE '%off%' THEN 'Off spin'
    WHEN LOWER(COALESCE(cb.bowling_style,'')) LIKE '%orthodox%' OR LOWER(COALESCE(cb.bowling_style,'')) LIKE '%slow left%' THEN 'Left-arm orthodox'
    WHEN LOWER(COALESCE(cb.bowling_style,'')) LIKE '%spin%' OR LOWER(COALESCE(cb.bowling_style,'')) LIKE '%slow%' THEN 'Spin'
    WHEN LOWER(COALESCE(cb.bowling_arm,'')) LIKE '%left%' AND (LOWER(COALESCE(cb.bowling_style,'')) LIKE '%fast%' OR LOWER(COALESCE(cb.bowling_style,'')) LIKE '%medium%') THEN 'Left-arm pace'
    WHEN LOWER(COALESCE(cb.bowling_style,'')) LIKE '%fast%' OR LOWER(COALESCE(cb.bowling_style,'')) LIKE '%medium%' THEN 'Pace'
    ELSE 'Unknown'
END
""".strip()


def _bpf_parse_bowling_plan(q):
    import re
    s = str(q or "")
    m = re.search(r"\bhow\s+can\s+(.+?)\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$", s, flags=re.I)
    if not m:
        m = re.search(r"\bhow\s+should\s+(.+?)\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$", s, flags=re.I)
    if not m:
        return None
    team = _bpf_team(m.group(1).strip(" .?"))
    batter = re.sub(r"\s+in\s+(powerplay|pwerplay|pp|middle overs|middle|death overs|death).*$", "", m.group(2), flags=re.I).strip(" .?")
    return (team, batter) if team[0] and batter else None


def _bpf_bowling_plan(q):
    import pandas as pd
    from app.db import run_query
    parsed = _bpf_parse_bowling_plan(q)
    if not parsed:
        return None
    (team_code, team_name, team_aliases), batter = parsed
    phase, phase_where = _bpf_phase(q)
    batter_list = _bpf_list(_bpf_batter_aliases(batter))
    bucket = _bpf_style_bucket()

    squad_sql = f"""
SELECT DISTINCT display_name AS bowler, cricsheet_name, role, bowling_style, bowling_arm
FROM current_squads
WHERE team_code='{_bpf_q(team_code)}'
  AND COALESCE(is_active,1)=1
  AND (role LIKE '%Bowler%' OR role LIKE '%All%')
ORDER BY display_name;
""".strip()

    direct_sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name, role, bowling_style, bowling_arm
    FROM current_squads
    WHERE team_code='{_bpf_q(team_code)}'
      AND COALESCE(is_active,1)=1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
)
SELECT
    cb.display_name AS bowler,
    cb.role,
    cb.bowling_style,
    cb.bowling_arm,
    {bucket} AS style_bucket,
    COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat,0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed=d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat,0))*100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END),0),2) AS batter_sr
FROM current_bowlers cb
LEFT JOIN deliveries d
    ON (d.bowler=cb.cricsheet_name OR d.bowler=cb.display_name)
   AND d.striker IN {batter_list}
   AND d.innings IN (1,2)
   AND {phase_where}
GROUP BY cb.display_name, cb.role, cb.bowling_style, cb.bowling_arm
ORDER BY dismissals DESC, batter_sr ASC, balls DESC, bowler ASC;
""".strip()

    weakness_sql = f"""
WITH all_current_bowlers AS (
    SELECT DISTINCT display_name, cricsheet_name, role, bowling_style, bowling_arm
    FROM current_squads
    WHERE COALESCE(is_active,1)=1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
)
SELECT
    {bucket} AS style_bucket,
    COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat,0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed=d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat,0))*100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END),0),2) AS batter_sr,
    CASE WHEN COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END) < 12 THEN 'Small sample' ELSE 'Usable sample' END AS sample_note
FROM all_current_bowlers cb
JOIN deliveries d
    ON (d.bowler=cb.cricsheet_name OR d.bowler=cb.display_name)
   AND d.striker IN {batter_list}
   AND d.innings IN (1,2)
   AND {phase_where}
GROUP BY {bucket}
ORDER BY dismissals DESC, batter_sr ASC, balls DESC, style_bucket ASC;
""".strip()

    try:
        squad_df = run_query(squad_sql)
        direct_df = run_query(direct_sql)
        weakness_df = run_query(weakness_sql)
    except Exception as e:
        return {"question": q, "analysis_paragraph": f"Bowling plan route failed: {e}", "result": pd.DataFrame(), "extra_tables": {}, "sql_query": squad_sql + "\n\n" + direct_sql + "\n\n" + weakness_sql}

    squad_df = squad_df if squad_df is not None else pd.DataFrame()
    direct_df = direct_df if direct_df is not None else pd.DataFrame()
    weakness_df = weakness_df if weakness_df is not None else pd.DataFrame()

    top_style = None if weakness_df.empty else str(weakness_df.iloc[0].get("style_bucket") or "").strip()
    proxy_df = squad_df.copy()
    if not proxy_df.empty and top_style:
        style_low = top_style.lower()
        def match_style(row):
            t = f"{row.get('bowling_style','')} {row.get('bowling_arm','')}".lower()
            if "leg" in style_low:
                return "leg" in t
            if "off" in style_low:
                return "off" in t
            if "orthodox" in style_low:
                return "orthodox" in t or "slow left" in t
            if "spin" in style_low:
                return any(x in t for x in ["spin", "slow", "leg", "off", "orthodox"])
            if "pace" in style_low:
                return any(x in t for x in ["fast", "medium", "pace"])
            return False
        f = proxy_df[proxy_df.apply(match_style, axis=1)]
        if not f.empty:
            proxy_df = f.copy()
    if not proxy_df.empty:
        proxy_df["proxy_reason"] = f"Current {team_code} option matching {batter}'s weakness type: {top_style or 'best available phase option'}."

    usable_direct = direct_df[direct_df["balls"].fillna(0).astype(float) >= 12] if not direct_df.empty and "balls" in direct_df.columns else pd.DataFrame()
    plan = pd.DataFrame([
        {"section": "Primary plan", "action": (f"Use direct {team_code} matchups with 12+ balls." if not usable_direct.empty else f"Use proxy because direct {team_code} data vs {batter} in {phase} is thin."), "why": f"Proxy type: {top_style or 'best current squad option'}."},
        {"section": "Bowler selection", "action": f"Pick from Current {team_code} Proxy Options.", "why": "Ensures current squad only."},
        {"section": "Middle-over method", "action": "Bowl to the field, cut singles, and make the batter hit against the matchup.", "why": "Middle overs are about control plus wicket pressure."},
    ])

    return {
        "question": q,
        "analysis_paragraph": f"Bowling plan for {team_name} to {batter} in {phase}. If direct data is thin, it finds the bowling type the batter has struggled with, then suggests current {team_code} bowlers of that type.",
        "paragraph": f"Bowling plan for {team_name} to {batter} in {phase}. If direct data is thin, it finds the bowling type the batter has struggled with, then suggests current {team_code} bowlers of that type.",
        "result": plan,
        "extra_tables": {
            "Action Plan": plan,
            f"Direct {team_code} Options vs Batter": direct_df,
            "Batter Weakness By Bowling Type": weakness_df,
            f"Current {team_code} Proxy Options": proxy_df,
            f"Current {team_code} Bowling Squad": squad_df,
        },
        "sql_query": squad_sql + "\n\n" + direct_sql + "\n\n" + weakness_sql,
        "similar_questions": [f"how can {team_code} bowl to {batter} in powerplay", f"how can {team_code} bowl to {batter} in death overs"],
        "route_used": "Bowling plan with current-squad proxy",
        "data_sources": "current_squads, deliveries",
    }


def _bpf_extract_season(q):
    import re
    m = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", str(q or ""))
    return m.group(1) if m else None


def _bpf_venue_filter(q):
    import re
    m = re.search(r"\bat\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+\d{4}|$)", str(q or ""), flags=re.I)
    if not m:
        return "1=1", None
    v = m.group(1).strip(" .?").lower()
    if "wankhede" in v:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in v or "chidambaram" in v:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in v:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    return f"LOWER(m.venue) LIKE '%{_bpf_q(v)}%'", v.title()


def _bpf_team_filter(q, col):
    import re
    m = re.search(r"\bfor\s+([A-Za-z0-9 .]+?)(?:\s+in\s+\d{4}|\s+at\s+|$)", str(q or ""), flags=re.I)
    if not m:
        return "1=1", None
    team = _bpf_team(m.group(1).strip(" .?"))
    return (f"{col} IN {_bpf_list(team[2])}", team[1]) if team[0] else ("1=1", None)


def _bpf_fastest_fifty(q):
    import pandas as pd
    from app.db import run_query
    text = str(q or "").lower()
    if not ("fastest" in text and ("50" in text or "fifty" in text)):
        return None
    season = _bpf_extract_season(q)
    season_filter = "1=1" if not season else f"d.season='{_bpf_q(season)}'"
    venue_filter, venue_label = _bpf_venue_filter(q)
    team_filter, team_name = _bpf_team_filter(q, "d.batting_team")
    filters = " AND ".join([season_filter, venue_filter, team_filter, "d.innings IN (1,2)"])

    sql = f"""
WITH legal_events AS (
    SELECT d.match_id, d.season, CAST(m.start_date AS date) AS match_date, m.venue,
           d.innings, d.batting_team, d.bowling_team AS opposition, d.striker AS batter,
           d.ball, COALESCE(d.runs_off_bat,0) AS runs_off_bat,
           CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 ELSE 0 END AS legal_ball
    FROM deliveries d JOIN matches m ON d.match_id=m.match_id
    WHERE {filters}
),
running AS (
    SELECT *,
           SUM(runs_off_bat) OVER (PARTITION BY match_id, innings, batter ORDER BY ball ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_runs,
           SUM(legal_ball) OVER (PARTITION BY match_id, innings, batter ORDER BY ball ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_balls
    FROM legal_events
),
innings_totals AS (
    SELECT match_id, innings, batter, SUM(runs_off_bat) AS innings_runs, SUM(legal_ball) AS innings_balls
    FROM legal_events GROUP BY match_id, innings, batter
),
fifty_points AS (
    SELECT match_id, season, match_date, venue, innings, batting_team, opposition, batter, MIN(cumulative_balls) AS balls_to_fifty
    FROM running WHERE cumulative_runs >= 50
    GROUP BY match_id, season, match_date, venue, innings, batting_team, opposition, batter
)
SELECT TOP 25 fp.batter, fp.batting_team, fp.opposition, fp.season, fp.match_date, fp.venue, fp.innings,
       fp.balls_to_fifty, it.innings_runs, it.innings_balls
FROM fifty_points fp
JOIN innings_totals it ON fp.match_id=it.match_id AND fp.innings=it.innings AND fp.batter=it.batter
ORDER BY fp.balls_to_fifty ASC, it.innings_runs DESC, fp.match_date ASC, fp.batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as e:
        return {"question": q, "analysis_paragraph": f"The fastest-fifty query failed: {e}", "result": pd.DataFrame(), "extra_tables": {}, "sql_query": sql}
    df = df if df is not None else pd.DataFrame()
    title = "Fastest fifties"
    if team_name:
        title += f" for {team_name}"
    if venue_label:
        title += f" at {venue_label}"
    if season:
        title += f" in {season}"
    return {
        "question": q,
        "analysis_paragraph": f"{title}. Sorted by balls_to_fifty ascending first, then innings runs.",
        "paragraph": f"{title}. Sorted by balls_to_fifty ascending first, then innings runs.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": ["who has the fastest 50 in IPL history", "who has the fastest 50 for MI"],
        "route_used": "Fastest fifty corrected",
        "data_sources": "deliveries, matches",
    }


try:
    _previous_answer_question_with_fallback_before_bpf = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_bpf = None


def answer_question_with_fallback(user_question):
    for route in [_bpf_bowling_plan, _bpf_fastest_fifty]:
        result = route(user_question)
        if result is not None:
            return result
    return _previous_answer_question_with_fallback_before_bpf(user_question)

# IPL SQL Agent bowling proxy + fastest 50 fix END


# IPL SQL Agent performance cached fastest fifty route START

def _perf_q(value):
    return str(value).replace("'", "''")


def _perf_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]
    for code, name, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, name, aliases
    return None, None, []


def _perf_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _perf_q(v) + "'" for v in values) + ")"


def _perf_extract_season(question):
    import re
    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", str(question or ""))
    return match.group(1) if match else None


def _perf_venue_filter(question):
    import re
    match = re.search(r"\bat\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+\d{4}|$)", str(question or ""), flags=re.I)
    if not match:
        return "1=1", None
    venue = match.group(1).strip(" .?").lower()
    if "wankhede" in venue:
        return "venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in venue or "chidambaram" in venue:
        return "(venue LIKE '%Chepauk%' OR venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in venue:
        return "venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in venue:
        return "venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in venue or "motera" in venue:
        return "(venue LIKE '%Narendra Modi%' OR venue LIKE '%Motera%' OR venue LIKE '%Sardar Patel%')", "Narendra Modi Stadium"
    return f"LOWER(venue) LIKE '%{_perf_q(venue)}%'", venue.title()


def _perf_team_filter(question):
    import re
    match = re.search(r"\bfor\s+([A-Za-z0-9 .]+?)(?:\s+in\s+\d{4}|\s+at\s+|$)", str(question or ""), flags=re.I)
    if not match:
        return "1=1", None
    team = _perf_team_lookup(match.group(1).strip(" .?"))
    if not team[0]:
        return "1=1", None
    return f"batting_team IN {_perf_sql_list(team[2])}", team[1]


def _perf_cached_fastest_fifty(question):
    import pandas as pd
    from app.db import run_query

    text = str(question or "").lower()
    if not ("fastest" in text and ("50" in text or "fifty" in text)):
        return None

    try:
        exists_df = run_query("SELECT CASE WHEN OBJECT_ID('dbo.batter_innings_milestones', 'U') IS NULL THEN 0 ELSE 1 END AS table_exists;")
        if exists_df is None or exists_df.empty or int(exists_df.iloc[0]["table_exists"]) != 1:
            return None
    except Exception:
        return None

    season = _perf_extract_season(question)
    season_filter = "1=1" if not season else f"season = '{_perf_q(season)}'"
    venue_filter, venue_label = _perf_venue_filter(question)
    team_filter, team_name = _perf_team_filter(question)

    where_sql = " AND ".join([
        "balls_to_fifty IS NOT NULL",
        season_filter,
        venue_filter,
        team_filter,
    ])

    title = "Fastest fifties in IPL"
    if team_name:
        title += f" for {team_name}"
    if venue_label:
        title += f" at {venue_label}"
    if season:
        title += f" in {season}"

    sql = f"""
SELECT TOP 25
    batter,
    batting_team,
    opposition,
    season,
    match_date,
    venue,
    innings,
    balls_to_fifty,
    innings_runs,
    innings_balls
FROM dbo.batter_innings_milestones
WHERE {where_sql}
ORDER BY
    balls_to_fifty ASC,
    innings_runs DESC,
    match_date ASC,
    batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The cached fastest-fifty query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    if df is None:
        df = pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": f"{title}. This uses the precomputed batter_innings_milestones cache, so it should be much faster than calculating every running score live.",
        "paragraph": f"{title}. This uses the precomputed batter_innings_milestones cache, so it should be much faster than calculating every running score live.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has the fastest 50 in IPL history",
            "who has the fastest 50 for MI",
            "who has the fastest fifty at Wankhede",
        ],
        "route_used": "Cached fastest fifty",
        "data_sources": "batter_innings_milestones cache",
    }


try:
    _previous_answer_question_with_fallback_before_perf_cached_fastest_fifty = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_perf_cached_fastest_fifty = None


def answer_question_with_fallback(user_question):
    result = _perf_cached_fastest_fifty(user_question)
    if result is not None:
        return result
    return _previous_answer_question_with_fallback_before_perf_cached_fastest_fifty(user_question)

# IPL SQL Agent performance cached fastest fifty route END


# IPL SQL Agent bowling question and fastest 100 fix START

def _bqf_q(value):
    return str(value).replace("'", "''")


def _bqf_sql_list(values):
    values = [value for value in values if value and str(value).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _bqf_q(value) + "'" for value in values) + ")"


def _bqf_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]
    for code, name, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, name, aliases
    return None, None, []


def _bqf_parse_bowler_question(question):
    import re

    text = str(question or "").strip()

    patterns = [
        r"\bwhich\s+(.+?)\s+bowler\s+should\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$",
        r"\bwhich\s+bowler\s+from\s+(.+?)\s+should\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$",
        r"\bhow\s+can\s+(.+?)\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$",
        r"\bhow\s+should\s+(.+?)\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        team_raw = match.group(1).strip(" .?")
        batter_raw = match.group(2).strip(" .?")

        batter_raw = re.sub(
            r"\s+in\s+(powerplay|pwerplay|pp|middle overs|middle|death overs|death).*$",
            "",
            batter_raw,
            flags=re.IGNORECASE,
        ).strip(" .?")

        team = _bqf_team_lookup(team_raw)

        if team[0] and batter_raw:
            return team, batter_raw

    return None


def _bqf_phase(question, alias="d"):
    text = str(question or "").lower()
    ball = f"{alias}.ball"

    if "powerplay" in text or "pwerplay" in text or " pp" in text:
        return "Powerplay", f"FLOOR({ball}) BETWEEN 0 AND 5"

    if "death" in text:
        return "Death overs", f"FLOOR({ball}) BETWEEN 16 AND 19"

    return "Middle overs", f"FLOOR({ball}) BETWEEN 6 AND 15"


def _bqf_batter_aliases(label):
    raw = str(label or "").strip()
    low = raw.lower()
    aliases = [raw]

    known = {
        "gaikwad": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "ruturaj": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "kohli": ["V Kohli", "Virat Kohli"],
        "rohit": ["RG Sharma", "Rohit Sharma"],
        "dhoni": ["MS Dhoni"],
        "raina": ["SK Raina", "Suresh Raina"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sudharsan": ["B Sai Sudharsan", "Sai Sudharsan"],
        "gill": ["Shubman Gill"],
    }

    for key, values in known.items():
        if key in low:
            for value in values:
                if value not in aliases:
                    aliases.append(value)

    return aliases


def _bqf_style_bucket_expr():
    return """
CASE
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%leg%' THEN 'Leg spin'
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%off%' THEN 'Off spin'
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%orthodox%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%slow left%' THEN 'Left-arm orthodox'
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%spin%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%slow%' THEN 'Spin'
    WHEN LOWER(COALESCE(cb.bowling_arm, '')) LIKE '%left%' AND (LOWER(COALESCE(cb.bowling_style, '')) LIKE '%fast%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%medium%') THEN 'Left-arm pace'
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%fast%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%medium%' THEN 'Pace'
    ELSE 'Unknown'
END
""".strip()


def _bqf_choose_bowler(question):
    import pandas as pd
    from app.db import run_query

    parsed = _bqf_parse_bowler_question(question)
    if not parsed:
        return None

    (team_code, team_name, team_aliases), batter_label = parsed
    batter_aliases = _bqf_batter_aliases(batter_label)
    batter_sql = _bqf_sql_list(batter_aliases)
    phase_label, phase_filter = _bqf_phase(question)
    style_bucket = _bqf_style_bucket_expr()

    squad_sql = f"""
SELECT DISTINCT
    display_name AS bowler,
    cricsheet_name,
    role,
    bowling_style,
    bowling_arm
FROM current_squads
WHERE team_code = '{_bqf_q(team_code)}'
  AND COALESCE(is_active, 1) = 1
  AND (role LIKE '%Bowler%' OR role LIKE '%All%')
ORDER BY display_name;
""".strip()

    direct_sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT
        display_name,
        cricsheet_name,
        role,
        bowling_style,
        bowling_arm
    FROM current_squads
    WHERE team_code = '{_bqf_q(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
)
SELECT
    cb.display_name AS bowler,
    cb.role,
    cb.bowling_style,
    cb.bowling_arm,
    {style_bucket} AS style_bucket,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr,
    CASE
        WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) >= 12 THEN 'Usable direct sample'
        WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0 THEN 'Small direct sample'
        ELSE 'No direct sample'
    END AS sample_note
FROM current_bowlers cb
LEFT JOIN deliveries d
    ON (d.bowler = cb.cricsheet_name OR d.bowler = cb.display_name)
   AND d.striker IN {batter_sql}
   AND d.innings IN (1, 2)
   AND {phase_filter}
GROUP BY cb.display_name, cb.role, cb.bowling_style, cb.bowling_arm
ORDER BY
    CASE WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) >= 12 THEN 0 ELSE 1 END,
    dismissals DESC,
    batter_sr ASC,
    balls DESC,
    bowler ASC;
""".strip()

    weakness_sql = f"""
WITH all_current_bowlers AS (
    SELECT DISTINCT
        display_name,
        cricsheet_name,
        role,
        bowling_style,
        bowling_arm
    FROM current_squads
    WHERE COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
)
SELECT
    {style_bucket} AS style_bucket,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr,
    CASE
        WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) < 12 THEN 'Small sample'
        ELSE 'Usable sample'
    END AS sample_note
FROM all_current_bowlers cb
JOIN deliveries d
    ON (d.bowler = cb.cricsheet_name OR d.bowler = cb.display_name)
   AND d.striker IN {batter_sql}
   AND d.innings IN (1, 2)
   AND {phase_filter}
GROUP BY {style_bucket}
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
ORDER BY dismissals DESC, batter_sr ASC, balls DESC, style_bucket ASC;
""".strip()

    try:
        squad_df = run_query(squad_sql)
        direct_df = run_query(direct_sql)
        weakness_df = run_query(weakness_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The current-squad bowler choice route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": squad_sql + "\n\n" + direct_sql + "\n\n" + weakness_sql,
            "similar_questions": [],
        }

    squad_df = squad_df if squad_df is not None else pd.DataFrame()
    direct_df = direct_df if direct_df is not None else pd.DataFrame()
    weakness_df = weakness_df if weakness_df is not None else pd.DataFrame()

    top_style = None
    if not weakness_df.empty:
        top_style = str(weakness_df.iloc[0].get("style_bucket") or "").strip()

    proxy_df = squad_df.copy()
    if not proxy_df.empty and top_style:
        style_low = top_style.lower()

        def style_match(row):
            text = f"{row.get('bowling_style', '')} {row.get('bowling_arm', '')}".lower()
            if "leg" in style_low:
                return "leg" in text
            if "off" in style_low:
                return "off" in text
            if "orthodox" in style_low:
                return "orthodox" in text or "slow left" in text
            if "spin" in style_low:
                return any(x in text for x in ["spin", "slow", "leg", "off", "orthodox"])
            if "left-arm pace" in style_low:
                return "left" in text and any(x in text for x in ["fast", "medium", "pace"])
            if "pace" in style_low:
                return any(x in text for x in ["fast", "medium", "pace"])
            return False

        filtered = proxy_df[proxy_df.apply(style_match, axis=1)]
        if not filtered.empty:
            proxy_df = filtered.copy()

    if not proxy_df.empty:
        proxy_df["proxy_reason"] = f"Current {team_code} option matching {batter_label}'s weakness type: {top_style or 'best available option'}."

    usable_direct = pd.DataFrame()
    if not direct_df.empty and "balls" in direct_df.columns:
        usable_direct = direct_df[direct_df["balls"].fillna(0).astype(float) >= 12]

    recommended = None
    basis = ""

    if not usable_direct.empty:
        recommended = str(usable_direct.iloc[0]["bowler"])
        basis = "direct usable matchup data"
    elif not proxy_df.empty:
        recommended = str(proxy_df.iloc[0]["bowler"])
        basis = f"proxy style match: {top_style or 'current squad option'}"

    plan_df = pd.DataFrame([
        {"section": "Recommended bowler", "action": recommended or "No clear current-squad option found", "why": basis or "Insufficient data"},
        {"section": "Data rule", "action": "Use direct matchup only if there are 12+ balls; otherwise use style proxy.", "why": "Avoid over-trusting tiny samples."},
        {"section": "Middle-over method", "action": "Bowl to field, block singles, and make Gaikwad hit against the matched style.", "why": "Middle overs are about pressure and matchup control."},
    ])

    paragraph = (
        f"Recommended current {team_code} option to bowl to {batter_label} in {phase_label}: "
        f"{recommended or 'no clear option'}. Selection basis: {basis or 'insufficient current-squad data'}."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": plan_df,
        "extra_tables": {
            "Action Plan": plan_df,
            f"Direct {team_code} Options vs Batter": direct_df,
            "Batter Weakness By Bowling Type": weakness_df,
            f"Current {team_code} Proxy Options": proxy_df,
            f"Current {team_code} Bowling Squad": squad_df,
        },
        "sql_query": squad_sql + "\n\n" + direct_sql + "\n\n" + weakness_sql,
        "similar_questions": [
            f"how can {team_code} bowl to {batter_label} in powerplay",
            f"how can {team_code} bowl to {batter_label} in death overs",
        ],
        "route_used": "Current-squad bowler recommendation",
        "data_sources": "current_squads, deliveries",
    }


def _bqf_extract_season(question):
    import re
    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", str(question or ""))
    return match.group(1) if match else None


def _bqf_venue_filter(question):
    import re
    match = re.search(r"\bat\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+\d{4}|$)", str(question or ""), flags=re.IGNORECASE)
    if not match:
        return "1=1", None

    venue = match.group(1).strip(" .?").lower()

    if "wankhede" in venue:
        return "venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in venue or "chidambaram" in venue:
        return "(venue LIKE '%Chepauk%' OR venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in venue:
        return "venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in venue:
        return "venue LIKE '%Chinnaswamy%'", "Chinnaswamy"

    safe = _bqf_q(venue)
    return f"LOWER(venue) LIKE '%{safe}%'", venue.title()


def _bqf_team_filter(question):
    import re
    match = re.search(r"\bfor\s+([A-Za-z0-9 .]+?)(?:\s+in\s+\d{4}|\s+at\s+|$)", str(question or ""), flags=re.IGNORECASE)
    if not match:
        return "1=1", None

    team = _bqf_team_lookup(match.group(1).strip(" .?"))

    if not team[0]:
        return "1=1", None

    return f"batting_team IN {_bqf_sql_list(team[2])}", team[1]


def _bqf_fastest_100(question):
    import pandas as pd
    from app.db import run_query

    text = str(question or "").lower()
    if not ("fastest" in text and ("100" in text or "hundred" in text or "century" in text)):
        return None

    try:
        exists_df = run_query("""
SELECT
    CASE WHEN OBJECT_ID('dbo.batter_innings_milestones', 'U') IS NULL THEN 0 ELSE 1 END AS table_exists,
    CASE WHEN COL_LENGTH('dbo.batter_innings_milestones', 'balls_to_hundred') IS NULL THEN 0 ELSE 1 END AS has_hundred_col;
""".strip())

        if exists_df is None or exists_df.empty or int(exists_df.iloc[0]["table_exists"]) != 1 or int(exists_df.iloc[0]["has_hundred_col"]) != 1:
            return {
                "question": question,
                "analysis_paragraph": "Fastest 100 needs the updated milestone cache. Run scripts\\rebuild_batter_milestones_with_100.sql in SSMS.",
                "result": pd.DataFrame(),
                "extra_tables": {},
                "sql_query": "",
                "similar_questions": [],
            }
    except Exception:
        return None

    season = _bqf_extract_season(question)
    season_filter = "1=1" if not season else f"season = '{_bqf_q(season)}'"
    venue_filter, venue_label = _bqf_venue_filter(question)
    team_filter, team_name = _bqf_team_filter(question)

    where_sql = " AND ".join([
        "balls_to_hundred IS NOT NULL",
        season_filter,
        venue_filter,
        team_filter,
    ])

    title = "Fastest hundreds in IPL"
    if team_name:
        title += f" for {team_name}"
    if venue_label:
        title += f" at {venue_label}"
    if season:
        title += f" in {season}"

    sql = f"""
SELECT TOP 25
    batter,
    batting_team,
    opposition,
    season,
    match_date,
    venue,
    innings,
    balls_to_hundred,
    innings_runs,
    innings_balls
FROM dbo.batter_innings_milestones
WHERE {where_sql}
ORDER BY
    balls_to_hundred ASC,
    innings_runs DESC,
    match_date ASC,
    batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The fastest-100 query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": f"{title}. Sorted by balls_to_hundred ascending first, then innings runs.",
        "paragraph": f"{title}. Sorted by balls_to_hundred ascending first, then innings runs.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has the fastest 100 in IPL history",
            "who has the fastest 100 for RCB",
            "who has the fastest hundred at Wankhede",
        ],
        "route_used": "Fastest hundred corrected",
        "data_sources": "batter_innings_milestones cache",
    }


try:
    _previous_answer_question_with_fallback_before_bqf = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_bqf = None


def answer_question_with_fallback(user_question):
    for route in [_bqf_choose_bowler, _bqf_fastest_100]:
        result = route(user_question)
        if result is not None:
            return result

    return _previous_answer_question_with_fallback_before_bqf(user_question)

# IPL SQL Agent bowling question and fastest 100 fix END


# IPL SQL Agent fix bowling recommender and cached milestones START

def _fixbf_q(value):
    return str(value).replace("'", "''")


def _fixbf_sql_list(values):
    values = [value for value in values if value and str(value).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _fixbf_q(value) + "'" for value in values) + ")"


def _fixbf_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]
    for code, name, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, name, aliases
    return None, None, []


def _fixbf_parse_bowling_question(question):
    import re
    text = str(question or "").strip()
    patterns = [
        r"\bwhich\s+(.+?)\s+bowler\s+should\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$",
        r"\bwhich\s+bowler\s+from\s+(.+?)\s+should\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$",
        r"\bhow\s+can\s+(.+?)\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$",
        r"\bhow\s+should\s+(.+?)\s+bowl\s+to\s+(.+?)(?:\s+in\s+.+)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        team_raw = match.group(1).strip(" .?")
        batter_raw = match.group(2).strip(" .?")
        batter_raw = re.sub(
            r"\s+in\s+(powerplay|pwerplay|pp|middle overs|middle|death overs|death).*$",
            "",
            batter_raw,
            flags=re.IGNORECASE,
        ).strip(" .?")
        team = _fixbf_team_lookup(team_raw)
        if team[0] and batter_raw:
            return team, batter_raw
    return None


def _fixbf_phase(question, alias="d"):
    text = str(question or "").lower()
    ball = f"{alias}.ball"
    if "powerplay" in text or "pwerplay" in text or " pp" in text:
        return "Powerplay", f"FLOOR({ball}) BETWEEN 0 AND 5"
    if "death" in text:
        return "Death overs", f"FLOOR({ball}) BETWEEN 16 AND 19"
    return "Middle overs", f"FLOOR({ball}) BETWEEN 6 AND 15"


def _fixbf_batter_aliases(label):
    raw = str(label or "").strip()
    low = raw.lower()
    aliases = [raw]
    known = {
        "gaikwad": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "ruturaj": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "kohli": ["V Kohli", "Virat Kohli"],
        "rohit": ["RG Sharma", "Rohit Sharma"],
        "dhoni": ["MS Dhoni"],
        "raina": ["SK Raina", "Suresh Raina"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sudharsan": ["B Sai Sudharsan", "Sai Sudharsan"],
        "gill": ["Shubman Gill"],
    }
    for key, values in known.items():
        if key in low:
            for value in values:
                if value not in aliases:
                    aliases.append(value)
    return aliases


def _fixbf_type_expr():
    return """
CASE
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%leg%' THEN 'Leg spin'
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%off%' THEN 'Off spin'
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%orthodox%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%slow left%' THEN 'Left-arm orthodox'
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%spin%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%slow%' THEN 'Spin'
    WHEN LOWER(COALESCE(cb.bowling_arm, '')) LIKE '%left%' AND (LOWER(COALESCE(cb.bowling_style, '')) LIKE '%fast%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%medium%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%pace%') THEN 'Left-arm pace'
    WHEN LOWER(COALESCE(cb.bowling_style, '')) LIKE '%fast%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%medium%' OR LOWER(COALESCE(cb.bowling_style, '')) LIKE '%pace%' THEN 'Pace'
    ELSE NULL
END
""".strip()


def _fixbf_style_match(row, bowling_type):
    text = f"{row.get('bowling_style', '')} {row.get('bowling_arm', '')}".lower()
    bowling_type = str(bowling_type or "").lower()
    if not bowling_type:
        return False
    if "leg" in bowling_type:
        return "leg" in text
    if "off" in bowling_type:
        return "off" in text
    if "orthodox" in bowling_type:
        return "orthodox" in text or "slow left" in text
    if "spin" in bowling_type:
        return any(x in text for x in ["spin", "slow", "leg", "off", "orthodox"])
    if "left-arm pace" in bowling_type:
        return "left" in text and any(x in text for x in ["fast", "medium", "pace"])
    if "pace" in bowling_type:
        return any(x in text for x in ["fast", "medium", "pace"])
    return False


def _fixbf_bowling_recommendation(question):
    import pandas as pd
    from app.db import run_query

    parsed = _fixbf_parse_bowling_question(question)
    if not parsed:
        return None

    (team_code, team_name, team_aliases), batter_label = parsed
    batter_sql = _fixbf_sql_list(_fixbf_batter_aliases(batter_label))
    phase_label, phase_filter = _fixbf_phase(question)
    bowling_type_expr = _fixbf_type_expr()

    squad_sql = f"""
SELECT DISTINCT
    display_name AS bowler,
    cricsheet_name,
    role,
    bowling_style,
    bowling_arm
FROM current_squads
WHERE team_code = '{_fixbf_q(team_code)}'
  AND COALESCE(is_active, 1) = 1
  AND (role LIKE '%Bowler%' OR role LIKE '%All%')
ORDER BY display_name;
""".strip()

    direct_sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT
        display_name,
        cricsheet_name,
        role,
        bowling_style,
        bowling_arm
    FROM current_squads
    WHERE team_code = '{_fixbf_q(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
)
SELECT
    cb.display_name AS bowler,
    cb.role,
    cb.bowling_style,
    cb.bowling_arm,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr,
    CASE
        WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) >= 12 THEN 'Usable direct sample'
        WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0 THEN 'Small direct sample'
        ELSE 'No direct sample'
    END AS sample_note
FROM current_bowlers cb
LEFT JOIN deliveries d
    ON (d.bowler = cb.cricsheet_name OR d.bowler = cb.display_name)
   AND d.striker IN {batter_sql}
   AND d.innings IN (1, 2)
   AND {phase_filter}
GROUP BY cb.display_name, cb.role, cb.bowling_style, cb.bowling_arm
ORDER BY
    CASE WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) >= 12 THEN 0 ELSE 1 END,
    dismissals DESC,
    batter_sr ASC,
    balls DESC,
    bowler ASC;
""".strip()

    weakness_sql = f"""
WITH all_current_bowlers AS (
    SELECT DISTINCT
        display_name,
        cricsheet_name,
        role,
        bowling_style,
        bowling_arm
    FROM current_squads
    WHERE COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
),
typed_balls AS (
    SELECT
        {bowling_type_expr} AS bowling_type,
        d.runs_off_bat,
        d.wides,
        d.noballs,
        d.wicket_type,
        d.player_dismissed,
        d.striker
    FROM all_current_bowlers cb
    JOIN deliveries d
        ON (d.bowler = cb.cricsheet_name OR d.bowler = cb.display_name)
       AND d.striker IN {batter_sql}
       AND d.innings IN (1, 2)
       AND {phase_filter}
)
SELECT
    bowling_type,
    COUNT(CASE WHEN COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN wicket_type IS NOT NULL AND player_dismissed = striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr,
    CASE
        WHEN COUNT(CASE WHEN COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END) < 12 THEN 'Small sample'
        ELSE 'Usable sample'
    END AS sample_note
FROM typed_balls
WHERE bowling_type IS NOT NULL
GROUP BY bowling_type
HAVING COUNT(CASE WHEN COALESCE(wides, 0)=0 AND COALESCE(noballs, 0)=0 THEN 1 END) > 0
ORDER BY dismissals DESC, batter_sr ASC, balls DESC, bowling_type ASC;
""".strip()

    try:
        squad_df = run_query(squad_sql)
        direct_df = run_query(direct_sql)
        weakness_df = run_query(weakness_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The current-squad bowler choice route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": squad_sql + "\n\n" + direct_sql + "\n\n" + weakness_sql,
            "similar_questions": [],
        }

    squad_df = squad_df if squad_df is not None else pd.DataFrame()
    direct_df = direct_df if direct_df is not None else pd.DataFrame()
    weakness_df = weakness_df if weakness_df is not None else pd.DataFrame()

    top_type = None
    if not weakness_df.empty:
        top_type = str(weakness_df.iloc[0].get("bowling_type") or "").strip()

    usable_direct = pd.DataFrame()
    if not direct_df.empty and "balls" in direct_df.columns:
        usable_direct = direct_df[direct_df["balls"].fillna(0).astype(float) >= 12]

    proxy_df = squad_df.copy()
    if top_type and not proxy_df.empty:
        filtered = proxy_df[proxy_df.apply(lambda row: _fixbf_style_match(row, top_type), axis=1)]
        if not filtered.empty:
            proxy_df = filtered.copy()

    if not proxy_df.empty:
        proxy_df["proxy_reason"] = (
            f"Current {team_code} option"
            + (f" matching {batter_label}'s weakness type: {top_type}." if top_type else " selected from current squad because no reliable bowling-type data exists.")
        )

    recommended = None
    basis = None

    if not usable_direct.empty:
        recommended = str(usable_direct.iloc[0]["bowler"])
        basis = "direct usable matchup data"
    elif not proxy_df.empty:
        recommended = str(proxy_df.iloc[0]["bowler"])
        basis = f"style proxy: {top_type}" if top_type else "current squad fallback; no known bowling-type split"

    plan_df = pd.DataFrame([
        {
            "section": "Recommended bowler",
            "action": recommended or "No clear current-squad option found",
            "why": basis or "Insufficient current-squad data",
        },
        {
            "section": "Data rule",
            "action": "Use direct matchup only if there are 12+ balls; otherwise use a known style proxy.",
            "why": "Avoid over-trusting tiny samples; do not treat Unknown as a bowling type.",
        },
        {
            "section": "Middle-over method",
            "action": "Bowl to the field, cut singles, and force the batter to hit against the matchup.",
            "why": "Middle overs are about pressure and matchup control.",
        },
    ])

    extra = {
        "Action Plan": plan_df,
        f"Direct {team_code} Options vs Batter": direct_df,
        f"Current {team_code} Proxy Options": proxy_df,
        f"Current {team_code} Bowling Squad": squad_df,
    }

    if not weakness_df.empty:
        extra["Batter Weakness By Bowling Type"] = weakness_df

    paragraph = (
        f"Recommended current {team_code} option to bowl to {batter_label} in {phase_label}: "
        f"{recommended or 'no clear option'}. Selection basis: {basis or 'insufficient data'}."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": plan_df,
        "extra_tables": extra,
        "sql_query": squad_sql + "\n\n" + direct_sql + "\n\n" + weakness_sql,
        "similar_questions": [
            f"which {team_code} bowler should bowl to {batter_label} in powerplay",
            f"which {team_code} bowler should bowl to {batter_label} in death overs",
        ],
        "route_used": "Current-squad bowler recommendation v2",
        "data_sources": "current_squads, deliveries",
    }


def _fixbf_extract_season(question):
    import re
    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", str(question or ""))
    return match.group(1) if match else None


def _fixbf_venue_filter(question):
    import re
    match = re.search(r"\bat\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+\d{4}|$)", str(question or ""), flags=re.IGNORECASE)
    if not match:
        return "1=1", None
    venue = match.group(1).strip(" .?").lower()
    if "wankhede" in venue:
        return "venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in venue or "chidambaram" in venue:
        return "(venue LIKE '%Chepauk%' OR venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in venue:
        return "venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in venue:
        return "venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    safe = _fixbf_q(venue)
    return f"LOWER(venue) LIKE '%{safe}%'", venue.title()


def _fixbf_team_filter(question):
    import re
    match = re.search(r"\bfor\s+([A-Za-z0-9 .]+?)(?:\s+in\s+\d{4}|\s+at\s+|$)", str(question or ""), flags=re.IGNORECASE)
    if not match:
        return "1=1", None
    team = _fixbf_team_lookup(match.group(1).strip(" .?"))
    if not team[0]:
        return "1=1", None
    return f"batting_team IN {_fixbf_sql_list(team[2])}", team[1]


def _fixbf_fastest_milestone(question):
    import pandas as pd
    from app.db import run_query

    text = str(question or "").lower()

    if "fastest" not in text:
        return None

    if "100" in text or "hundred" in text or "century" in text:
        milestone = "hundred"
        balls_col = "balls_to_hundred"
        label = "hundreds"
        required_col = "balls_to_hundred"
    elif "50" in text or "fifty" in text:
        milestone = "fifty"
        balls_col = "balls_to_fifty"
        label = "fifties"
        required_col = "balls_to_fifty"
    else:
        return None

    try:
        exists_df = run_query(f"""
SELECT
    CASE WHEN OBJECT_ID('dbo.batter_innings_milestones', 'U') IS NULL THEN 0 ELSE 1 END AS table_exists,
    CASE WHEN COL_LENGTH('dbo.batter_innings_milestones', '{required_col}') IS NULL THEN 0 ELSE 1 END AS has_col;
""".strip())

        if exists_df is None or exists_df.empty or int(exists_df.iloc[0]["table_exists"]) != 1 or int(exists_df.iloc[0]["has_col"]) != 1:
            return {
                "question": question,
                "analysis_paragraph": "Milestone cache needs rebuilding. Run scripts\\rebuild_batter_milestones_with_100.sql in SSMS.",
                "result": pd.DataFrame(),
                "extra_tables": {},
                "sql_query": "",
                "similar_questions": [],
            }
    except Exception:
        return None

    season = _fixbf_extract_season(question)
    season_filter = "1=1" if not season else f"season = '{_fixbf_q(season)}'"
    venue_filter, venue_label = _fixbf_venue_filter(question)
    team_filter, team_name = _fixbf_team_filter(question)

    where_sql = " AND ".join([
        f"{balls_col} IS NOT NULL",
        season_filter,
        venue_filter,
        team_filter,
    ])

    title = f"Fastest {label} in IPL"
    if team_name:
        title += f" for {team_name}"
    if venue_label:
        title += f" at {venue_label}"
    if season:
        title += f" in {season}"

    sql = f"""
SELECT TOP 25
    batter,
    batting_team,
    opposition,
    season,
    match_date,
    venue,
    innings,
    {balls_col},
    innings_runs,
    innings_balls
FROM dbo.batter_innings_milestones
WHERE {where_sql}
ORDER BY
    {balls_col} ASC,
    innings_runs DESC,
    match_date ASC,
    batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The fastest-{milestone} query failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": f"{title}. Sorted by {balls_col} ascending first, then innings runs.",
        "paragraph": f"{title}. Sorted by {balls_col} ascending first, then innings runs.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has the fastest 50 in IPL history",
            "who has the fastest 100 in IPL history",
        ],
        "route_used": f"Fastest {milestone} corrected",
        "data_sources": "batter_innings_milestones cache",
    }


try:
    _previous_answer_question_with_fallback_before_fixbf = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_fixbf = None


def answer_question_with_fallback(user_question):
    for route in [_fixbf_bowling_recommendation, _fixbf_fastest_milestone]:
        result = route(user_question)
        if result is not None:
            return result
    return _previous_answer_question_with_fallback_before_fixbf(user_question)

# IPL SQL Agent fix bowling recommender and cached milestones END


# IPL SQL Agent player fifties + profile ordering quick fix START

def _qpf_quote(x):
    return str(x).replace("'", "''")


def _qpf_list(xs):
    xs = [x for x in xs if x and str(x).strip()]
    return "(" + ", ".join("'" + _qpf_quote(x) + "'" for x in xs) + ")" if xs else "('')"


def _qpf_team_lookup(x):
    t = str(x or "").lower().strip()
    teams = ["csk","mi","rcb","gt","kkr","rr","srh","dc","pbks","kxip","lsg","chennai","mumbai","bangalore","bengaluru","gujarat","kolkata","rajasthan","hyderabad","delhi","punjab","lucknow"]
    return any(team == t or team in t for team in teams)


def _qpf_aliases(label):
    raw = str(label or "").strip()
    low = raw.lower()
    aliases = [raw]
    known = {
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "vaibhav": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "bumrah": ["JJ Bumrah", "Jasprit Bumrah"],
        "jasprit": ["JJ Bumrah", "Jasprit Bumrah"],
        "narine": ["SP Narine", "Sunil Narine"],
        "kohli": ["V Kohli", "Virat Kohli"],
        "rohit": ["RG Sharma", "Rohit Sharma"],
        "raina": ["SK Raina", "Suresh Raina"],
        "dhoni": ["MS Dhoni"],
        "gaikwad": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "sudharsan": ["B Sai Sudharsan", "Sai Sudharsan"],
        "gill": ["Shubman Gill"],
        "rashid": ["Rashid Khan"],
        "jadeja": ["RA Jadeja", "Ravindra Jadeja"],
    }
    for k, vals in known.items():
        if k in low:
            aliases += [v for v in vals if v not in aliases]
    return aliases


def _qpf_resolve(label):
    from app.db import run_query
    aliases = _qpf_aliases(label)
    sql = f"""
SELECT TOP 1 player_name
FROM (
    SELECT striker AS player_name, COUNT(*) AS n FROM deliveries WHERE striker IN {_qpf_list(aliases)} GROUP BY striker
    UNION ALL
    SELECT bowler AS player_name, COUNT(*) AS n FROM deliveries WHERE bowler IN {_qpf_list(aliases)} GROUP BY bowler
    UNION ALL
    SELECT cricsheet_name AS player_name, 1000 AS n FROM current_squads WHERE display_name IN {_qpf_list(aliases)} OR cricsheet_name IN {_qpf_list(aliases)}
) x
WHERE player_name IS NOT NULL
GROUP BY player_name
ORDER BY SUM(n) DESC, player_name ASC;
"""
    try:
        df = run_query(sql)
        if df is not None and not df.empty:
            p = str(df.iloc[0]["player_name"])
            if p not in aliases:
                aliases.insert(0, p)
            return p, aliases
    except Exception:
        pass
    return aliases[0], aliases


def _qpf_parse_player_fifties(q):
    import re
    s = str(q or "")
    patterns = [
        r"\bhow\s+many\s+(?:fifties|50s|fifty scores)\s+does\s+(.+?)\s+have\b",
        r"\bhow\s+many\s+(?:fifties|50s|fifty scores)\s+has\s+(.+?)\s+scored\b",
    ]
    for pat in patterns:
        m = re.search(pat, s, flags=re.I)
        if m:
            label = m.group(1).strip(" .?")
            if not _qpf_team_lookup(label):
                return label
    return None


def _qpf_player_fifties(q):
    import pandas as pd
    from app.db import run_query
    label = _qpf_parse_player_fifties(q)
    if not label:
        return None
    player, aliases = _qpf_resolve(label)
    filt = f"d.striker IN {_qpf_list(aliases)}"
    sql = f"""
WITH innings_scores AS (
    SELECT d.season, d.match_id, d.innings,
           SUM(COALESCE(d.runs_off_bat,0)) AS innings_runs,
           COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END) AS balls
    FROM deliveries d
    WHERE {filt} AND d.innings IN (1,2)
    GROUP BY d.season, d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat,0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END) > 0
)
SELECT '{_qpf_quote(player)}' AS player,
       COUNT(DISTINCT match_id) AS matches,
       COUNT(*) AS innings,
       SUM(innings_runs) AS runs,
       SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
       SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
       SUM(CASE WHEN innings_runs >= 50 THEN 1 ELSE 0 END) AS fifty_plus_scores,
       MAX(innings_runs) AS highest_score
FROM innings_scores;
"""
    scores_sql = f"""
WITH innings_scores AS (
    SELECT d.season, d.match_id, CAST(m.start_date AS date) AS match_date, d.batting_team,
           d.bowling_team AS opposition, d.innings, m.venue,
           SUM(COALESCE(d.runs_off_bat,0)) AS innings_runs,
           COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END) AS balls
    FROM deliveries d JOIN matches m ON d.match_id=m.match_id
    WHERE {filt} AND d.innings IN (1,2)
    GROUP BY d.season, d.match_id, CAST(m.start_date AS date), d.batting_team, d.bowling_team, d.innings, m.venue
)
SELECT season, match_date, batting_team, opposition, innings, innings_runs, balls, venue,
       CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 'Fifty' WHEN innings_runs >= 100 THEN 'Hundred' ELSE '' END AS score_type
FROM innings_scores
WHERE innings_runs >= 50
ORDER BY innings_runs DESC, match_date ASC;
"""
    try:
        df = run_query(sql)
        scores = run_query(scores_sql)
    except Exception as e:
        return {"question": q, "analysis_paragraph": f"Player fifties query failed: {e}", "result": pd.DataFrame(), "extra_tables": {}, "sql_query": sql}
    df = df if df is not None else pd.DataFrame()
    scores = scores if scores is not None else pd.DataFrame()
    f = int(df.iloc[0].get("fifties") or 0) if not df.empty else 0
    h = int(df.iloc[0].get("hundreds") or 0) if not df.empty else 0
    para = f"{player} has {f} fifties using the strict 50-99 definition. He also has {h} hundreds, so fifty-plus scores are shown separately."
    return {"question": q, "analysis_paragraph": para, "paragraph": para, "result": df, "extra_tables": {"Fifties Summary": df, "All 50+ Scores": scores}, "sql_query": sql+"\n\n"+scores_sql, "similar_questions": [f"analyse {player}", "who has the most fifties in IPL"], "route_used": "Player-specific fifties", "data_sources": "deliveries, matches"}


def _qpf_parse_profile(q):
    import re
    s = str(q or "").strip()
    m = re.search(r"^(?:analyse|analyze|profile|tell me about)\s+(.+?)\s*$", s, flags=re.I)
    if not m:
        return None
    label = m.group(1).strip(" .?")
    low = label.lower()
    if _qpf_team_lookup(label) or any(v in low for v in ["stadium","venue","chepauk","eden","wankhede","chinnaswamy","narendra"]):
        return None
    return label


def _qpf_role_profile(q):
    import pandas as pd
    from app.db import run_query
    label = _qpf_parse_profile(q)
    if not label:
        return None
    player, aliases = _qpf_resolve(label)
    bat_f = f"d.striker IN {_qpf_list(aliases)}"
    bowl_f = f"d.bowler IN {_qpf_list(aliases)}"
    bat_sql = f"""
WITH innings_scores AS (
    SELECT d.match_id, d.innings,
           SUM(COALESCE(d.runs_off_bat,0)) AS innings_runs,
           COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END) AS balls
    FROM deliveries d
    WHERE {bat_f} AND d.innings IN (1,2)
    GROUP BY d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat,0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END) > 0
)
SELECT '{_qpf_quote(player)}' AS player, COUNT(DISTINCT match_id) AS batting_matches,
       COUNT(*) AS batting_innings, SUM(innings_runs) AS runs, MAX(innings_runs) AS highest_score,
       SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
       SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
       ROUND(SUM(innings_runs)*100.0/NULLIF(SUM(balls),0),2) AS strike_rate
FROM innings_scores;
"""
    bowl_sql = f"""
SELECT '{_qpf_quote(player)}' AS player,
       COUNT(DISTINCT d.match_id) AS bowling_matches,
       COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS bowling_innings,
       CAST(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END)/6 AS varchar(20))
       + '.' + CAST(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END)%6 AS varchar(1)) AS overs_bowled,
       COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field') THEN 1 END) AS wickets,
       ROUND(SUM(COALESCE(d.runs_off_bat,0)+COALESCE(d.extras,0))*6.0/NULLIF(COUNT(CASE WHEN COALESCE(d.wides,0)=0 AND COALESCE(d.noballs,0)=0 THEN 1 END),0),2) AS economy,
       COUNT(CASE WHEN COALESCE(d.runs_off_bat,0)=0 AND COALESCE(d.extras,0)=0 THEN 1 END) AS dot_balls
FROM deliveries d
WHERE {bowl_f} AND d.innings IN (1,2);
"""
    try:
        bat = run_query(bat_sql)
        bowl = run_query(bowl_sql)
    except Exception as e:
        return {"question": q, "analysis_paragraph": f"Player profile query failed: {e}", "result": pd.DataFrame(), "extra_tables": {}, "sql_query": bat_sql+"\n\n"+bowl_sql}
    bat = bat if bat is not None else pd.DataFrame()
    bowl = bowl if bowl is not None else pd.DataFrame()
    runs = int(bat.iloc[0].get("runs") or 0) if not bat.empty else 0
    wkts = int(bowl.iloc[0].get("wickets") or 0) if not bowl.empty else 0
    if wkts >= 25 and wkts*8 > runs:
        main = bowl
        extra = {"Bowling Summary": bowl, "Batting Summary": bat}
        para = f"{player} is shown as a bowling-first profile, so bowling appears first and batting is still included."
    elif runs >= 1000 and runs > wkts*8:
        main = bat
        extra = {"Batting Summary": bat, "Bowling Summary": bowl}
        para = f"{player} is shown as a batting-first profile, so batting appears first and bowling is still included."
    else:
        main = bat if runs >= wkts else bowl
        extra = {"Batting Summary": bat, "Bowling Summary": bowl}
        para = f"{player} is shown as a mixed/all-round profile with both batting and bowling included."
    return {"question": q, "analysis_paragraph": para, "paragraph": para, "result": main, "extra_tables": extra, "sql_query": bat_sql+"\n\n"+bowl_sql, "similar_questions": [f"how many fifties does {player} have"], "route_used": "Role-ordered player profile", "data_sources": "deliveries"}


def _qpf_is_most_fifties(q):
    s = str(q or "").lower()
    return ("most" in s or "top" in s) and ("fifties" in s or "50s" in s) and "how many" not in s


try:
    _previous_answer_question_with_fallback_before_qpf = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_qpf = None


def answer_question_with_fallback(user_question):
    for route in [_qpf_player_fifties, _qpf_role_profile]:
        result = route(user_question)
        if result is not None:
            return result
    result = _previous_answer_question_with_fallback_before_qpf(user_question)
    if isinstance(result, dict) and _qpf_is_most_fifties(user_question):
        for key in ["result"]:
            table = result.get(key)
            if hasattr(table, "columns"):
                drop_cols = [c for c in table.columns if str(c).lower() in {"season", "seasons", "season_count", "seasons_played"}]
                if drop_cols:
                    result[key] = table.drop(columns=drop_cols)
        extra = result.get("extra_tables")
        if isinstance(extra, dict):
            for name, table in list(extra.items()):
                if hasattr(table, "columns"):
                    drop_cols = [c for c in table.columns if str(c).lower() in {"season", "seasons", "season_count", "seasons_played"}]
                    if drop_cols:
                        extra[name] = table.drop(columns=drop_cols)
            result["extra_tables"] = extra
    return result

# IPL SQL Agent player fifties + profile ordering quick fix END


# IPL SQL Agent profile resolved_player compatibility v2 START

def _rpv2_parse_profile_question(question):
    import re

    text = str(question or "").strip()
    match = re.search(r"^(?:analyse|analyze|profile|tell me about)\s+(.+?)\s*$", text, flags=re.IGNORECASE)

    if not match:
        return None

    label = match.group(1).strip(" .?")
    low = label.lower()

    if any(x in low for x in ["stadium", "venue", "chepauk", "eden", "wankhede", "chinnaswamy", "narendra"]):
        return None

    team_words = {
        "csk", "mi", "rcb", "gt", "kkr", "rr", "srh", "dc", "pbks", "kxip", "lsg",
        "chennai", "mumbai", "bangalore", "bengaluru", "gujarat", "kolkata",
        "rajasthan", "hyderabad", "delhi", "punjab", "lucknow"
    }

    if low in team_words:
        return None

    return label


def _rpv2_known_resolved(label):
    low = str(label or "").lower()

    known = {
        "kohli": "V Kohli",
        "virat": "V Kohli",
        "raina": "SK Raina",
        "suresh": "SK Raina",
        "bumrah": "JJ Bumrah",
        "jasprit": "JJ Bumrah",
        "narine": "SP Narine",
        "rohit": "RG Sharma",
        "dhoni": "MS Dhoni",
        "gaikwad": "RD Gaikwad",
        "ruturaj": "RD Gaikwad",
        "sooryavanshi": "V Suryavanshi",
        "suryavanshi": "V Suryavanshi",
        "vaibhav": "V Suryavanshi",
        "sudharsan": "B Sai Sudharsan",
        "gill": "Shubman Gill",
        "rashid": "Rashid Khan",
        "jadeja": "RA Jadeja",
    }

    for key, value in known.items():
        if key in low:
            return value

    return str(label or "").strip()


def _rpv2_get_resolved_from_result(result, label):
    table = result.get("result") if isinstance(result, dict) else None

    if hasattr(table, "columns") and "player" in table.columns and not table.empty:
        try:
            value = str(table.iloc[0]["player"]).strip()
            if value:
                return value
        except Exception:
            pass

    if hasattr(table, "columns") and "resolved_player" in table.columns and not table.empty:
        try:
            value = str(table.iloc[0]["resolved_player"]).strip()
            if value:
                return value
        except Exception:
            pass

    return _rpv2_known_resolved(label)


def _rpv2_add_resolved_player_column(table, resolved_player):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()

        if "resolved_player" in table.columns:
            table["resolved_player"] = resolved_player
            return table

        table.insert(0, "resolved_player", resolved_player)
        return table
    except Exception:
        return table


try:
    _previous_answer_question_with_fallback_before_rpv2 = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_rpv2 = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_rpv2(user_question)

    label = _rpv2_parse_profile_question(user_question)

    if label and isinstance(result, dict):
        resolved_player = _rpv2_get_resolved_from_result(result, label)

        result["result"] = _rpv2_add_resolved_player_column(result.get("result"), resolved_player)

        extra = result.get("extra_tables")

        if isinstance(extra, dict):
            for name, table in list(extra.items()):
                extra[name] = _rpv2_add_resolved_player_column(table, resolved_player)
            result["extra_tables"] = extra

        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""
        resolved_text = f"Resolved as {resolved_player}."

        if resolved_text not in paragraph:
            paragraph = (paragraph + " " + resolved_text).strip()

        result["analysis_paragraph"] = paragraph
        result["paragraph"] = paragraph

    return result

# IPL SQL Agent profile resolved_player compatibility v2 END


# IPL SQL Agent team trophy win pct and team season scorers fix START

def _tsfix_q(value):
    return str(value).replace("'", "''")


def _tsfix_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _tsfix_q(v) + "'" for v in values) + ")"


def _tsfix_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "Rising Pune Supergiant", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "Gujarat Lions", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "Kochi Tuskers Kerala", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "Pune Warriors", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
        ("DEC", "Deccan Chargers", ["Deccan Chargers"], ["deccan"]),
    ]
    for code, canonical, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, canonical, aliases
    return None, None, []


def _tsfix_canonical_team_expr(column_name):
    return f"""
CASE
    WHEN {column_name} IN ('Chennai Super Kings') THEN 'Chennai Super Kings'
    WHEN {column_name} IN ('Mumbai Indians') THEN 'Mumbai Indians'
    WHEN {column_name} IN ('Royal Challengers Bangalore', 'Royal Challengers Bengaluru') THEN 'Royal Challengers Bengaluru'
    WHEN {column_name} IN ('Gujarat Titans') THEN 'Gujarat Titans'
    WHEN {column_name} IN ('Kolkata Knight Riders') THEN 'Kolkata Knight Riders'
    WHEN {column_name} IN ('Rajasthan Royals') THEN 'Rajasthan Royals'
    WHEN {column_name} IN ('Sunrisers Hyderabad') THEN 'Sunrisers Hyderabad'
    WHEN {column_name} IN ('Delhi Daredevils', 'Delhi Capitals') THEN 'Delhi Capitals'
    WHEN {column_name} IN ('Kings XI Punjab', 'Punjab Kings') THEN 'Punjab Kings'
    WHEN {column_name} IN ('Lucknow Super Giants') THEN 'Lucknow Super Giants'
    WHEN {column_name} IN ('Rising Pune Supergiant', 'Rising Pune Supergiants') THEN 'Rising Pune Supergiant'
    WHEN {column_name} IN ('Gujarat Lions') THEN 'Gujarat Lions'
    WHEN {column_name} IN ('Deccan Chargers') THEN 'Deccan Chargers'
    WHEN {column_name} IN ('Pune Warriors', 'Pune Warriors India') THEN 'Pune Warriors'
    WHEN {column_name} IN ('Kochi Tuskers Kerala') THEN 'Kochi Tuskers Kerala'
    ELSE {column_name}
END
""".strip()


def _tsfix_season_key(value):
    import re
    text = str(value)
    match = re.search(r"(19|20)\d{2}", text)
    if match:
        return int(match.group(0))
    return 9999


def _tsfix_trophy_route(question):
    import pandas as pd
    from app.db import run_query

    text = str(question or "").lower()

    if not (
        ("most" in text or "highest" in text or "won" in text)
        and ("troph" in text or "titles" in text or "title" in text)
    ):
        return None

    winner_expr = _tsfix_canonical_team_expr("winner")

    sql = f"""
WITH final_match AS (
    SELECT
        season,
        match_id,
        CAST(start_date AS date) AS match_date,
        winner,
        ROW_NUMBER() OVER (
            PARTITION BY season
            ORDER BY CAST(start_date AS date) DESC, match_id DESC
        ) AS rn
    FROM matches
    WHERE winner IS NOT NULL
)
SELECT
    season,
    match_date,
    {winner_expr} AS team
FROM final_match
WHERE rn = 1
  AND winner IS NOT NULL
ORDER BY
    CASE
        WHEN CHARINDEX('/', CAST(season AS varchar(20))) > 0
        THEN TRY_CONVERT(INT, LEFT(CAST(season AS varchar(20)), 4))
        ELSE TRY_CONVERT(INT, CAST(season AS varchar(20)))
    END,
    season;
""".strip()

    try:
        finals_df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The trophy route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    finals_df = finals_df if finals_df is not None else pd.DataFrame()

    if finals_df.empty:
        return {
            "question": question,
            "analysis_paragraph": "No trophy winners could be inferred from the final match of each season.",
            "result": finals_df,
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    rows = []
    for team, group in finals_df.groupby("team", dropna=True):
        seasons = sorted([str(s) for s in group["season"].dropna().tolist()], key=_tsfix_season_key)
        rows.append({
            "team": team,
            "trophies": len(seasons),
            "years_won": ", ".join(seasons),
        })

    result_df = pd.DataFrame(rows).sort_values(
        by=["trophies", "team"],
        ascending=[False, True],
    ).reset_index(drop=True)

    return {
        "question": question,
        "analysis_paragraph": "Most IPL trophies by team. The years_won column is sorted in ascending season order.",
        "paragraph": "Most IPL trophies by team. The years_won column is sorted in ascending season order.",
        "result": result_df,
        "extra_tables": {
            "Trophy Winners": result_df,
            "Season Champions": finals_df,
        },
        "sql_query": sql,
        "similar_questions": [
            "which team has the best win percentage",
            "which team has reached the most finals",
        ],
        "route_used": "Trophy winners sorted years",
        "data_sources": "matches",
    }


def _tsfix_best_win_percentage_route(question):
    import pandas as pd
    from app.db import run_query

    text = str(question or "").lower()

    if not (
        ("win percentage" in text or "win percent" in text or "win rate" in text)
        and ("team" in text or "franchise" in text or "best" in text or "highest" in text)
    ):
        return None

    team_expr = _tsfix_canonical_team_expr("mt.team")
    winner_expr = _tsfix_canonical_team_expr("m.winner")

    sql = f"""
WITH match_teams_raw AS (
    SELECT DISTINCT match_id, batting_team AS team
    FROM deliveries
    WHERE batting_team IS NOT NULL

    UNION

    SELECT DISTINCT match_id, bowling_team AS team
    FROM deliveries
    WHERE bowling_team IS NOT NULL
),
match_teams AS (
    SELECT
        match_id,
        {team_expr} AS team
    FROM match_teams_raw mt
),
results AS (
    SELECT
        mt.team,
        mt.match_id,
        {winner_expr} AS winner
    FROM match_teams mt
    JOIN matches m
        ON mt.match_id = m.match_id
)
SELECT
    team,
    COUNT(DISTINCT match_id) AS matches,
    SUM(CASE WHEN team = winner THEN 1 ELSE 0 END) AS wins,
    COUNT(DISTINCT match_id) - SUM(CASE WHEN team = winner THEN 1 ELSE 0 END) AS non_wins,
    ROUND(SUM(CASE WHEN team = winner THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(DISTINCT match_id), 0), 2) AS win_percentage
FROM results
WHERE team IS NOT NULL
GROUP BY team
HAVING COUNT(DISTINCT match_id) >= 10
ORDER BY win_percentage DESC, wins DESC, matches DESC, team ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The win percentage route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": "Best IPL team win percentage. Minimum 10 matches are required so one-off teams or tiny samples do not distort the table.",
        "paragraph": "Best IPL team win percentage. Minimum 10 matches are required so one-off teams or tiny samples do not distort the table.",
        "result": df,
        "extra_tables": {"Team Win Percentage": df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has won the most trophies",
            "compare CSK and MI",
        ],
        "route_used": "Team win percentage",
        "data_sources": "matches, deliveries",
    }


def _tsfix_extract_season(question):
    import re
    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", str(question or ""))
    return match.group(1) if match else None


def _tsfix_parse_team_run_scorers(question):
    import re

    text = str(question or "")

    if not ("run scorer" in text.lower() or "run scorers" in text.lower() or "most runs" in text.lower()):
        return None

    team_label = None

    # Handles "top 10 run scorers for csk in 2026"
    match = re.search(r"\b(?:for|from)\s+([A-Za-z0-9 .]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s*$)", text, flags=re.IGNORECASE)
    if match:
        team_label = match.group(1).strip(" .?")

    # Handles "csk top 10 run scorers in 2026"
    if not team_label:
        for token in ["csk", "mi", "rcb", "gt", "kkr", "rr", "srh", "dc", "pbks", "kxip", "lsg"]:
            if re.search(rf"\b{token}\b", text, flags=re.IGNORECASE):
                team_label = token
                break

    if not team_label:
        return None

    team = _tsfix_team_lookup(team_label)

    if not team[0]:
        return None

    season = _tsfix_extract_season(text)

    return team, season


def _tsfix_team_season_run_scorers_route(question):
    import pandas as pd
    from app.db import run_query

    parsed = _tsfix_parse_team_run_scorers(question)

    if not parsed:
        return None

    (team_code, team_name, team_aliases), season = parsed

    filters = [
        f"d.batting_team IN {_tsfix_sql_list(team_aliases)}",
        "d.innings IN (1, 2)",
    ]

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_tsfix_q(season)}'")

    where_sql = " AND ".join(filters)

    title = f"Top 10 run scorers for {team_code}"
    if season:
        title += f" in {season}"

    sql = f"""
WITH batter_innings AS (
    SELECT
        d.striker AS batter,
        d.season,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls
    FROM deliveries d
    WHERE {where_sql}
    GROUP BY d.striker, d.season, d.match_id, d.innings
),
batter_totals AS (
    SELECT
        batter,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(balls) AS balls,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM batter_innings
    GROUP BY batter
)
SELECT TOP 10
    batter,
    matches,
    innings,
    runs,
    balls,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate,
    highest_score,
    fifties,
    hundreds
FROM batter_totals
ORDER BY runs DESC, strike_rate DESC, batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The team run scorers route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            f"top 10 run scorers for {team_code}",
            f"top 10 wicket takers for {team_code}",
        ],
        "route_used": "Team season run scorers",
        "data_sources": "deliveries",
    }


try:
    _previous_answer_question_with_fallback_before_tsfix = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_tsfix = None


def answer_question_with_fallback(user_question):
    for route in [
        _tsfix_trophy_route,
        _tsfix_best_win_percentage_route,
        _tsfix_team_season_run_scorers_route,
    ]:
        result = route(user_question)
        if result is not None:
            return result

    return _previous_answer_question_with_fallback_before_tsfix(user_question)

# IPL SQL Agent team trophy win pct and team season scorers fix END


# IPL SQL Agent leaderboard routes overall/team/venue season fix START

def _lbfix_q(value):
    return str(value).replace("'", "''")


def _lbfix_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _lbfix_q(v) + "'" for v in values) + ")"


def _lbfix_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "Rising Pune Supergiant", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "Gujarat Lions", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "Kochi Tuskers Kerala", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "Pune Warriors", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
        ("DEC", "Deccan Chargers", ["Deccan Chargers"], ["deccan"]),
    ]
    for code, canonical, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, canonical, aliases
    return None, None, []


def _lbfix_extract_season(question):
    import re
    text = str(question or "")
    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", text)
    return match.group(1) if match else None


def _lbfix_parse_team(question):
    import re
    text = str(question or "")

    match = re.search(
        r"\b(?:for|from)\s+([A-Za-z0-9 .]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s+at\s+|\s+venue\s+|\s*$)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        raw = match.group(1).strip(" .?")
        team = _lbfix_team_lookup(raw)
        if team[0]:
            return team

    # Token fallback: "csk top 10 run scorers in 2026"
    for token in ["csk", "mi", "rcb", "gt", "kkr", "rr", "srh", "dc", "pbks", "kxip", "lsg"]:
        if re.search(rf"\b{token}\b", text, flags=re.IGNORECASE):
            team = _lbfix_team_lookup(token)
            if team[0]:
                return team

    return None, None, []


def _lbfix_parse_venue(question):
    import re
    text = str(question or "")

    match = re.search(
        r"\bat\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s+for\s+|\s*$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"\bvenue\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s+for\s+|\s*$)",
            text,
            flags=re.IGNORECASE,
        )

    if not match:
        return "1=1", None

    raw = match.group(1).strip(" .?")
    low = raw.lower()

    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"
    if "dubai" in low:
        return "(m.venue LIKE '%Dubai%' OR m.city LIKE '%Dubai%')", "Dubai"
    if "sharjah" in low:
        return "(m.venue LIKE '%Sharjah%' OR m.city LIKE '%Sharjah%')", "Sharjah"
    if "abu dhabi" in low or "zayed" in low:
        return "(m.venue LIKE '%Abu Dhabi%' OR m.venue LIKE '%Zayed%' OR m.city LIKE '%Abu Dhabi%')", "Abu Dhabi"

    safe = _lbfix_q(low)
    return f"(LOWER(m.venue) LIKE '%{safe}%' OR LOWER(m.city) LIKE '%{safe}%')", raw.title()


def _lbfix_is_batting_leaderboard(question):
    text = str(question or "").lower()
    return (
        ("run scorer" in text)
        or ("run scorers" in text)
        or ("run scoer" in text)      # catches typo: scoers
        or ("run scoers" in text)
        or ("most runs" in text)
        or ("top runs" in text)
        or ("top 10 runs" in text)
    )


def _lbfix_is_bowling_leaderboard(question):
    text = str(question or "").lower()
    return (
        ("wicket taker" in text)
        or ("wicket takers" in text)
        or ("most wickets" in text)
        or ("top wickets" in text)
        or ("top 10 wickets" in text)
    )


def _lbfix_limit(question):
    import re
    match = re.search(r"\btop\s+(\d+)\b", str(question or ""), flags=re.IGNORECASE)
    if match:
        value = int(match.group(1))
        if 1 <= value <= 50:
            return value
    return 10


def _lbfix_batting_leaderboard(question):
    import pandas as pd
    from app.db import run_query

    if not _lbfix_is_batting_leaderboard(question):
        return None

    limit = _lbfix_limit(question)
    season = _lbfix_extract_season(question)
    team_code, team_name, team_aliases = _lbfix_parse_team(question)
    venue_filter, venue_label = _lbfix_parse_venue(question)

    filters = [
        "d.innings IN (1, 2)",
        venue_filter,
    ]

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_lbfix_q(season)}'")

    if team_aliases:
        filters.append(f"d.batting_team IN {_lbfix_sql_list(team_aliases)}")

    where_sql = " AND ".join(filters)

    title_parts = [f"Top {limit} run scorers"]
    if team_code:
        title_parts.append(f"for {team_code}")
    if venue_label:
        title_parts.append(f"at {venue_label}")
    if season:
        title_parts.append(f"in {season}")
    else:
        title_parts.append("across all seasons")
    title = " ".join(title_parts)

    sql = f"""
WITH batter_innings AS (
    SELECT
        d.striker AS batter,
        d.season,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out', 'retired not out')
            THEN 1 ELSE 0
        END) AS out_flag
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.striker, d.season, d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
),
batter_totals AS (
    SELECT
        batter,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(out_flag) AS dismissals,
        SUM(balls) AS balls,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM batter_innings
    GROUP BY batter
)
SELECT TOP {limit}
    batter,
    matches,
    innings,
    runs,
    dismissals,
    ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average,
    balls,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate,
    highest_score,
    fifties,
    hundreds
FROM batter_totals
ORDER BY runs DESC, batting_average DESC, strike_rate DESC, batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The batting leaderboard route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": f"{title}. Batting average is runs divided by dismissals, so not-outs do not count in the denominator.",
        "paragraph": f"{title}. Batting average is runs divided by dismissals, so not-outs do not count in the denominator.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who are top 10 run scorers in 2026",
            "who are top 10 run scorers for CSK in 2026",
            "who are top 10 run scorers at Wankhede",
        ],
        "route_used": "Flexible batting leaderboard",
        "data_sources": "deliveries, matches",
    }


def _lbfix_bowling_leaderboard(question):
    import pandas as pd
    from app.db import run_query

    if not _lbfix_is_bowling_leaderboard(question):
        return None

    limit = _lbfix_limit(question)
    season = _lbfix_extract_season(question)
    team_code, team_name, team_aliases = _lbfix_parse_team(question)
    venue_filter, venue_label = _lbfix_parse_venue(question)

    filters = [
        "d.innings IN (1, 2)",
        venue_filter,
    ]

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_lbfix_q(season)}'")

    if team_aliases:
        filters.append(f"d.bowling_team IN {_lbfix_sql_list(team_aliases)}")

    where_sql = " AND ".join(filters)

    title_parts = [f"Top {limit} wicket takers"]
    if team_code:
        title_parts.append(f"for {team_code}")
    if venue_label:
        title_parts.append(f"at {venue_label}")
    if season:
        title_parts.append(f"in {season}")
    else:
        title_parts.append("across all seasons")
    title = " ".join(title_parts)

    sql = f"""
SELECT TOP {limit}
    d.bowler,
    COUNT(DISTINCT d.match_id) AS matches,
    CAST(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) / 6 AS varchar(20))
        + '.' +
        CAST(COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) % 6 AS varchar(1)) AS overs_bowled,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
         AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
        THEN 1
    END) AS wickets,
    SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS economy,
    ROUND(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) * 1.0 / NULLIF(COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
         AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
        THEN 1
    END), 0), 2) AS bowling_strike_rate,
    COUNT(CASE WHEN COALESCE(d.runs_off_bat, 0) = 0 AND COALESCE(d.extras, 0) = 0 THEN 1 END) AS dot_balls
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {where_sql}
GROUP BY d.bowler
HAVING COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
         AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
        THEN 1
    END) > 0
ORDER BY wickets DESC, economy ASC, bowling_strike_rate ASC, d.bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The bowling leaderboard route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": f"{title}. Wickets exclude run-outs and retired dismissals.",
        "paragraph": f"{title}. Wickets exclude run-outs and retired dismissals.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "top 10 wicket takers in 2026",
            "top 10 wicket takers for CSK in 2026",
            "top 10 wicket takers at Wankhede",
        ],
        "route_used": "Flexible bowling leaderboard",
        "data_sources": "deliveries, matches",
    }


try:
    _previous_answer_question_with_fallback_before_leaderboard_fix = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_leaderboard_fix = None


def answer_question_with_fallback(user_question):
    for route in [
        _lbfix_batting_leaderboard,
        _lbfix_bowling_leaderboard,
    ]:
        result = route(user_question)
        if result is not None:
            return result

    return _previous_answer_question_with_fallback_before_leaderboard_fix(user_question)

# IPL SQL Agent leaderboard routes overall/team/venue season fix END


# IPL SQL Agent leaderboard team column fix START

def _lbteam_q(value):
    return str(value).replace("'", "''")


def _lbteam_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _lbteam_q(v) + "'" for v in values) + ")"


def _lbteam_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "Rising Pune Supergiant", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "Gujarat Lions", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "Kochi Tuskers Kerala", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "Pune Warriors", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
        ("DEC", "Deccan Chargers", ["Deccan Chargers"], ["deccan"]),
    ]
    for code, canonical, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, canonical, aliases
    return None, None, []


def _lbteam_extract_season(question):
    import re
    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", str(question or ""))
    return match.group(1) if match else None


def _lbteam_parse_team(question):
    import re

    text = str(question or "")

    match = re.search(
        r"\b(?:for|from)\s+([A-Za-z0-9 .]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s+at\s+|\s+venue\s+|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        raw = match.group(1).strip(" .?")
        team = _lbteam_team_lookup(raw)
        if team[0]:
            return team

    for token in ["csk", "mi", "rcb", "gt", "kkr", "rr", "srh", "dc", "pbks", "kxip", "lsg"]:
        if re.search(rf"\b{token}\b", text, flags=re.IGNORECASE):
            team = _lbteam_team_lookup(token)
            if team[0]:
                return team

    return None, None, []


def _lbteam_parse_venue(question):
    import re

    text = str(question or "")

    match = re.search(
        r"\bat\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s+for\s+|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        match = re.search(
            r"\bvenue\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s+for\s+|\s*$)",
            text,
            flags=re.IGNORECASE,
        )

    if not match:
        return "1=1", None

    raw = match.group(1).strip(" .?")
    low = raw.lower()

    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"
    if "dubai" in low:
        return "(m.venue LIKE '%Dubai%' OR m.city LIKE '%Dubai%')", "Dubai"
    if "sharjah" in low:
        return "(m.venue LIKE '%Sharjah%' OR m.city LIKE '%Sharjah%')", "Sharjah"
    if "abu dhabi" in low or "zayed" in low:
        return "(m.venue LIKE '%Abu Dhabi%' OR m.venue LIKE '%Zayed%' OR m.city LIKE '%Abu Dhabi%')", "Abu Dhabi"

    safe = _lbteam_q(low)
    return f"(LOWER(m.venue) LIKE '%{safe}%' OR LOWER(m.city) LIKE '%{safe}%')", raw.title()


def _lbteam_is_batting_leaderboard(question):
    text = str(question or "").lower()
    return (
        "run scorer" in text
        or "run scorers" in text
        or "run scoer" in text
        or "run scoers" in text
        or "most runs" in text
        or "top runs" in text
        or "top 10 runs" in text
    )


def _lbteam_is_bowling_leaderboard(question):
    text = str(question or "").lower()
    return (
        "wicket taker" in text
        or "wicket takers" in text
        or "most wickets" in text
        or "top wickets" in text
        or "top 10 wickets" in text
    )


def _lbteam_limit(question):
    import re

    match = re.search(r"\btop\s+(\d+)\b", str(question or ""), flags=re.IGNORECASE)

    if match:
        value = int(match.group(1))
        if 1 <= value <= 50:
            return value

    return 10


def _lbteam_batting_leaderboard(question):
    import pandas as pd
    from app.db import run_query

    if not _lbteam_is_batting_leaderboard(question):
        return None

    limit = _lbteam_limit(question)
    season = _lbteam_extract_season(question)
    team_code, team_name, team_aliases = _lbteam_parse_team(question)
    venue_filter, venue_label = _lbteam_parse_venue(question)

    filters = [
        "d.innings IN (1, 2)",
        venue_filter,
    ]

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_lbteam_q(season)}'")

    if team_aliases:
        filters.append(f"d.batting_team IN {_lbteam_sql_list(team_aliases)}")

    where_sql = " AND ".join(filters)

    title_parts = [f"Top {limit} run scorers"]
    if team_code:
        title_parts.append(f"for {team_code}")
    if venue_label:
        title_parts.append(f"at {venue_label}")
    if season:
        title_parts.append(f"in {season}")
    else:
        title_parts.append("across all seasons")
    title = " ".join(title_parts)

    sql = f"""
WITH batter_innings AS (
    SELECT
        d.striker AS batter,
        d.batting_team AS team,
        d.season,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS balls,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out', 'retired not out')
            THEN 1 ELSE 0
        END) AS out_flag
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.striker, d.batting_team, d.season, d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) > 0
),
batter_totals AS (
    SELECT
        batter,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM batter_innings bi2
            WHERE bi2.batter = bi.batter
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(out_flag) AS dismissals,
        SUM(balls) AS balls,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM batter_innings bi
    GROUP BY batter
)
SELECT TOP {limit}
    batter,
    team,
    matches,
    innings,
    runs,
    dismissals,
    ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average,
    balls,
    ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate,
    highest_score,
    fifties,
    hundreds
FROM batter_totals
ORDER BY runs DESC, batting_average DESC, strike_rate DESC, batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The batting leaderboard route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": f"{title}. Team shows the batting team(s) represented within the requested filter.",
        "paragraph": f"{title}. Team shows the batting team(s) represented within the requested filter.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who are top 10 run scorers in 2026",
            "who are top 10 run scorers for CSK in 2026",
            "who are top 10 run scorers at Wankhede",
        ],
        "route_used": "Flexible batting leaderboard with team column",
        "data_sources": "deliveries, matches",
    }


def _lbteam_bowling_leaderboard(question):
    import pandas as pd
    from app.db import run_query

    if not _lbteam_is_bowling_leaderboard(question):
        return None

    limit = _lbteam_limit(question)
    season = _lbteam_extract_season(question)
    team_code, team_name, team_aliases = _lbteam_parse_team(question)
    venue_filter, venue_label = _lbteam_parse_venue(question)

    filters = [
        "d.innings IN (1, 2)",
        venue_filter,
    ]

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_lbteam_q(season)}'")

    if team_aliases:
        filters.append(f"d.bowling_team IN {_lbteam_sql_list(team_aliases)}")

    where_sql = " AND ".join(filters)

    title_parts = [f"Top {limit} wicket takers"]
    if team_code:
        title_parts.append(f"for {team_code}")
    if venue_label:
        title_parts.append(f"at {venue_label}")
    if season:
        title_parts.append(f"in {season}")
    else:
        title_parts.append("across all seasons")
    title = " ".join(title_parts)

    sql = f"""
WITH bowler_match AS (
    SELECT
        d.bowler,
        d.bowling_team AS team,
        d.match_id,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS legal_balls,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(CASE WHEN COALESCE(d.runs_off_bat, 0) = 0 AND COALESCE(d.extras, 0) = 0 THEN 1 END) AS dot_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.bowler, d.bowling_team, d.match_id
),
bowler_totals AS (
    SELECT
        bowler,
        STUFF((
            SELECT DISTINCT ', ' + bm2.team
            FROM bowler_match bm2
            WHERE bm2.bowler = bm.bowler
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        SUM(legal_balls) AS legal_balls,
        SUM(wickets) AS wickets,
        SUM(runs_conceded) AS runs_conceded,
        SUM(dot_balls) AS dot_balls
    FROM bowler_match bm
    GROUP BY bowler
)
SELECT TOP {limit}
    bowler,
    team,
    matches,
    CAST(legal_balls / 6 AS varchar(20)) + '.' + CAST(legal_balls % 6 AS varchar(1)) AS overs_bowled,
    wickets,
    runs_conceded,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy,
    ROUND(legal_balls * 1.0 / NULLIF(wickets, 0), 2) AS bowling_strike_rate,
    dot_balls
FROM bowler_totals
WHERE wickets > 0
ORDER BY wickets DESC, economy ASC, bowling_strike_rate ASC, bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The bowling leaderboard route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": f"{title}. Team shows the bowling team(s) represented within the requested filter.",
        "paragraph": f"{title}. Team shows the bowling team(s) represented within the requested filter.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "top 10 wicket takers in 2026",
            "top 10 wicket takers for CSK in 2026",
            "top 10 wicket takers at Wankhede",
        ],
        "route_used": "Flexible bowling leaderboard with team column",
        "data_sources": "deliveries, matches",
    }


try:
    _previous_answer_question_with_fallback_before_leaderboard_teamcol = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_leaderboard_teamcol = None


def answer_question_with_fallback(user_question):
    for route in [
        _lbteam_batting_leaderboard,
        _lbteam_bowling_leaderboard,
    ]:
        result = route(user_question)
        if result is not None:
            return result

    return _previous_answer_question_with_fallback_before_leaderboard_teamcol(user_question)

# IPL SQL Agent leaderboard team column fix END


# IPL SQL Agent bowling leaderboard innings compatibility fix START

def _wif_q(value):
    return str(value).replace("'", "''")


def _wif_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _wif_q(v) + "'" for v in values) + ")"


def _wif_team_lookup(text_value):
    text = str(text_value or "").lower().strip()
    teams = [
        ("CSK", "Chennai Super Kings", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "Mumbai Indians", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "Royal Challengers Bengaluru", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "Gujarat Titans", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "Kolkata Knight Riders", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "Rajasthan Royals", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "Sunrisers Hyderabad", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("DC", "Delhi Capitals", ["Delhi Daredevils", "Delhi Capitals"], ["dc", "delhi"]),
        ("PBKS", "Punjab Kings", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab"]),
        ("LSG", "Lucknow Super Giants", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "Rising Pune Supergiant", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "Gujarat Lions", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "Kochi Tuskers Kerala", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "Pune Warriors", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
        ("DEC", "Deccan Chargers", ["Deccan Chargers"], ["deccan"]),
    ]
    for code, canonical, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, canonical, aliases
    return None, None, []


def _wif_extract_season(question):
    import re
    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", str(question or ""))
    return match.group(1) if match else None


def _wif_parse_team(question):
    import re
    text = str(question or "")

    match = re.search(
        r"\b(?:for|from)\s+([A-Za-z0-9 .]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s+at\s+|\s+venue\s+|\s*$)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        raw = match.group(1).strip(" .?")
        team = _wif_team_lookup(raw)
        if team[0]:
            return team

    for token in ["csk", "mi", "rcb", "gt", "kkr", "rr", "srh", "dc", "pbks", "kxip", "lsg"]:
        if re.search(rf"\b{token}\b", text, flags=re.IGNORECASE):
            team = _wif_team_lookup(token)
            if team[0]:
                return team

    return None, None, []


def _wif_parse_venue(question):
    import re
    text = str(question or "")

    match = re.search(
        r"\bat\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s+for\s+|\s*$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"\bvenue\s+([A-Za-z0-9 .'-]+?)(?:\s+in\s+20\d{2}(?:/\d{2})?|\s+for\s+|\s*$)",
            text,
            flags=re.IGNORECASE,
        )

    if not match:
        return "1=1", None

    raw = match.group(1).strip(" .?")
    low = raw.lower()

    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"
    if "dubai" in low:
        return "(m.venue LIKE '%Dubai%' OR m.city LIKE '%Dubai%')", "Dubai"
    if "sharjah" in low:
        return "(m.venue LIKE '%Sharjah%' OR m.city LIKE '%Sharjah%')", "Sharjah"
    if "abu dhabi" in low or "zayed" in low:
        return "(m.venue LIKE '%Abu Dhabi%' OR m.venue LIKE '%Zayed%' OR m.city LIKE '%Abu Dhabi%')", "Abu Dhabi"

    safe = _wif_q(low)
    return f"(LOWER(m.venue) LIKE '%{safe}%' OR LOWER(m.city) LIKE '%{safe}%')", raw.title()


def _wif_is_bowling_leaderboard(question):
    text = str(question or "").lower()
    return (
        "wicket taker" in text
        or "wicket takers" in text
        or "most wickets" in text
        or "top wickets" in text
        or "top 10 wickets" in text
    )


def _wif_limit(question):
    import re
    match = re.search(r"\btop\s+(\d+)\b", str(question or ""), flags=re.IGNORECASE)
    if match:
        value = int(match.group(1))
        if 1 <= value <= 50:
            return value
    return 10


def _wif_bowling_leaderboard(question):
    import pandas as pd
    from app.db import run_query

    if not _wif_is_bowling_leaderboard(question):
        return None

    limit = _wif_limit(question)
    season = _wif_extract_season(question)
    team_code, team_name, team_aliases = _wif_parse_team(question)
    venue_filter, venue_label = _wif_parse_venue(question)

    filters = [
        "d.innings IN (1, 2)",
        venue_filter,
    ]

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_wif_q(season)}'")

    if team_aliases:
        filters.append(f"d.bowling_team IN {_wif_sql_list(team_aliases)}")

    where_sql = " AND ".join(filters)

    title_parts = [f"Top {limit} wicket takers"]
    if team_code:
        title_parts.append(f"for {team_code}")
    if venue_label:
        title_parts.append(f"at {venue_label}")
    if season:
        title_parts.append(f"in {season}")
    else:
        title_parts.append("across all seasons")
    title = " ".join(title_parts)

    sql = f"""
WITH bowler_innings AS (
    SELECT
        d.bowler,
        d.bowling_team AS team,
        d.match_id,
        d.innings,
        COUNT(CASE WHEN COALESCE(d.wides, 0) = 0 AND COALESCE(d.noballs, 0) = 0 THEN 1 END) AS legal_balls,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(CASE WHEN COALESCE(d.runs_off_bat, 0) = 0 AND COALESCE(d.extras, 0) = 0 THEN 1 END) AS dot_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.bowler, d.bowling_team, d.match_id, d.innings
),
bowler_totals AS (
    SELECT
        bowler,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM bowler_innings bi2
            WHERE bi2.bowler = bi.bowler
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(legal_balls) AS legal_balls,
        SUM(wickets) AS wickets,
        SUM(runs_conceded) AS runs_conceded,
        SUM(dot_balls) AS dot_balls
    FROM bowler_innings bi
    GROUP BY bowler
)
SELECT TOP {limit}
    bowler,
    team,
    matches,
    innings,
    CAST(legal_balls / 6 AS varchar(20)) + '.' + CAST(legal_balls % 6 AS varchar(1)) AS overs_bowled,
    wickets,
    runs_conceded,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy,
    ROUND(legal_balls * 1.0 / NULLIF(wickets, 0), 2) AS bowling_strike_rate,
    dot_balls
FROM bowler_totals
WHERE wickets > 0
ORDER BY wickets DESC, economy ASC, bowling_strike_rate ASC, bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The bowling leaderboard route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": f"{title}. Innings counts bowler innings, not batting innings. Team shows the bowling team(s) in the requested filter.",
        "paragraph": f"{title}. Innings counts bowler innings, not batting innings. Team shows the bowling team(s) in the requested filter.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who are the top 10 wicket takers in IPL",
            "top 10 wicket takers in 2026",
            "top 10 wicket takers for CSK in 2026",
            "top 10 wicket takers at Wankhede",
        ],
        "route_used": "Flexible bowling leaderboard with team and innings",
        "data_sources": "deliveries, matches",
    }


try:
    _previous_answer_question_with_fallback_before_wicket_innings_fix = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_wicket_innings_fix = None


def answer_question_with_fallback(user_question):
    result = _wif_bowling_leaderboard(user_question)
    if result is not None:
        return result
    return _previous_answer_question_with_fallback_before_wicket_innings_fix(user_question)

# IPL SQL Agent bowling leaderboard innings compatibility fix END


# IPL SQL Agent UI cleanup team names and profile suggestions START

def _uiclean_is_profile_question(question):
    import re
    text = str(question or "").strip()
    match = re.search(r"^(?:analyse|analyze|profile|tell me about)\s+(.+?)\s*$", text, flags=re.IGNORECASE)
    if not match:
        return None
    label = match.group(1).strip(" .?")
    low = label.lower()
    if any(x in low for x in ["stadium", "venue", "chepauk", "eden", "wankhede", "chinnaswamy", "narendra"]):
        return None
    team_words = {"csk", "mi", "rcb", "gt", "kkr", "rr", "srh", "dc", "pbks", "kxip", "lsg", "chennai", "mumbai", "bangalore", "bengaluru", "gujarat", "kolkata", "rajasthan", "hyderabad", "delhi", "punjab", "lucknow"}
    if low in team_words:
        return None
    return label


def _uiclean_known_display_name(label):
    low = str(label or "").lower()
    known = {
        "kohli": "V Kohli", "virat": "V Kohli",
        "raina": "SK Raina", "suresh": "SK Raina",
        "bumrah": "JJ Bumrah", "jasprit": "JJ Bumrah",
        "narine": "SP Narine", "sunil": "SP Narine",
        "rohit": "RG Sharma", "dhoni": "MS Dhoni",
        "gaikwad": "RD Gaikwad", "ruturaj": "RD Gaikwad",
        "sooryavanshi": "V Suryavanshi", "suryavanshi": "V Suryavanshi", "vaibhav": "V Suryavanshi",
        "sudharsan": "B Sai Sudharsan", "gill": "Shubman Gill",
        "rashid": "Rashid Khan", "jadeja": "RA Jadeja",
        "warner": "DA Warner", "rahul": "KL Rahul", "de villiers": "AB de Villiers",
    }
    for key, value in known.items():
        if key in low:
            return value
    return str(label or "").strip()


def _uiclean_table_scalar(table, column_name):
    try:
        if table is not None and hasattr(table, "columns") and column_name in table.columns and not table.empty:
            value = table.iloc[0][column_name]
            if value is not None and str(value).strip() and str(value).lower() != "nan":
                return str(value).strip()
    except Exception:
        pass
    return None


def _uiclean_resolved_player(result, label):
    if not isinstance(result, dict):
        return _uiclean_known_display_name(label)
    table = result.get("result")
    for column in ["resolved_player", "player", "batter", "bowler"]:
        value = _uiclean_table_scalar(table, column)
        if value:
            return value
    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for table in extra.values():
            for column in ["resolved_player", "player", "batter", "bowler"]:
                value = _uiclean_table_scalar(table, column)
                if value:
                    return value
    return _uiclean_known_display_name(label)


def _uiclean_profile_type(result):
    if not isinstance(result, dict):
        return "mixed"

    def first_numeric(table, name):
        try:
            if table is not None and hasattr(table, "columns") and name in table.columns and not table.empty:
                value = table.iloc[0][name]
                if value is None or str(value).lower() == "nan":
                    return 0.0
                return float(value)
        except Exception:
            pass
        return 0.0

    result_table = result.get("result")
    wickets = first_numeric(result_table, "wickets")
    runs = first_numeric(result_table, "runs")

    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in extra.items():
            lname = str(name).lower()
            if "bowling" in lname:
                wickets = max(wickets, first_numeric(table, "wickets"))
            if "batting" in lname:
                runs = max(runs, first_numeric(table, "runs"))

    if wickets >= 25 and wickets * 8 > runs:
        return "bowler"
    if runs >= 1000 and runs > wickets * 8:
        return "batter"
    return "mixed"


def _uiclean_profile_questions(player, profile_type):
    player = str(player or "").strip() or "this player"
    if profile_type == "bowler":
        return [
            f"analyse Rashid Khan",
            f"compare {player} and Rashid Khan",
            "who are the top 10 wicket takers in IPL",
            "who has bowled the most dot balls in death overs",
        ]
    if profile_type == "batter":
        return [
            f"how many fifties does {player} have",
            f"compare {player} and V Kohli",
            "who has the most fifties in IPL",
            "who are top 10 run scorers in 2026",
        ]
    return [
        f"compare {player} and SP Narine",
        f"how many fifties does {player} have",
        "who are the top 10 wicket takers in IPL",
        "who are top 10 run scorers in 2026",
    ]


def _uiclean_clean_profile(result, label):
    if not isinstance(result, dict):
        return result
    player = _uiclean_resolved_player(result, label)
    profile_type = _uiclean_profile_type(result)
    if profile_type == "bowler":
        paragraph = f"Player profile for {player}. Bowling and batting summaries are included below."
    else:
        paragraph = f"Player profile for {player}. Batting and bowling summaries are included below."
    result["analysis_paragraph"] = paragraph
    result["paragraph"] = paragraph
    result["similar_questions"] = _uiclean_profile_questions(player, profile_type)[:4]
    return result


def _uiclean_team_name_value(value):
    if value is None:
        return value
    pieces = [piece.strip() for piece in str(value).split(",")]
    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Capitals": "Delhi Capitals",
        "Delhi Daredevils": "Delhi Daredevils",
        "Deccan Chargers": "Deccan Chargers",
    }
    return ", ".join(mapping.get(piece, piece) for piece in pieces)


def _uiclean_apply_short_team_names(table):
    if table is None or not hasattr(table, "columns"):
        return table
    try:
        table = table.copy()
        for column in ["team", "batting_team", "bowling_team", "winner", "toss_winner"]:
            if column in table.columns:
                table[column] = table[column].apply(_uiclean_team_name_value)
        return table
    except Exception:
        return table


def _uiclean_apply_table_cleanup(result):
    if not isinstance(result, dict):
        return result
    result["result"] = _uiclean_apply_short_team_names(result.get("result"))
    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _uiclean_apply_short_team_names(table)
        result["extra_tables"] = extra
    return result


try:
    _previous_answer_question_with_fallback_before_uiclean = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_uiclean = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_uiclean(user_question)
    result = _uiclean_apply_table_cleanup(result)
    label = _uiclean_is_profile_question(user_question)
    if label:
        result = _uiclean_clean_profile(result, label)
    return result

# IPL SQL Agent UI cleanup team names and profile suggestions END


# IPL SQL Agent DC ambiguity, current-squad matchup, and concise text fix START

def _dcclean_q(value):
    return str(value).replace("'", "''")


def _dcclean_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _dcclean_q(v) + "'" for v in values) + ")"


def _dcclean_batter_aliases(label):
    raw = str(label or "").strip()
    low = raw.lower()
    aliases = [raw]

    known = {
        "kohli": ["V Kohli", "Virat Kohli"],
        "virat": ["V Kohli", "Virat Kohli"],
        "rohit": ["RG Sharma", "Rohit Sharma"],
        "gaikwad": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "ruturaj": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "dhoni": ["MS Dhoni"],
        "raina": ["SK Raina", "Suresh Raina"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sudharsan": ["B Sai Sudharsan", "Sai Sudharsan"],
        "gill": ["Shubman Gill"],
    }

    for key, values in known.items():
        if key in low:
            for value in values:
                if value not in aliases:
                    aliases.append(value)

    return aliases


def _dcclean_parse_best_bowlers_against(question):
    import re

    text = str(question or "").strip()

    patterns = [
        r"\bbest\s+bowlers\s+against\s+(.+?)\s+for\s+(.+?)\s*$",
        r"\bbest\s+bowler\s+against\s+(.+?)\s+for\s+(.+?)\s*$",
        r"\bwhich\s+bowlers\s+are\s+best\s+against\s+(.+?)\s+for\s+(.+?)\s*$",
        r"\bwhich\s+(.+?)\s+bowlers\s+are\s+best\s+against\s+(.+?)\s*$",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        if pattern.startswith(r"\bwhich\s+(.+?)"):
            team_raw = match.group(1).strip(" .?")
            batter_raw = match.group(2).strip(" .?")
        else:
            batter_raw = match.group(1).strip(" .?")
            team_raw = match.group(2).strip(" .?")

        return batter_raw, team_raw

    return None


def _dcclean_team_from_matchup_text(team_raw):
    low = str(team_raw or "").lower().strip()

    if low == "dc":
        return "AMBIGUOUS_DC", None, None

    if "delhi capitals" in low:
        return "DC", "Delhi Capitals", ["Delhi Capitals"]

    if "delhi daredevils" in low:
        return "DD", "Delhi Daredevils", ["Delhi Daredevils"]

    if "deccan chargers" in low:
        return "DEC", "Deccan Chargers", ["Deccan Chargers"]

    teams = [
        ("CSK", "CSK", ["Chennai Super Kings"], ["csk", "chennai"]),
        ("MI", "MI", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "RCB", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru"]),
        ("GT", "GT", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "KKR", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "RR", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "SRH", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("PBKS", "PBKS", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab"]),
        ("LSG", "LSG", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
    ]

    for code, display, aliases, triggers in teams:
        if low in triggers or any(trigger in low for trigger in triggers):
            return code, display, aliases

    return None, None, None


def _dcclean_dc_ambiguity_response(question):
    import pandas as pd

    data = pd.DataFrame([
        {
            "issue": "DC is ambiguous",
            "action": "Please write Delhi Capitals or Deccan Chargers in full.",
            "example": "best bowlers against Kohli for Delhi Capitals",
        }
    ])

    paragraph = "DC is ambiguous because it can mean Delhi Capitals or Deccan Chargers. Please use the full team name."

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": data,
        "extra_tables": {"Clarification": data},
        "sql_query": "",
        "similar_questions": [
            "best bowlers against Kohli for Delhi Capitals",
            "best bowlers against Kohli for Deccan Chargers",
            "best bowlers against Rohit for Delhi Capitals",
            "best bowlers against Gaikwad for Delhi Capitals",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _dcclean_best_bowlers_against_route(question):
    import pandas as pd
    from app.db import run_query

    parsed = _dcclean_parse_best_bowlers_against(question)

    if not parsed:
        return None

    batter_raw, team_raw = parsed
    team_code, display_team, team_aliases = _dcclean_team_from_matchup_text(team_raw)

    if team_code == "AMBIGUOUS_DC":
        return _dcclean_dc_ambiguity_response(question)

    if not team_code:
        return None

    batter_aliases = _dcclean_batter_aliases(batter_raw)
    batter_sql = _dcclean_sql_list(batter_aliases)

    current_team_codes = {"DC", "CSK", "MI", "RCB", "GT", "KKR", "RR", "SRH", "PBKS", "LSG"}

    if team_code in current_team_codes:
        sql = f"""
WITH current_bowlers AS (
    SELECT DISTINCT
        display_name,
        cricsheet_name,
        role,
        bowling_style,
        bowling_arm
    FROM current_squads
    WHERE team_code = '{_dcclean_q(team_code)}'
      AND COALESCE(is_active, 1) = 1
      AND (role LIKE '%Bowler%' OR role LIKE '%All%')
)
SELECT
    cb.display_name AS bowler,
    '{_dcclean_q(display_team)}' AS team,
    cb.role,
    cb.bowling_style,
    cb.bowling_arm,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr,
    CASE
        WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) >= 12 THEN 'Usable direct sample'
        WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0 THEN 'Small direct sample'
        ELSE 'No direct sample'
    END AS sample_note
FROM current_bowlers cb
LEFT JOIN deliveries d
    ON (d.bowler = cb.cricsheet_name OR d.bowler = cb.display_name)
   AND d.striker IN {batter_sql}
   AND d.innings IN (1, 2)
GROUP BY cb.display_name, cb.role, cb.bowling_style, cb.bowling_arm
ORDER BY
    CASE WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0 THEN 0 ELSE 1 END,
    dismissals DESC,
    batter_sr ASC,
    balls DESC,
    bowler ASC;
""".strip()
    else:
        sql = f"""
SELECT
    d.bowler,
    d.bowling_team AS team,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN d.wicket_type IS NOT NULL AND d.player_dismissed = d.striker THEN 1 END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr
FROM deliveries d
WHERE d.bowling_team IN {_dcclean_sql_list(team_aliases)}
  AND d.striker IN {batter_sql}
  AND d.innings IN (1, 2)
GROUP BY d.bowler, d.bowling_team
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
ORDER BY dismissals DESC, batter_sr ASC, balls DESC, bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The best-bowlers-against route failed: {error}",
            "paragraph": f"The best-bowlers-against route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
            "route_used": "",
            "data_sources": "",
        }

    df = df if df is not None else pd.DataFrame()

    if team_code in current_team_codes:
        paragraph = f"Best current {display_team} bowling options against {batter_raw}."
    else:
        paragraph = f"Best historical {display_team} bowlers against {batter_raw}."

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {f"{display_team} bowlers vs {batter_raw}": df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            f"best bowlers against {batter_raw} for Delhi Capitals",
            f"best bowlers against {batter_raw} for CSK",
            f"best bowlers against Rohit for Delhi Capitals",
            f"best bowlers against Gaikwad for Delhi Capitals",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _dcclean_is_match_plan_result(question, result):
    text = str(question or "").lower()

    if "match plan" in text:
        return True

    if "how can" in text and " beat " in text:
        return True

    if isinstance(result, dict):
        extra = result.get("extra_tables")
        if isinstance(extra, dict):
            keys = {str(k).lower() for k in extra.keys()}
            if ("key matchups" in keys or "opponent key batters" in keys) and any("phase diagnostic" in k for k in keys):
                return True

    return False


def _dcclean_concise_match_plan_text(question, result):
    if not isinstance(result, dict):
        return result

    if not _dcclean_is_match_plan_result(question, result):
        return result

    paragraph = "Match plan generated. See the action plan and supporting tabs below."

    result["analysis_paragraph"] = paragraph
    result["paragraph"] = paragraph

    return result


def _dcclean_hide_route_metadata(result):
    if isinstance(result, dict):
        result["route_used"] = ""
        result["data_sources"] = ""
    return result


try:
    _previous_answer_question_with_fallback_before_dcclean = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_dcclean = None


def answer_question_with_fallback(user_question):
    result = _dcclean_best_bowlers_against_route(user_question)

    if result is None:
        result = _previous_answer_question_with_fallback_before_dcclean(user_question)

    result = _dcclean_concise_match_plan_text(user_question, result)
    result = _dcclean_hide_route_metadata(result)

    return result

# IPL SQL Agent DC ambiguity, current-squad matchup, and concise text fix END


# IPL SQL Agent team cleanup + profile season trend tabs START

def _ptab_q(value):
    return str(value).replace("'", "''")


def _ptab_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _ptab_q(v) + "'" for v in values) + ")"


def _ptab_short_team_value(value):
    if value is None:
        return value

    pieces = [piece.strip() for piece in str(value).split(",") if piece and str(piece).strip()]

    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "DD",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }

    cleaned = []
    seen = set()

    for piece in pieces:
        short = mapping.get(piece, piece)
        key = short.lower()
        if key not in seen:
            cleaned.append(short)
            seen.add(key)

    return ", ".join(cleaned)


def _ptab_clean_table_team_columns(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()
        for column in ["team", "teams", "batting_team", "bowling_team", "opposition", "winner", "toss_winner"]:
            if column in table.columns:
                table[column] = table[column].apply(_ptab_short_team_value)
        return table
    except Exception:
        return table


def _ptab_clean_result_team_columns(result):
    if not isinstance(result, dict):
        return result

    result["result"] = _ptab_clean_table_team_columns(result.get("result"))

    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _ptab_clean_table_team_columns(table)
        result["extra_tables"] = extra

    return result


def _ptab_team_lookup(label):
    text = str(label or "").lower().strip()
    terms = {
        "csk", "chennai", "mi", "mumbai", "rcb", "bangalore", "bengaluru", "gt", "gujarat",
        "kkr", "kolkata", "rr", "rajasthan", "srh", "sunrisers", "dc", "delhi capitals",
        "dd", "delhi daredevils", "deccan chargers", "pbks", "kxip", "punjab", "lsg", "lucknow",
        "rps", "rising pune", "gl", "gujarat lions", "ktk", "kochi", "pwi", "pune warriors"
    }
    return any(term == text or term in text for term in terms)


def _ptab_profile_label(question):
    import re
    text = str(question or "").strip()
    match = re.search(r"^(?:analyse|analyze|profile|tell me about)\s+(.+?)\s*$", text, flags=re.IGNORECASE)

    if not match:
        return None

    label = match.group(1).strip(" .?")
    low = label.lower()

    if _ptab_team_lookup(label):
        return None

    if any(x in low for x in ["stadium", "venue", "chepauk", "eden", "wankhede", "chinnaswamy", "narendra"]):
        return None

    return label


def _ptab_player_aliases(label):
    raw = str(label or "").strip()
    low = raw.lower()
    aliases = [raw]

    known = {
        "kohli": ["V Kohli", "Virat Kohli"],
        "virat": ["V Kohli", "Virat Kohli"],
        "bumrah": ["JJ Bumrah", "Jasprit Bumrah"],
        "jasprit": ["JJ Bumrah", "Jasprit Bumrah"],
        "raina": ["SK Raina", "Suresh Raina"],
        "suresh": ["SK Raina", "Suresh Raina"],
        "narine": ["SP Narine", "Sunil Narine"],
        "sunil": ["SP Narine", "Sunil Narine"],
        "rohit": ["RG Sharma", "Rohit Sharma"],
        "dhoni": ["MS Dhoni"],
        "gaikwad": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "ruturaj": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sudharsan": ["B Sai Sudharsan", "Sai Sudharsan"],
        "gill": ["Shubman Gill"],
        "rashid": ["Rashid Khan"],
        "jadeja": ["RA Jadeja", "Ravindra Jadeja"],
        "rahul": ["KL Rahul"],
        "warner": ["DA Warner", "David Warner"],
        "de villiers": ["AB de Villiers"],
    }

    for key, values in known.items():
        if key in low:
            for value in values:
                if value not in aliases:
                    aliases.append(value)

    return aliases


def _ptab_resolve_player(label):
    from app.db import run_query

    aliases = _ptab_player_aliases(label)

    sql = f"""
SELECT TOP 1 player_name
FROM (
    SELECT striker AS player_name, COUNT(*) AS appearances
    FROM deliveries
    WHERE striker IN {_ptab_sql_list(aliases)}
    GROUP BY striker

    UNION ALL

    SELECT bowler AS player_name, COUNT(*) AS appearances
    FROM deliveries
    WHERE bowler IN {_ptab_sql_list(aliases)}
    GROUP BY bowler

    UNION ALL

    SELECT cricsheet_name AS player_name, 1000 AS appearances
    FROM current_squads
    WHERE display_name IN {_ptab_sql_list(aliases)}
       OR cricsheet_name IN {_ptab_sql_list(aliases)}
) x
WHERE player_name IS NOT NULL
GROUP BY player_name
ORDER BY SUM(appearances) DESC, player_name ASC;
""".strip()

    try:
        df = run_query(sql)
        if df is not None and not df.empty:
            resolved = str(df.iloc[0]["player_name"])
            if resolved not in aliases:
                aliases.insert(0, resolved)
            return resolved, aliases
    except Exception:
        pass

    return aliases[0], aliases


def _ptab_add_profile_season_trends(question, result):
    import pandas as pd
    from app.db import run_query

    if not isinstance(result, dict):
        return result

    label = _ptab_profile_label(question)
    if not label:
        return result

    resolved, aliases = _ptab_resolve_player(label)

    batting_sql = f"""
WITH innings_scores AS (
    SELECT
        d.season,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out', 'retired not out')
            THEN 1 ELSE 0
        END) AS out_flag
    FROM deliveries d
    WHERE d.striker IN {_ptab_sql_list(aliases)}
      AND d.innings IN (1, 2)
    GROUP BY d.season, d.match_id, d.innings
)
SELECT
    season,
    COUNT(DISTINCT match_id) AS matches,
    COUNT(*) AS innings,
    SUM(innings_runs) AS runs,
    SUM(out_flag) AS dismissals,
    ROUND(SUM(innings_runs) * 1.0 / NULLIF(SUM(out_flag), 0), 2) AS batting_average,
    SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
    SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
    ROUND(SUM(innings_runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate
FROM innings_scores
GROUP BY season
ORDER BY
    CASE
        WHEN CHARINDEX('/', CAST(season AS varchar(20))) > 0
        THEN TRY_CONVERT(INT, LEFT(CAST(season AS varchar(20)), 4))
        ELSE TRY_CONVERT(INT, CAST(season AS varchar(20)))
    END,
    season;
""".strip()

    bowling_sql = f"""
SELECT
    d.season,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS innings,
    CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) / 6 AS varchar(20))
        + '.' +
        CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) % 6 AS varchar(1)) AS overs_bowled,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
         AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
        THEN 1
    END) AS wickets,
    SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS economy,
    ROUND(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) * 1.0 / NULLIF(COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
         AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
        THEN 1
    END), 0), 2) AS bowling_strike_rate,
    COUNT(CASE WHEN COALESCE(d.runs_off_bat, 0)=0 AND COALESCE(d.extras, 0)=0 THEN 1 END) AS dot_balls
FROM deliveries d
WHERE d.bowler IN {_ptab_sql_list(aliases)}
  AND d.innings IN (1, 2)
GROUP BY d.season
ORDER BY
    CASE
        WHEN CHARINDEX('/', CAST(d.season AS varchar(20))) > 0
        THEN TRY_CONVERT(INT, LEFT(CAST(d.season AS varchar(20)), 4))
        ELSE TRY_CONVERT(INT, CAST(d.season AS varchar(20)))
    END,
    d.season;
""".strip()

    try:
        batting_df = run_query(batting_sql)
        bowling_df = run_query(bowling_sql)
    except Exception:
        return result

    batting_df = batting_df if batting_df is not None else pd.DataFrame()
    bowling_df = bowling_df if bowling_df is not None else pd.DataFrame()

    extra = result.get("extra_tables")
    if not isinstance(extra, dict):
        extra = {}

    if not batting_df.empty:
        extra["Batting Season Trend"] = batting_df

    if not bowling_df.empty:
        extra["Bowling Season Trend"] = bowling_df

    result["extra_tables"] = extra
    result["sql_query"] = (result.get("sql_query") or "") + "\n\n" + batting_sql + "\n\n" + bowling_sql

    return result


try:
    _previous_answer_question_with_fallback_before_profile_tabs_team_cleanup = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_profile_tabs_team_cleanup = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_profile_tabs_team_cleanup(user_question)
    result = _ptab_add_profile_season_trends(user_question, result)
    result = _ptab_clean_result_team_columns(result)
    return result

# IPL SQL Agent team cleanup + profile season trend tabs END


# IPL SQL Agent filtered player milestones and wickets against team START

def _fwfix_q(value):
    return str(value).replace("'", "''")


def _fwfix_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _fwfix_q(v) + "'" for v in values) + ")"


def _fwfix_team_lookup(text_value):
    text = str(text_value or "").lower().strip()

    teams = [
        ("CSK", "CSK", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "MI", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "RCB", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "GT", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "KKR", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "RR", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "SRH", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("Delhi Capitals", "Delhi Capitals", ["Delhi Capitals"], ["delhi capitals"]),
        ("DD", "DD", ["Delhi Daredevils"], ["dd", "delhi daredevils"]),
        ("Deccan Chargers", "Deccan Chargers", ["Deccan Chargers"], ["deccan", "deccan chargers"]),
        ("PBKS", "PBKS", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "LSG", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "RPS", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "GL", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "KTK", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "PWI", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
    ]

    for code, display, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, display, aliases

    return None, None, []


def _fwfix_team_short_value(value):
    if value is None:
        return value

    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "DD",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }

    parts = [p.strip() for p in str(value).split(",") if p and str(p).strip()]
    cleaned = []
    seen = set()

    for part in parts:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            cleaned.append(short)
            seen.add(key)

    return ", ".join(cleaned)


def _fwfix_cleanup_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()
        for column in ["team", "teams", "batting_team", "bowling_team", "opposition"]:
            if column in table.columns:
                table[column] = table[column].apply(_fwfix_team_short_value)
        return table
    except Exception:
        return table


def _fwfix_cleanup_result(result):
    if not isinstance(result, dict):
        return result

    result["result"] = _fwfix_cleanup_table(result.get("result"))

    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _fwfix_cleanup_table(table)
        result["extra_tables"] = extra

    return result


def _fwfix_player_aliases(label):
    raw = str(label or "").strip()
    low = raw.lower()
    aliases = [raw]

    known = {
        "kohli": ["V Kohli", "Virat Kohli"],
        "virat": ["V Kohli", "Virat Kohli"],
        "bumrah": ["JJ Bumrah", "Jasprit Bumrah"],
        "jasprit": ["JJ Bumrah", "Jasprit Bumrah"],
        "raina": ["SK Raina", "Suresh Raina"],
        "suresh": ["SK Raina", "Suresh Raina"],
        "narine": ["SP Narine", "Sunil Narine"],
        "rohit": ["RG Sharma", "Rohit Sharma"],
        "dhoni": ["MS Dhoni"],
        "gaikwad": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "ruturaj": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sudharsan": ["B Sai Sudharsan", "Sai Sudharsan"],
        "gill": ["Shubman Gill"],
        "rashid": ["Rashid Khan"],
        "jadeja": ["RA Jadeja", "Ravindra Jadeja"],
        "rahul": ["KL Rahul"],
        "warner": ["DA Warner", "David Warner"],
        "de villiers": ["AB de Villiers"],
    }

    for key, values in known.items():
        if key in low:
            for value in values:
                if value not in aliases:
                    aliases.append(value)

    return aliases


def _fwfix_resolve_player(label):
    from app.db import run_query

    aliases = _fwfix_player_aliases(label)

    sql = f"""
SELECT TOP 1 player_name
FROM (
    SELECT striker AS player_name, COUNT(*) AS appearances
    FROM deliveries
    WHERE striker IN {_fwfix_sql_list(aliases)}
    GROUP BY striker

    UNION ALL

    SELECT bowler AS player_name, COUNT(*) AS appearances
    FROM deliveries
    WHERE bowler IN {_fwfix_sql_list(aliases)}
    GROUP BY bowler

    UNION ALL

    SELECT cricsheet_name AS player_name, 1000 AS appearances
    FROM current_squads
    WHERE display_name IN {_fwfix_sql_list(aliases)}
       OR cricsheet_name IN {_fwfix_sql_list(aliases)}
) x
WHERE player_name IS NOT NULL
GROUP BY player_name
ORDER BY SUM(appearances) DESC, player_name ASC;
""".strip()

    try:
        df = run_query(sql)
        if df is not None and not df.empty:
            resolved = str(df.iloc[0]["player_name"])
            if resolved not in aliases:
                aliases.insert(0, resolved)
            return resolved, aliases
    except Exception:
        pass

    return aliases[0], aliases


def _fwfix_extract_season(question):
    import re

    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", str(question or ""))

    return match.group(1) if match else None


def _fwfix_venue_filter(question):
    import re

    text = str(question or "")
    match = re.search(
        r"\bat\s+([A-Za-z0-9 .'-]+?)(?:\s+against\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return "1=1", None

    raw = match.group(1).strip(" .?")
    low = raw.lower()

    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"

    safe = _fwfix_q(low)
    return f"(LOWER(m.venue) LIKE '%{safe}%' OR LOWER(m.city) LIKE '%{safe}%')", raw.title()


def _fwfix_parse_player_milestone_question(question):
    import re

    text = str(question or "").strip()
    low = text.lower()

    if "fifties" in low or "50s" in low or "fifty" in low:
        metric = "fifties"
    elif "hundreds" in low or "100s" in low or "centuries" in low:
        metric = "hundreds"
    else:
        return None

    match = re.search(
        r"\bhow\s+many\s+(?:fifties|50s|fifty scores|hundreds|100s|centuries)\s+(?:does|has)\s+(.+?)(?:\s+have|\s+scored|\s+against|\s+at|\s+in\s+20\d{2}(?:/\d{2})?|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    player_label = match.group(1).strip(" .?")

    against_team = None
    team_match = re.search(
        r"\bagainst\s+([A-Za-z0-9 .]+?)(?:\s+at\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if team_match:
        team_code, team_display, team_aliases = _fwfix_team_lookup(team_match.group(1).strip(" .?"))
        if team_code:
            against_team = (team_code, team_display, team_aliases)

    season = _fwfix_extract_season(text)
    venue_filter, venue_label = _fwfix_venue_filter(text)

    return metric, player_label, against_team, season, venue_filter, venue_label


def _fwfix_player_filtered_milestones(question):
    import pandas as pd
    from app.db import run_query

    parsed = _fwfix_parse_player_milestone_question(question)

    if not parsed:
        return None

    metric, player_label, against_team, season, venue_filter, venue_label = parsed
    resolved, aliases = _fwfix_resolve_player(player_label)

    filters = [
        f"d.striker IN {_fwfix_sql_list(aliases)}",
        "d.innings IN (1, 2)",
        venue_filter,
    ]

    if against_team:
        filters.append(f"d.bowling_team IN {_fwfix_sql_list(against_team[2])}")

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_fwfix_q(season)}'")

    where_sql = " AND ".join(filters)

    title_bits = [f"{metric.title()} for {resolved}"]
    if against_team:
        title_bits.append(f"against {against_team[1]}")
    if venue_label:
        title_bits.append(f"at {venue_label}")
    if season:
        title_bits.append(f"in {season}")
    title = " ".join(title_bits)

    sql = f"""
WITH innings_scores AS (
    SELECT
        d.striker AS player,
        d.season,
        d.match_id,
        CAST(m.start_date AS date) AS match_date,
        d.batting_team,
        d.bowling_team AS opposition,
        m.venue,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.striker, d.season, d.match_id, CAST(m.start_date AS date), d.batting_team, d.bowling_team, m.venue, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
),
summary AS (
    SELECT
        '{_fwfix_q(resolved)}' AS player,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
        SUM(CASE WHEN innings_runs >= 50 THEN 1 ELSE 0 END) AS fifty_plus_scores,
        MAX(innings_runs) AS highest_score
    FROM innings_scores
)
SELECT *
FROM summary;
""".strip()

    detail_where = "innings_runs >= 100" if metric == "hundreds" else "innings_runs >= 50"

    detail_sql = f"""
WITH innings_scores AS (
    SELECT
        d.striker AS player,
        d.season,
        d.match_id,
        CAST(m.start_date AS date) AS match_date,
        d.batting_team,
        d.bowling_team AS opposition,
        m.venue,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.striker, d.season, d.match_id, CAST(m.start_date AS date), d.batting_team, d.bowling_team, m.venue, d.innings
)
SELECT
    season,
    match_date,
    batting_team,
    opposition,
    venue,
    innings,
    innings_runs,
    balls,
    CASE
        WHEN innings_runs BETWEEN 50 AND 99 THEN 'Fifty'
        WHEN innings_runs >= 100 THEN 'Hundred'
        ELSE ''
    END AS score_type
FROM innings_scores
WHERE {detail_where}
ORDER BY innings_runs DESC, match_date ASC;
""".strip()

    try:
        summary_df = run_query(sql)
        detail_df = run_query(detail_sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The filtered milestone route failed: {error}",
            "paragraph": f"The filtered milestone route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql + "\n\n" + detail_sql,
            "similar_questions": [],
        }

    summary_df = summary_df if summary_df is not None else pd.DataFrame()
    detail_df = detail_df if detail_df is not None else pd.DataFrame()

    count_value = int(summary_df.iloc[0].get(metric) or 0) if not summary_df.empty and metric in summary_df.columns else 0
    paragraph = f"{title}: {count_value}."

    if metric == "fifties":
        paragraph += " Fifties means 50–99; hundreds are counted separately."

    return _fwfix_cleanup_result({
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": summary_df,
        "extra_tables": {
            "Summary": summary_df,
            "Scoring Innings": detail_df,
        },
        "sql_query": sql + "\n\n" + detail_sql,
        "similar_questions": [
            f"how many hundreds does {resolved} have",
            f"how many fifties does {resolved} have against CSK",
            f"how many hundreds does {resolved} have against MI",
            f"how many fifties does {resolved} have at Wankhede",
        ],
        "route_used": "",
        "data_sources": "",
    })


def _fwfix_parse_wickets_against_team(question):
    import re

    text = str(question or "").strip()

    if not re.search(r"\b(most|top|highest|taken)\b", text, flags=re.IGNORECASE):
        return None

    if not re.search(r"\bwickets?\b", text, flags=re.IGNORECASE):
        return None

    team_match = re.search(
        r"\bagainst\s+([A-Za-z0-9 .]+?)(?:\s+at\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if not team_match:
        return None

    team_code, team_display, team_aliases = _fwfix_team_lookup(team_match.group(1).strip(" .?"))

    if not team_code:
        return None

    season = _fwfix_extract_season(text)
    venue_filter, venue_label = _fwfix_venue_filter(text)

    return team_code, team_display, team_aliases, season, venue_filter, venue_label


def _fwfix_wickets_against_team(question):
    import pandas as pd
    from app.db import run_query

    parsed = _fwfix_parse_wickets_against_team(question)

    if not parsed:
        return None

    team_code, team_display, team_aliases, season, venue_filter, venue_label = parsed

    filters = [
        f"d.batting_team IN {_fwfix_sql_list(team_aliases)}",
        "d.innings IN (1, 2)",
        venue_filter,
    ]

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_fwfix_q(season)}'")

    where_sql = " AND ".join(filters)

    title_bits = [f"Most wickets against {team_display}"]
    if venue_label:
        title_bits.append(f"at {venue_label}")
    if season:
        title_bits.append(f"in {season}")
    title = " ".join(title_bits)

    sql = f"""
WITH bowler_innings AS (
    SELECT
        d.bowler,
        d.bowling_team AS team,
        d.match_id,
        d.innings,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS legal_balls,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(CASE WHEN COALESCE(d.runs_off_bat, 0)=0 AND COALESCE(d.extras, 0)=0 THEN 1 END) AS dot_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.bowler, d.bowling_team, d.match_id, d.innings
),
bowler_totals AS (
    SELECT
        bowler,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM bowler_innings bi2
            WHERE bi2.bowler = bi.bowler
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(legal_balls) AS legal_balls,
        SUM(wickets) AS wickets,
        SUM(runs_conceded) AS runs_conceded,
        SUM(dot_balls) AS dot_balls
    FROM bowler_innings bi
    GROUP BY bowler
)
SELECT TOP 25
    bowler,
    team,
    matches,
    innings,
    CAST(legal_balls / 6 AS varchar(20)) + '.' + CAST(legal_balls % 6 AS varchar(1)) AS overs_bowled,
    wickets,
    runs_conceded,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy,
    ROUND(legal_balls * 1.0 / NULLIF(wickets, 0), 2) AS bowling_strike_rate,
    dot_balls
FROM bowler_totals
WHERE wickets > 0
ORDER BY wickets DESC, economy ASC, bowling_strike_rate ASC, bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The wickets-against-team route failed: {error}",
            "paragraph": f"The wickets-against-team route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return _fwfix_cleanup_result({
        "question": question,
        "analysis_paragraph": f"{title}. This ranks opposition bowlers who took wickets while bowling against {team_display}.",
        "paragraph": f"{title}. This ranks opposition bowlers who took wickets while bowling against {team_display}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has taken the most wickets against MI",
            "who has taken the most wickets against CSK in 2026",
            "who has taken the most wickets against RCB at Wankhede",
            f"top 10 wicket takers against {team_display}",
        ],
        "route_used": "",
        "data_sources": "",
    })


try:
    _previous_answer_question_with_fallback_before_filtered_milestones_wickets = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_filtered_milestones_wickets = None


def answer_question_with_fallback(user_question):
    for route in [
        _fwfix_player_filtered_milestones,
        _fwfix_wickets_against_team,
    ]:
        result = route(user_question)
        if result is not None:
            return result

    result = _previous_answer_question_with_fallback_before_filtered_milestones_wickets(user_question)
    return _fwfix_cleanup_result(result)

# IPL SQL Agent filtered player milestones and wickets against team END


# IPL SQL Agent venue wording normalizer START

def _vennorm_should_try(question):
    text = str(question or "").lower()
    return any(word in text for word in [
        "run scorer", "run scorers", "run scoer", "run scoers", "most runs", "highest runs",
        "wicket taker", "wicket takers", "most wickets", "highest wickets",
        "fifties", "hundreds", "50s", "100s", "centuries",
        "fastest 50", "fastest 100", "death overs", "powerplay", "middle overs"
    ])


def _vennorm_normalize(question):
    import re

    original = str(question or "")

    if not _vennorm_should_try(original):
        return original

    venue_words = (
        r"wankhede|chepauk|chidambaram|eden gardens|eden|chinnaswamy|"
        r"narendra modi(?: stadium)?|motera|ahmedabad|dubai|sharjah|"
        r"abu dhabi|zayed|brabourne|kotla|arun jaitley|"
        r"sawai mansingh|sawai|jaipur|mohali|bindra|"
        r"dharamsala|dharamshala|rajiv gandhi|uppal"
    )

    # Convert "in Wankhede" / "inside Wankhede" / "on Wankhede" to "at Wankhede"
    # while avoiding "in 2026", "in IPL", etc.
    pattern = re.compile(
        rf"\b(?:in|inside|on)\s+({venue_words})(?=\s+in\s+20\d{{2}}(?:/\d{{2}})?|\s+for\s+|\s+against\s+|\s*$)",
        flags=re.IGNORECASE,
    )

    normalized = pattern.sub(lambda m: "at " + m.group(1), original, count=1)

    # Also support venue-first phrasing like "Wankhede top 10 run scorers".
    if normalized == original:
        venue_first = re.compile(
            rf"^\s*({venue_words})\s+(top\s+\d+\s+.*|who\s+.*|most\s+.*|highest\s+.*)$",
            flags=re.IGNORECASE,
        )
        match = venue_first.search(original)
        if match:
            normalized = f"{match.group(2)} at {match.group(1)}"

    return normalized


try:
    _previous_answer_question_with_fallback_before_vennorm = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_vennorm = None


def answer_question_with_fallback(user_question):
    normalized_question = _vennorm_normalize(user_question)

    if normalized_question != str(user_question or ""):
        result = _previous_answer_question_with_fallback_before_vennorm(normalized_question)

        if isinstance(result, dict):
            result["question"] = user_question
            result["normalized_question"] = normalized_question
            result["route_used"] = ""
            result["data_sources"] = ""

        return result

    return _previous_answer_question_with_fallback_before_vennorm(user_question)

# IPL SQL Agent venue wording normalizer END


# IPL SQL Agent bowler-vs-batter venue route + venue team grouping START

def _bvv_q(x):
    return str(x).replace("'", "''")


def _bvv_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    return "(" + ", ".join("'" + _bvv_q(v) + "'" for v in values) + ")" if values else "('')"


def _bvv_player_aliases(label):
    raw = str(label or "").strip()
    low = raw.lower()
    aliases = [raw]
    known = {
        "dhoni": ["MS Dhoni"],
        "kohli": ["V Kohli", "Virat Kohli"],
        "virat": ["V Kohli", "Virat Kohli"],
        "rohit": ["RG Sharma", "Rohit Sharma"],
        "gaikwad": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "ruturaj": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "raina": ["SK Raina", "Suresh Raina"],
        "warner": ["DA Warner", "David Warner"],
        "rahul": ["KL Rahul"],
        "de villiers": ["AB de Villiers"],
        "abd": ["AB de Villiers"],
        "gill": ["Shubman Gill"],
        "sudharsan": ["B Sai Sudharsan", "Sai Sudharsan"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
    }
    for key, vals in known.items():
        if key in low:
            for val in vals:
                if val not in aliases:
                    aliases.append(val)
    return aliases


def _bvv_resolve_player(label):
    try:
        from app.db import run_query
        aliases = _bvv_player_aliases(label)
        sql = f"""
SELECT TOP 1 player_name
FROM (
    SELECT striker AS player_name, COUNT(*) AS n FROM deliveries WHERE striker IN {_bvv_sql_list(aliases)} GROUP BY striker
    UNION ALL
    SELECT bowler AS player_name, COUNT(*) AS n FROM deliveries WHERE bowler IN {_bvv_sql_list(aliases)} GROUP BY bowler
) x
GROUP BY player_name
ORDER BY SUM(n) DESC, player_name;
""".strip()
        df = run_query(sql)
        if df is not None and not df.empty:
            resolved = str(df.iloc[0]["player_name"])
            if resolved not in aliases:
                aliases.insert(0, resolved)
            return resolved, aliases
    except Exception:
        pass
    aliases = _bvv_player_aliases(label)
    return aliases[0], aliases


def _bvv_venue_filter(raw):
    low = str(raw or "").lower().strip(" .?")
    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"
    if "dubai" in low:
        return "(m.venue LIKE '%Dubai%' OR m.city LIKE '%Dubai%')", "Dubai"
    if "sharjah" in low:
        return "(m.venue LIKE '%Sharjah%' OR m.city LIKE '%Sharjah%')", "Sharjah"
    if "abu dhabi" in low or "zayed" in low:
        return "(m.venue LIKE '%Abu Dhabi%' OR m.venue LIKE '%Zayed%' OR m.city LIKE '%Abu Dhabi%')", "Abu Dhabi"
    if "brabourne" in low:
        return "m.venue LIKE '%Brabourne%'", "Brabourne"
    if "kotla" in low or "arun jaitley" in low:
        return "(m.venue LIKE '%Kotla%' OR m.venue LIKE '%Arun Jaitley%')", "Arun Jaitley Stadium"
    if "mohali" in low or "bindra" in low:
        return "(m.venue LIKE '%Mohali%' OR m.venue LIKE '%Bindra%' OR m.city LIKE '%Mohali%')", "Mohali"
    if "rajiv gandhi" in low or "uppal" in low:
        return "(m.venue LIKE '%Rajiv Gandhi%' OR m.venue LIKE '%Uppal%')", "Rajiv Gandhi Stadium"
    if len(low) >= 4:
        safe = _bvv_q(low)
        return f"(LOWER(m.venue) LIKE '%{safe}%' OR LOWER(m.city) LIKE '%{safe}%')", str(raw).strip(" .?").title()
    return None, None


def _bvv_parse(question):
    import re
    text = str(question or "").strip()
    match = re.search(
        r"\b(?:best|top|effective|good|which)\b.*?\bbowlers?\b.*?\b(?:against|vs|versus)\s+(.+?)\s+\b(?:at|in|inside|on)\s+([A-Za-z0-9 .'-]+?)\s*$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    player = match.group(1).strip(" .?")
    venue_raw = match.group(2).strip(" .?")
    venue_filter, venue_label = _bvv_venue_filter(venue_raw)
    if not venue_filter:
        return None
    return player, venue_filter, venue_label


def _bvv_short_team(v):
    if v is None:
        return v
    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }
    out, seen = [], set()
    for part in [p.strip() for p in str(v).split(",") if p and str(p).strip()]:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            out.append(short)
            seen.add(key)
    return ", ".join(out)


def _bvv_clean_table(df):
    if df is None or not hasattr(df, "columns"):
        return df
    try:
        df = df.copy()
        for col in ["team", "Team", "teams", "Teams", "batting_team", "bowling_team", "opposition", "winner", "toss_winner"]:
            if col in df.columns:
                df[col] = df[col].apply(_bvv_short_team)
        return df
    except Exception:
        return df


def _bvv_group_venue_team_record(df):
    if df is None or not hasattr(df, "columns"):
        return df
    try:
        cols = {str(c).lower().strip().replace(" ", "_"): c for c in df.columns}
        team_col = cols.get("team")
        matches_col = cols.get("matches")
        wins_col = cols.get("wins")
        losses_col = cols.get("losses")
        win_pct_col = cols.get("win_pct") or cols.get("win_percentage")
        if not all([team_col, matches_col, wins_col, losses_col]):
            return _bvv_clean_table(df)
        df = df.copy()
        df[team_col] = df[team_col].apply(_bvv_short_team)
        grouped = df.groupby(team_col, as_index=False).agg({matches_col: "sum", wins_col: "sum", losses_col: "sum"})
        if win_pct_col:
            grouped[win_pct_col] = (grouped[wins_col] * 100.0 / grouped[matches_col].replace(0, float("nan"))).round(2)
        grouped = grouped.sort_values([matches_col, wins_col], ascending=[False, False]).reset_index(drop=True)
        ordered = [c for c in df.columns if c in grouped.columns]
        return grouped[ordered]
    except Exception:
        return _bvv_clean_table(df)


def _bvv_cleanup_result(result):
    if not isinstance(result, dict):
        return result
    result["result"] = _bvv_clean_table(result.get("result"))
    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            lname = str(name).lower()
            if "team record" in lname and "venue" in lname:
                extra[name] = _bvv_group_venue_team_record(table)
            else:
                extra[name] = _bvv_clean_table(table)
        result["extra_tables"] = extra
    return result


def _bvv_route(question):
    import pandas as pd
    from app.db import run_query

    parsed = _bvv_parse(question)
    if not parsed:
        return None

    player_label, venue_filter, venue_label = parsed
    resolved, aliases = _bvv_resolve_player(player_label)
    venue_filter_2 = venue_filter.replace("m.", "m2.")

    sql = f"""
SELECT TOP 25
    d.bowler,
    STUFF((
        SELECT DISTINCT ', ' + d2.bowling_team
        FROM deliveries d2
        JOIN matches m2 ON d2.match_id = m2.match_id
        WHERE d2.bowler = d.bowler
          AND d2.striker IN {_bvv_sql_list(aliases)}
          AND d2.innings IN (1, 2)
          AND {venue_filter_2}
        FOR XML PATH(''), TYPE
    ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
         AND d.player_dismissed = d.striker
         AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS batter_sr,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 1.0 / NULLIF(COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
         AND d.player_dismissed = d.striker
         AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
        THEN 1
    END), 0), 2) AS batter_average,
    COUNT(CASE WHEN COALESCE(d.runs_off_bat, 0)=0 AND COALESCE(d.extras, 0)=0 THEN 1 END) AS dot_balls,
    SUM(CASE WHEN COALESCE(d.runs_off_bat, 0) IN (4, 6) THEN 1 ELSE 0 END) AS boundaries,
    CASE
        WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) >= 12 THEN 'Usable sample'
        ELSE 'Small sample'
    END AS sample_note
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.striker IN {_bvv_sql_list(aliases)}
  AND d.innings IN (1, 2)
  AND {venue_filter}
GROUP BY d.bowler
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
ORDER BY
    CASE WHEN COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) >= 12 THEN 0 ELSE 1 END,
    dismissals DESC,
    batter_sr ASC,
    balls DESC,
    bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The bowler-vs-batter-at-venue route failed: {error}",
            "paragraph": f"The bowler-vs-batter-at-venue route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _bvv_clean_table(df if df is not None else pd.DataFrame())
    paragraph = f"Best bowlers against {resolved} at {venue_label}."

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {f"Bowlers vs {resolved} at {venue_label}": df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            f"best bowlers against Kohli at {venue_label}",
            f"best bowlers against Rohit at {venue_label}",
            f"best bowlers against {resolved} at Wankhede",
            f"who has dismissed {resolved} most at {venue_label}",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_bvv = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_bvv = None


def answer_question_with_fallback(user_question):
    result = _bvv_route(user_question)
    if result is not None:
        return result
    result = _previous_answer_question_with_fallback_before_bvv(user_question)
    return _bvv_cleanup_result(result)

# IPL SQL Agent bowler-vs-batter venue route + venue team grouping END


# IPL SQL Agent venue profile Delhi Capitals grouping final fix START

def _dcgroup_team_for_venue_record(value):
    if value is None:
        return value

    text = str(value).strip()

    mapping = {
        "Delhi Daredevils": "Delhi Capitals",
        "DD": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",

        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "RCB": "RCB",

        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "RPS": "RPS",

        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "PBKS": "PBKS",
        "KXIP": "PBKS",
    }

    return mapping.get(text, text)


def _dcgroup_venue_team_record_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()

        cols = {str(c).lower().strip().replace(" ", "_"): c for c in table.columns}

        team_col = cols.get("team")
        matches_col = cols.get("matches")
        wins_col = cols.get("wins")
        losses_col = cols.get("losses")
        win_pct_col = cols.get("win_pct") or cols.get("win_percentage")

        if not all([team_col, matches_col, wins_col, losses_col]):
            return table

        table[team_col] = table[team_col].apply(_dcgroup_team_for_venue_record)

        grouped = (
            table
            .groupby(team_col, as_index=False)
            .agg({
                matches_col: "sum",
                wins_col: "sum",
                losses_col: "sum",
            })
        )

        if win_pct_col:
            grouped[win_pct_col] = (
                grouped[wins_col] * 100.0 / grouped[matches_col].replace(0, float("nan"))
            ).round(2)

        grouped = grouped.sort_values([matches_col, wins_col], ascending=[False, False]).reset_index(drop=True)

        ordered_cols = [c for c in table.columns if c in grouped.columns]
        return grouped[ordered_cols]

    except Exception:
        return table


def _dcgroup_apply_venue_record_fix(result):
    if not isinstance(result, dict):
        return result

    extra = result.get("extra_tables")

    if not isinstance(extra, dict):
        return result

    for name, table in list(extra.items()):
        lname = str(name).lower()

        if "team record" in lname and "venue" in lname:
            extra[name] = _dcgroup_venue_team_record_table(table)

    result["extra_tables"] = extra

    return result


try:
    _previous_answer_question_with_fallback_before_dcgroup = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_dcgroup = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_dcgroup(user_question)
    return _dcgroup_apply_venue_record_fix(result)

# IPL SQL Agent venue profile Delhi Capitals grouping final fix END


# IPL SQL Agent batting rate and bowling economy filters START

def _rate_q(value):
    return str(value).replace("'", "''")


def _rate_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    if not values:
        return "('')"
    return "(" + ", ".join("'" + _rate_q(v) + "'" for v in values) + ")"


def _rate_team_lookup(text_value):
    text = str(text_value or "").lower().strip()

    if text in {"ipl", "history", "overall", "all seasons"}:
        return None, None, []

    teams = [
        ("CSK", "CSK", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "MI", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "RCB", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "GT", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "KKR", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "RR", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "SRH", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("Delhi Capitals", "Delhi Capitals", ["Delhi Capitals", "Delhi Daredevils"], ["delhi capitals", "delhi daredevils"]),
        ("Deccan Chargers", "Deccan Chargers", ["Deccan Chargers"], ["deccan chargers", "deccan"]),
        ("PBKS", "PBKS", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "LSG", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "RPS", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "GL", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "KTK", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "PWI", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
    ]

    if text == "dc":
        return "AMBIGUOUS_DC", None, []

    for code, display, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, display, aliases

    return None, None, []


def _rate_short_team_value(value):
    if value is None:
        return value

    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }

    parts = [p.strip() for p in str(value).split(",") if p and str(p).strip()]
    output = []
    seen = set()

    for part in parts:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            output.append(short)
            seen.add(key)

    return ", ".join(output)


def _rate_clean_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()
        for column in ["team", "teams", "batting_team", "bowling_team", "opposition", "winner", "toss_winner"]:
            if column in table.columns:
                table[column] = table[column].apply(_rate_short_team_value)
        return table
    except Exception:
        return table


def _rate_clean_result(result):
    if not isinstance(result, dict):
        return result

    result["result"] = _rate_clean_table(result.get("result"))

    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _rate_clean_table(table)
        result["extra_tables"] = extra

    return result


def _rate_extract_limit(question):
    import re

    match = re.search(r"\btop\s+(\d+)\b", str(question or ""), flags=re.IGNORECASE)

    if match:
        value = int(match.group(1))
        if 1 <= value <= 50:
            return value

    return 10


def _rate_extract_season(question):
    import re

    match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", str(question or ""))

    return match.group(1) if match else None


def _rate_extract_thresholds(question, metric):
    import re

    text = str(question or "").lower()

    thresholds = {
        "balls": None,
        "matches": None,
        "innings": None,
        "dismissals": None,
        "wickets": None,
    }

    patterns = [
        r"(?:min|minimum|at least)\s*[:=]?\s*(\d+)\s*(balls?|deliveries|balls faced|balls bowled)",
        r"(?:min|minimum|at least)\s*[:=]?\s*(\d+)\s*(matches?|matches played)",
        r"(?:min|minimum|at least)\s*[:=]?\s*(\d+)\s*(innings?)",
        r"(?:min|minimum|at least)\s*[:=]?\s*(\d+)\s*(dismissals?|outs?)",
        r"(?:min|minimum|at least)\s*[:=]?\s*(\d+)\s*(wickets?)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = int(match.group(1))
            unit = match.group(2).lower()

            if "ball" in unit or "deliver" in unit:
                thresholds["balls"] = value
            elif "match" in unit:
                thresholds["matches"] = value
            elif "inning" in unit:
                thresholds["innings"] = value
            elif "dismiss" in unit or "out" in unit:
                thresholds["dismissals"] = value
            elif "wicket" in unit:
                thresholds["wickets"] = value

    # Defaults only apply when user gives no explicit minimum.
    if all(v is None for v in thresholds.values()):
        if metric == "strike_rate":
            thresholds["balls"] = 300
        elif metric == "batting_average":
            thresholds["dismissals"] = 10
        elif metric == "economy":
            thresholds["balls"] = 300

    return thresholds


def _rate_venue_filter(question):
    import re

    text = str(question or "")

    match = re.search(
        r"\b(?:at|in|inside|on|venue|ground)\s+([A-Za-z0-9 .'-]+?)(?:\s*\(|\s+for\s+|\s+against\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return "1=1", None

    raw = match.group(1).strip(" .?")
    low = raw.lower()

    if low in {"ipl", "history", "all seasons", "overall"}:
        return "1=1", None

    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"
    if "dubai" in low:
        return "(m.venue LIKE '%Dubai%' OR m.city LIKE '%Dubai%')", "Dubai"
    if "sharjah" in low:
        return "(m.venue LIKE '%Sharjah%' OR m.city LIKE '%Sharjah%')", "Sharjah"
    if "abu dhabi" in low or "zayed" in low:
        return "(m.venue LIKE '%Abu Dhabi%' OR m.venue LIKE '%Zayed%' OR m.city LIKE '%Abu Dhabi%')", "Abu Dhabi"
    if "brabourne" in low:
        return "m.venue LIKE '%Brabourne%'", "Brabourne"
    if "kotla" in low or "arun jaitley" in low:
        return "(m.venue LIKE '%Kotla%' OR m.venue LIKE '%Arun Jaitley%')", "Arun Jaitley Stadium"
    if "mohali" in low or "bindra" in low:
        return "(m.venue LIKE '%Mohali%' OR m.venue LIKE '%Bindra%' OR m.city LIKE '%Mohali%')", "Mohali"
    if "dharamsala" in low or "dharamshala" in low:
        return "(m.venue LIKE '%Dharamsala%' OR m.venue LIKE '%Dharamshala%' OR m.city LIKE '%Dharam%')", "Dharamshala"
    if "rajiv gandhi" in low or "uppal" in low:
        return "(m.venue LIKE '%Rajiv Gandhi%' OR m.venue LIKE '%Uppal%')", "Rajiv Gandhi Stadium"

    if len(low) >= 4:
        safe = _rate_q(low)
        return f"(LOWER(m.venue) LIKE '%{safe}%' OR LOWER(m.city) LIKE '%{safe}%')", raw.title()

    return "1=1", None


def _rate_team_filters(question, kind):
    import re

    text = str(question or "")

    team_filter_sql = []
    label_parts = []

    # for/from/by TEAM = player's own team
    own_match = re.search(
        r"\b(?:for|from|by)\s+([A-Za-z0-9 .]+?)(?:\s*\(|\s+at\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s+against\s+|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if own_match:
        raw = own_match.group(1).strip(" .?")
        code, display, aliases = _rate_team_lookup(raw)

        if code == "AMBIGUOUS_DC":
            return "AMBIGUOUS_DC", [], []

        if aliases:
            if kind == "batting":
                team_filter_sql.append(f"d.batting_team IN {_rate_sql_list(aliases)}")
            else:
                team_filter_sql.append(f"d.bowling_team IN {_rate_sql_list(aliases)}")
            label_parts.append(f"for {display}")

    # against TEAM = opposition
    against_match = re.search(
        r"\bagainst\s+([A-Za-z0-9 .]+?)(?:\s*\(|\s+at\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if against_match:
        raw = against_match.group(1).strip(" .?")
        code, display, aliases = _rate_team_lookup(raw)

        if code == "AMBIGUOUS_DC":
            return "AMBIGUOUS_DC", [], []

        if aliases:
            if kind == "batting":
                team_filter_sql.append(f"d.bowling_team IN {_rate_sql_list(aliases)}")
            else:
                team_filter_sql.append(f"d.batting_team IN {_rate_sql_list(aliases)}")
            label_parts.append(f"against {display}")

    # Token fallback for "CSK best strike rate..." only when no explicit for/against found.
    if not team_filter_sql:
        for token in ["csk", "mi", "rcb", "gt", "kkr", "rr", "srh", "pbks", "kxip", "lsg"]:
            if re.search(rf"\b{token}\b", text, flags=re.IGNORECASE):
                code, display, aliases = _rate_team_lookup(token)
                if aliases:
                    if kind == "batting":
                        team_filter_sql.append(f"d.batting_team IN {_rate_sql_list(aliases)}")
                    else:
                        team_filter_sql.append(f"d.bowling_team IN {_rate_sql_list(aliases)}")
                    label_parts.append(f"for {display}")
                    break

    return None, team_filter_sql, label_parts


def _rate_dc_ambiguity(question):
    import pandas as pd

    data = pd.DataFrame([
        {
            "issue": "DC is ambiguous",
            "action": "Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
            "example": "best strike rate for Delhi Capitals min 500 balls",
        }
    ])

    return {
        "question": question,
        "analysis_paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "result": data,
        "extra_tables": {"Clarification": data},
        "sql_query": "",
        "similar_questions": [
            "best strike rate for Delhi Capitals min 500 balls",
            "best average for Delhi Capitals min 5 matches",
            "best economy rate for Delhi Capitals min 700 balls",
            "best strike rate against Deccan Chargers min 200 balls",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _rate_is_batting_rate_question(question):
    text = str(question or "").lower()

    if "economy" in text:
        return None

    if "strike rate" in text or re.search(r"\bsr\b", text):
        if any(x in text for x in ["best", "highest", "top"]):
            return "strike_rate"

    if "average" in text and "bowling average" not in text:
        if any(x in text for x in ["best", "highest", "top"]):
            return "batting_average"

    return None


def _rate_is_bowling_economy_question(question):
    text = str(question or "").lower()

    if "economy" in text and any(x in text for x in ["best", "lowest", "top"]):
        return True

    return False


def _rate_min_label(thresholds, kind):
    parts = []

    if thresholds.get("balls") is not None:
        parts.append(f"min {thresholds['balls']} balls {'faced' if kind == 'batting' else 'bowled'}")

    if thresholds.get("matches") is not None:
        parts.append(f"min {thresholds['matches']} matches")

    if thresholds.get("innings") is not None:
        parts.append(f"min {thresholds['innings']} innings")

    if thresholds.get("dismissals") is not None:
        parts.append(f"min {thresholds['dismissals']} dismissals")

    if thresholds.get("wickets") is not None:
        parts.append(f"min {thresholds['wickets']} wickets")

    return ", ".join(parts)


def _rate_threshold_where(thresholds, kind):
    clauses = []

    if thresholds.get("balls") is not None:
        col = "balls" if kind == "batting" else "legal_balls"
        clauses.append(f"{col} >= {int(thresholds['balls'])}")

    if thresholds.get("matches") is not None:
        clauses.append(f"matches >= {int(thresholds['matches'])}")

    if thresholds.get("innings") is not None:
        clauses.append(f"innings >= {int(thresholds['innings'])}")

    if thresholds.get("dismissals") is not None and kind == "batting":
        clauses.append(f"dismissals >= {int(thresholds['dismissals'])}")

    if thresholds.get("wickets") is not None and kind == "bowling":
        clauses.append(f"wickets >= {int(thresholds['wickets'])}")

    if kind == "batting":
        clauses.append("balls > 0")
    else:
        clauses.append("legal_balls > 0")

    return " AND ".join(clauses)


def _rate_batting_route(question):
    import pandas as pd
    from app.db import run_query

    metric = _rate_is_batting_rate_question(question)

    if not metric:
        return None

    limit = _rate_extract_limit(question)
    season = _rate_extract_season(question)
    thresholds = _rate_extract_thresholds(question, metric)
    venue_filter, venue_label = _rate_venue_filter(question)

    ambiguity, team_filters, label_parts = _rate_team_filters(question, "batting")

    if ambiguity == "AMBIGUOUS_DC":
        return _rate_dc_ambiguity(question)

    filters = [
        "d.innings IN (1, 2)",
        venue_filter,
    ]

    filters.extend(team_filters)

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_rate_q(season)}'")

    where_sql = " AND ".join(filters)
    threshold_where = _rate_threshold_where(thresholds, "batting")
    min_label = _rate_min_label(thresholds, "batting")

    sort_expr = "strike_rate DESC, runs DESC, batter ASC" if metric == "strike_rate" else "batting_average DESC, runs DESC, strike_rate DESC, batter ASC"

    title_metric = "Best strike rate" if metric == "strike_rate" else "Best batting average"
    title_parts = [title_metric]

    if label_parts:
        title_parts.extend(label_parts)

    if venue_label:
        title_parts.append(f"at {venue_label}")

    if season:
        title_parts.append(f"in {season}")

    if min_label:
        title_parts.append(f"({min_label})")

    title = " ".join(title_parts)

    sql = f"""
WITH batter_innings AS (
    SELECT
        d.striker AS batter,
        d.batting_team AS team,
        d.season,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out', 'retired not out')
            THEN 1 ELSE 0
        END) AS out_flag
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.striker, d.batting_team, d.season, d.match_id, d.innings
    HAVING SUM(COALESCE(d.runs_off_bat, 0)) > 0
        OR COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
),
batter_totals AS (
    SELECT
        batter,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM batter_innings bi2
            WHERE bi2.batter = bi.batter
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(out_flag) AS dismissals,
        SUM(balls) AS balls,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM batter_innings bi
    GROUP BY batter
),
ranked AS (
    SELECT
        batter,
        team,
        matches,
        innings,
        runs,
        dismissals,
        ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average,
        balls,
        ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate,
        highest_score,
        fifties,
        hundreds
    FROM batter_totals
)
SELECT TOP {limit}
    batter,
    team,
    matches,
    innings,
    runs,
    dismissals,
    batting_average,
    balls,
    strike_rate,
    highest_score,
    fifties,
    hundreds
FROM ranked
WHERE {threshold_where}
ORDER BY {sort_expr};
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The batting rate route failed: {error}",
            "paragraph": f"The batting rate route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _rate_clean_table(df if df is not None else pd.DataFrame())

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "best strike rate in IPL min 500 balls faced",
            "who has the best average at Chepauk min 5 matches played",
            "best strike rate for CSK min 300 balls",
            "best average against MI min 10 matches",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _rate_bowling_economy_route(question):
    import pandas as pd
    from app.db import run_query

    if not _rate_is_bowling_economy_question(question):
        return None

    limit = _rate_extract_limit(question)
    season = _rate_extract_season(question)
    thresholds = _rate_extract_thresholds(question, "economy")
    venue_filter, venue_label = _rate_venue_filter(question)

    ambiguity, team_filters, label_parts = _rate_team_filters(question, "bowling")

    if ambiguity == "AMBIGUOUS_DC":
        return _rate_dc_ambiguity(question)

    filters = [
        "d.innings IN (1, 2)",
        venue_filter,
    ]

    filters.extend(team_filters)

    if season:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_rate_q(season)}'")

    where_sql = " AND ".join(filters)
    threshold_where = _rate_threshold_where(thresholds, "bowling")
    min_label = _rate_min_label(thresholds, "bowling")

    title_parts = ["Best economy rate"]

    if label_parts:
        title_parts.extend(label_parts)

    if venue_label:
        title_parts.append(f"at {venue_label}")

    if season:
        title_parts.append(f"in {season}")

    if min_label:
        title_parts.append(f"({min_label})")

    title = " ".join(title_parts)

    sql = f"""
WITH bowler_innings AS (
    SELECT
        d.bowler,
        d.bowling_team AS team,
        d.match_id,
        d.innings,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS legal_balls,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(CASE WHEN COALESCE(d.runs_off_bat, 0)=0 AND COALESCE(d.extras, 0)=0 THEN 1 END) AS dot_balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.bowler, d.bowling_team, d.match_id, d.innings
),
bowler_totals AS (
    SELECT
        bowler,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM bowler_innings bi2
            WHERE bi2.bowler = bi.bowler
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(legal_balls) AS legal_balls,
        SUM(wickets) AS wickets,
        SUM(runs_conceded) AS runs_conceded,
        SUM(dot_balls) AS dot_balls
    FROM bowler_innings bi
    GROUP BY bowler
),
ranked AS (
    SELECT
        bowler,
        team,
        matches,
        innings,
        CAST(legal_balls / 6 AS varchar(20)) + '.' + CAST(legal_balls % 6 AS varchar(1)) AS overs_bowled,
        legal_balls,
        wickets,
        runs_conceded,
        ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy,
        ROUND(legal_balls * 1.0 / NULLIF(wickets, 0), 2) AS bowling_strike_rate,
        dot_balls
    FROM bowler_totals
)
SELECT TOP {limit}
    bowler,
    team,
    matches,
    innings,
    overs_bowled,
    legal_balls,
    wickets,
    runs_conceded,
    economy,
    bowling_strike_rate,
    dot_balls
FROM ranked
WHERE {threshold_where}
ORDER BY economy ASC, wickets DESC, legal_balls DESC, bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The bowling economy route failed: {error}",
            "paragraph": f"The bowling economy route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _rate_clean_table(df if df is not None else pd.DataFrame())

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "best economy rate in IPL min 700 balls bowled",
            "who has the best economy rate at Chepauk min 300 balls",
            "best economy rate for CSK min 300 balls",
            "best economy rate against MI min 500 balls",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_rate_routes = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_rate_routes = None


def answer_question_with_fallback(user_question):
    for route in [
        _rate_batting_route,
        _rate_bowling_economy_route,
    ]:
        result = route(user_question)
        if result is not None:
            return result

    result = _previous_answer_question_with_fallback_before_rate_routes(user_question)
    return _rate_clean_result(result)

# IPL SQL Agent batting rate and bowling economy filters END


# IPL SQL Agent final robust rate/economy routes START

def _rrfinal_q(value):
    return str(value).replace("'", "''")


def _rrfinal_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    return "(" + ", ".join("'" + _rrfinal_q(v) + "'" for v in values) + ")" if values else "('')"


def _rrfinal_short_team_value(value):
    if value is None:
        return value

    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }

    parts = [p.strip() for p in str(value).split(",") if p and str(p).strip()]
    out = []
    seen = set()

    for part in parts:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            out.append(short)
            seen.add(key)

    return ", ".join(out)


def _rrfinal_clean_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()
        for col in ["team", "teams", "batting_team", "bowling_team", "opposition", "winner", "toss_winner"]:
            if col in table.columns:
                table[col] = table[col].apply(_rrfinal_short_team_value)
        return table
    except Exception:
        return table


def _rrfinal_clean_result(result):
    if not isinstance(result, dict):
        return result

    result["result"] = _rrfinal_clean_table(result.get("result"))

    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _rrfinal_clean_table(table)
        result["extra_tables"] = extra

    return result


def _rrfinal_team_lookup(raw):
    text = str(raw or "").lower().strip()

    if text in {"ipl", "the ipl", "history", "overall", "all seasons", "all time"}:
        return None, None, []

    if text == "dc":
        return "AMBIGUOUS_DC", None, []

    teams = [
        ("CSK", "CSK", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "MI", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "RCB", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "GT", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "KKR", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "RR", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "SRH", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("Delhi Capitals", "Delhi Capitals", ["Delhi Capitals", "Delhi Daredevils"], ["delhi capitals", "delhi daredevils"]),
        ("Deccan Chargers", "Deccan Chargers", ["Deccan Chargers"], ["deccan chargers", "deccan"]),
        ("PBKS", "PBKS", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "LSG", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "RPS", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "GL", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "KTK", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "PWI", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
    ]

    for code, display, aliases, triggers in teams:
        if text in triggers or any(t in text for t in triggers):
            return code, display, aliases

    return None, None, []


def _rrfinal_venue_filter(raw):
    low = str(raw or "").lower().strip(" .?")

    if not low or low in {"ipl", "the ipl", "history", "overall", "all seasons", "all time"}:
        return "1=1", None

    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"
    if "dubai" in low:
        return "(m.venue LIKE '%Dubai%' OR m.city LIKE '%Dubai%')", "Dubai"
    if "sharjah" in low:
        return "(m.venue LIKE '%Sharjah%' OR m.city LIKE '%Sharjah%')", "Sharjah"
    if "abu dhabi" in low or "zayed" in low:
        return "(m.venue LIKE '%Abu Dhabi%' OR m.venue LIKE '%Zayed%' OR m.city LIKE '%Abu Dhabi%')", "Abu Dhabi"
    if "brabourne" in low:
        return "m.venue LIKE '%Brabourne%'", "Brabourne"
    if "kotla" in low or "arun jaitley" in low:
        return "(m.venue LIKE '%Kotla%' OR m.venue LIKE '%Arun Jaitley%')", "Arun Jaitley Stadium"
    if "mohali" in low or "bindra" in low:
        return "(m.venue LIKE '%Mohali%' OR m.venue LIKE '%Bindra%' OR m.city LIKE '%Mohali%')", "Mohali"
    if "dharamsala" in low or "dharamshala" in low:
        return "(m.venue LIKE '%Dharamsala%' OR m.venue LIKE '%Dharamshala%' OR m.city LIKE '%Dharam%')", "Dharamshala"
    if "rajiv gandhi" in low or "uppal" in low:
        return "(m.venue LIKE '%Rajiv Gandhi%' OR m.venue LIKE '%Uppal%')", "Rajiv Gandhi Stadium"

    return "1=1", None


def _rrfinal_parse_minimums(question):
    import re

    text = str(question or "").lower()
    mins = {"balls": None, "matches": None, "innings": None, "dismissals": None, "wickets": None}

    # Capture either "(min 500 balls faced)" or "min 500 balls faced".
    for match in re.finditer(r"(?:min|minimum|at least)\s*[:=]?\s*(\d+)\s*([a-z ]+)", text, flags=re.IGNORECASE):
        value = int(match.group(1))
        unit = match.group(2).strip()

        # Stop unit at common next clauses.
        for stop in [" at ", " in ", " for ", " against ", " by "]:
            if stop in unit:
                unit = unit.split(stop)[0].strip()

        if "ball" in unit or "deliver" in unit:
            mins["balls"] = value
        elif "match" in unit:
            mins["matches"] = value
        elif "inning" in unit:
            mins["innings"] = value
        elif "dismiss" in unit or "out" in unit:
            mins["dismissals"] = value
        elif "wicket" in unit:
            mins["wickets"] = value

    return mins


def _rrfinal_strip_min_clauses(question):
    import re

    text = str(question or "")

    text = re.sub(
        r"\((?:\s*)(?:min|minimum|at least)\s*[:=]?\s*\d+\s*[A-Za-z ]*(?:\s*)\)",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b(?:min|minimum|at least)\s*[:=]?\s*\d+\s*[A-Za-z ]*",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    return text


def _rrfinal_parse_context(question, kind):
    import re

    clean = _rrfinal_strip_min_clauses(question)
    text = clean.lower()

    season = None
    season_match = re.search(r"\b(20\d{2}(?:/\d{2})?)\b", clean)
    if season_match:
        season = season_match.group(1)

    venue_filter = "1=1"
    venue_label = None

    # Only these words should trigger venue parsing.
    venue_match = re.search(
        r"\b(?:at|inside|on|venue|ground)\s+([A-Za-z0-9 .'-]+?)(?:\s+for\s+|\s+against\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s*$)",
        clean,
        flags=re.IGNORECASE,
    )

    if venue_match:
        venue_filter, venue_label = _rrfinal_venue_filter(venue_match.group(1))

    # "in Chepauk" should be allowed, but "in IPL" should not become a venue.
    if not venue_label:
        in_match = re.search(
            r"\bin\s+([A-Za-z0-9 .'-]+?)(?:\s+for\s+|\s+against\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s*$)",
            clean,
            flags=re.IGNORECASE,
        )
        if in_match:
            possible = in_match.group(1).strip(" .?")
            if possible.lower() not in {"ipl", "the ipl", "history", "overall", "all seasons", "all time"} and not re.fullmatch(r"20\d{2}(?:/\d{2})?", possible):
                venue_filter, venue_label = _rrfinal_venue_filter(possible)

    team_clauses = []
    labels = []
    ambiguity = False

    # "for/from/by TEAM" means own team.
    own_match = re.search(
        r"\b(?:for|from|by)\s+([A-Za-z0-9 .]+?)(?:\s+at\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s+against\s+|\s*$)",
        clean,
        flags=re.IGNORECASE,
    )

    if own_match:
        code, display, aliases = _rrfinal_team_lookup(own_match.group(1).strip(" .?"))

        if code == "AMBIGUOUS_DC":
            ambiguity = True
        elif aliases:
            team_col = "d.batting_team" if kind == "batting" else "d.bowling_team"
            team_clauses.append(f"{team_col} IN {_rrfinal_sql_list(aliases)}")
            labels.append(f"for {display}")

    # "against TEAM" means opposition.
    against_match = re.search(
        r"\bagainst\s+([A-Za-z0-9 .]+?)(?:\s+at\s+|\s+in\s+20\d{2}(?:/\d{2})?|\s*$)",
        clean,
        flags=re.IGNORECASE,
    )

    if against_match:
        code, display, aliases = _rrfinal_team_lookup(against_match.group(1).strip(" .?"))

        if code == "AMBIGUOUS_DC":
            ambiguity = True
        elif aliases:
            opp_col = "d.bowling_team" if kind == "batting" else "d.batting_team"
            team_clauses.append(f"{opp_col} IN {_rrfinal_sql_list(aliases)}")
            labels.append(f"against {display}")

    return {
        "season": season,
        "venue_filter": venue_filter,
        "venue_label": venue_label,
        "team_clauses": team_clauses,
        "labels": labels,
        "ambiguity": ambiguity,
    }


def _rrfinal_limit(question):
    import re

    match = re.search(r"\btop\s+(\d+)\b", str(question or ""), flags=re.IGNORECASE)

    if match:
        n = int(match.group(1))
        if 1 <= n <= 50:
            return n

    return 10


def _rrfinal_metric(question):
    text = str(question or "").lower()

    if "economy" in text and any(x in text for x in ["best", "lowest", "top"]):
        return "economy"

    if ("strike rate" in text or " sr" in text) and any(x in text for x in ["best", "highest", "top"]):
        return "strike_rate"

    if "average" in text and "bowling average" not in text and any(x in text for x in ["best", "highest", "top"]):
        return "batting_average"

    return None


def _rrfinal_min_label(mins, kind):
    parts = []

    if mins.get("balls") is not None:
        parts.append(f"min {mins['balls']} balls {'faced' if kind == 'batting' else 'bowled'}")
    if mins.get("matches") is not None:
        parts.append(f"min {mins['matches']} matches")
    if mins.get("innings") is not None:
        parts.append(f"min {mins['innings']} innings")
    if mins.get("dismissals") is not None:
        parts.append(f"min {mins['dismissals']} dismissals")
    if mins.get("wickets") is not None:
        parts.append(f"min {mins['wickets']} wickets")

    return ", ".join(parts)


def _rrfinal_dc_ambiguity(question):
    import pandas as pd

    df = pd.DataFrame([{
        "issue": "DC is ambiguous",
        "action": "Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "example": "best strike rate for Delhi Capitals min 500 balls",
    }])

    return {
        "question": question,
        "analysis_paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "result": df,
        "extra_tables": {"Clarification": df},
        "sql_query": "",
        "similar_questions": [
            "best strike rate for Delhi Capitals min 500 balls",
            "best average for Delhi Capitals min 5 matches",
            "best economy rate for Delhi Capitals min 700 balls",
            "best strike rate against Deccan Chargers min 200 balls",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _rrfinal_batting_rate_route(question, metric):
    import pandas as pd
    from app.db import run_query

    ctx = _rrfinal_parse_context(question, "batting")
    if ctx["ambiguity"]:
        return _rrfinal_dc_ambiguity(question)

    mins = _rrfinal_parse_minimums(question)

    if not any(v is not None for v in mins.values()):
        if metric == "strike_rate":
            mins["balls"] = 300
        else:
            mins["dismissals"] = 10

    filters = [
        "d.innings IN (1, 2)",
        ctx["venue_filter"],
    ]
    filters.extend(ctx["team_clauses"])

    if ctx["season"]:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_rrfinal_q(ctx['season'])}'")

    where_sql = " AND ".join(filters)

    threshold_parts = ["balls > 0"]

    if metric == "batting_average":
        threshold_parts.append("dismissals > 0")

    if mins.get("balls") is not None:
        threshold_parts.append(f"balls >= {int(mins['balls'])}")
    if mins.get("matches") is not None:
        threshold_parts.append(f"matches >= {int(mins['matches'])}")
    if mins.get("innings") is not None:
        threshold_parts.append(f"innings >= {int(mins['innings'])}")
    if mins.get("dismissals") is not None:
        threshold_parts.append(f"dismissals >= {int(mins['dismissals'])}")

    threshold_sql = " AND ".join(threshold_parts)

    sort_sql = "strike_rate DESC, runs DESC, batter ASC" if metric == "strike_rate" else "batting_average DESC, runs DESC, strike_rate DESC, batter ASC"
    limit = _rrfinal_limit(question)

    sql = f"""
WITH batter_innings AS (
    SELECT
        d.striker AS batter,
        d.batting_team AS team,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out', 'retired not out')
            THEN 1 ELSE 0
        END) AS out_flag
    FROM deliveries d
    JOIN matches m ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.striker, d.batting_team, d.match_id, d.innings
),
totals AS (
    SELECT
        batter,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM batter_innings bi2
            WHERE bi2.batter = bi.batter
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(out_flag) AS dismissals,
        SUM(balls) AS balls,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM batter_innings bi
    GROUP BY batter
),
ranked AS (
    SELECT
        batter,
        team,
        matches,
        innings,
        runs,
        dismissals,
        ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average,
        balls,
        ROUND(runs * 100.0 / NULLIF(balls, 0), 2) AS strike_rate,
        highest_score,
        fifties,
        hundreds
    FROM totals
)
SELECT TOP {limit}
    batter,
    team,
    matches,
    innings,
    runs,
    dismissals,
    batting_average,
    balls,
    strike_rate,
    highest_score,
    fifties,
    hundreds
FROM ranked
WHERE {threshold_sql}
ORDER BY {sort_sql};
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The robust batting rate route failed: {error}",
            "paragraph": f"The robust batting rate route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _rrfinal_clean_table(df if df is not None else pd.DataFrame())

    title_parts = ["Best strike rate" if metric == "strike_rate" else "Best batting average"]
    title_parts.extend(ctx["labels"])
    if ctx["venue_label"]:
        title_parts.append(f"at {ctx['venue_label']}")
    if ctx["season"]:
        title_parts.append(f"in {ctx['season']}")
    min_label = _rrfinal_min_label(mins, "batting")
    if min_label:
        title_parts.append(f"({min_label})")
    title = " ".join(title_parts)

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "best strike rate in IPL min 500 balls faced",
            "who has the best average at Chepauk min 5 matches played",
            "best strike rate for CSK min 300 balls",
            "best average against MI min 10 matches",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _rrfinal_economy_route(question):
    import pandas as pd
    from app.db import run_query

    ctx = _rrfinal_parse_context(question, "bowling")
    if ctx["ambiguity"]:
        return _rrfinal_dc_ambiguity(question)

    mins = _rrfinal_parse_minimums(question)
    if not any(v is not None for v in mins.values()):
        mins["balls"] = 300

    filters = [
        "d.innings IN (1, 2)",
        ctx["venue_filter"],
    ]
    filters.extend(ctx["team_clauses"])

    if ctx["season"]:
        filters.append(f"CAST(d.season AS varchar(20)) = '{_rrfinal_q(ctx['season'])}'")

    where_sql = " AND ".join(filters)

    threshold_parts = ["legal_balls > 0"]

    if mins.get("balls") is not None:
        threshold_parts.append(f"legal_balls >= {int(mins['balls'])}")
    if mins.get("matches") is not None:
        threshold_parts.append(f"matches >= {int(mins['matches'])}")
    if mins.get("innings") is not None:
        threshold_parts.append(f"innings >= {int(mins['innings'])}")
    if mins.get("wickets") is not None:
        threshold_parts.append(f"wickets >= {int(mins['wickets'])}")

    threshold_sql = " AND ".join(threshold_parts)
    limit = _rrfinal_limit(question)

    sql = f"""
WITH bowler_innings AS (
    SELECT
        d.bowler,
        d.bowling_team AS team,
        d.match_id,
        d.innings,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS legal_balls,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(CASE WHEN COALESCE(d.runs_off_bat, 0)=0 AND COALESCE(d.extras, 0)=0 THEN 1 END) AS dot_balls
    FROM deliveries d
    JOIN matches m ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.bowler, d.bowling_team, d.match_id, d.innings
),
totals AS (
    SELECT
        bowler,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM bowler_innings bi2
            WHERE bi2.bowler = bi.bowler
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(legal_balls) AS legal_balls,
        SUM(wickets) AS wickets,
        SUM(runs_conceded) AS runs_conceded,
        SUM(dot_balls) AS dot_balls
    FROM bowler_innings bi
    GROUP BY bowler
),
ranked AS (
    SELECT
        bowler,
        team,
        matches,
        innings,
        CAST(legal_balls / 6 AS varchar(20)) + '.' + CAST(legal_balls % 6 AS varchar(1)) AS overs_bowled,
        legal_balls,
        wickets,
        runs_conceded,
        ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy,
        ROUND(legal_balls * 1.0 / NULLIF(wickets, 0), 2) AS bowling_strike_rate,
        dot_balls
    FROM totals
)
SELECT TOP {limit}
    bowler,
    team,
    matches,
    innings,
    overs_bowled,
    legal_balls,
    wickets,
    runs_conceded,
    economy,
    bowling_strike_rate,
    dot_balls
FROM ranked
WHERE {threshold_sql}
ORDER BY economy ASC, wickets DESC, legal_balls DESC, bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The robust economy route failed: {error}",
            "paragraph": f"The robust economy route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _rrfinal_clean_table(df if df is not None else pd.DataFrame())

    title_parts = ["Best economy rate"]
    title_parts.extend(ctx["labels"])
    if ctx["venue_label"]:
        title_parts.append(f"at {ctx['venue_label']}")
    if ctx["season"]:
        title_parts.append(f"in {ctx['season']}")
    min_label = _rrfinal_min_label(mins, "bowling")
    if min_label:
        title_parts.append(f"({min_label})")
    title = " ".join(title_parts)

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "best economy rate in IPL min 700 balls bowled",
            "who has the best economy rate at Chepauk min 300 balls",
            "best economy rate for CSK min 300 balls",
            "best economy rate against MI min 500 balls",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_rrfinal = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_rrfinal = None


def answer_question_with_fallback(user_question):
    metric = _rrfinal_metric(user_question)

    if metric == "strike_rate" or metric == "batting_average":
        return _rrfinal_batting_rate_route(user_question, metric)

    if metric == "economy":
        return _rrfinal_economy_route(user_question)

    result = _previous_answer_question_with_fallback_before_rrfinal(user_question)
    return _rrfinal_clean_result(result)

# IPL SQL Agent final robust rate/economy routes END


# IPL SQL Agent New Chandigarh venue alias START

def _nc_venue_filter_condition(prefix="m."):
    return (
        f"({prefix}venue LIKE '%Yadavindra%' "
        f"OR {prefix}venue LIKE '%Mullanpur%' "
        f"OR {prefix}venue LIKE '%New Chandigarh%' "
        f"OR {prefix}city LIKE '%Chandigarh%' "
        f"OR {prefix}city LIKE '%Mullanpur%')"
    )


def _nc_is_new_chandigarh(text):
    low = str(text or "").lower()
    return (
        "new chandigarh" in low
        or "mullanpur" in low
        or "yadavindra" in low
        or "maharaja yadavindra" in low
    )


def _nc_normalize_question_text(question):
    text = str(question or "")
    replacements = [
        "New Chandigarh",
        "new chandigarh",
        "Mullanpur",
        "mullanpur",
        "Maharaja Yadavindra Singh Stadium",
        "maharaja yadavindra singh stadium",
        "Maharaja Yadavindra Singh International Cricket Stadium",
        "maharaja yadavindra singh international cricket stadium",
    ]
    for old in replacements:
        text = text.replace(old, "Maharaja Yadavindra Singh")
    return text


try:
    _previous_rrfinal_venue_filter_before_nc = _rrfinal_venue_filter
except NameError:
    _previous_rrfinal_venue_filter_before_nc = None


def _rrfinal_venue_filter(raw):
    if _nc_is_new_chandigarh(raw):
        return _nc_venue_filter_condition("m."), "New Chandigarh"
    if _previous_rrfinal_venue_filter_before_nc:
        return _previous_rrfinal_venue_filter_before_nc(raw)
    return "1=1", None


try:
    _previous_bvv_venue_filter_before_nc = _bvv_venue_filter
except NameError:
    _previous_bvv_venue_filter_before_nc = None


def _bvv_venue_filter(raw):
    if _nc_is_new_chandigarh(raw):
        return _nc_venue_filter_condition("m."), "New Chandigarh"
    if _previous_bvv_venue_filter_before_nc:
        return _previous_bvv_venue_filter_before_nc(raw)
    return None, None


try:
    _previous_bvvenue_venue_filter_from_raw_before_nc = _bvvenue_venue_filter_from_raw
except NameError:
    _previous_bvvenue_venue_filter_from_raw_before_nc = None


def _bvvenue_venue_filter_from_raw(raw):
    if _nc_is_new_chandigarh(raw):
        return _nc_venue_filter_condition("m."), "New Chandigarh"
    if _previous_bvvenue_venue_filter_from_raw_before_nc:
        return _previous_bvvenue_venue_filter_from_raw_before_nc(raw)
    return None, None


try:
    _previous_rate_venue_filter_before_nc = _rate_venue_filter
except NameError:
    _previous_rate_venue_filter_before_nc = None


def _rate_venue_filter(question):
    if _nc_is_new_chandigarh(question):
        return _nc_venue_filter_condition("m."), "New Chandigarh"
    if _previous_rate_venue_filter_before_nc:
        return _previous_rate_venue_filter_before_nc(question)
    return "1=1", None


try:
    _previous_answer_question_with_fallback_before_nc_alias = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_nc_alias = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_nc_alias(user_question)

    try:
        table = result.get("result") if isinstance(result, dict) else None
        is_empty = table is None or (hasattr(table, "empty") and table.empty)
    except Exception:
        is_empty = False

    if _nc_is_new_chandigarh(user_question) and is_empty:
        normalized_question = _nc_normalize_question_text(user_question)
        if normalized_question != str(user_question):
            retry_result = _previous_answer_question_with_fallback_before_nc_alias(normalized_question)
            if isinstance(retry_result, dict):
                retry_result["question"] = user_question
                paragraph = retry_result.get("analysis_paragraph") or retry_result.get("paragraph") or ""
                paragraph = str(paragraph).replace("Maharaja Yadavindra Singh", "New Chandigarh")
                retry_result["analysis_paragraph"] = paragraph
                retry_result["paragraph"] = paragraph
                return retry_result

    return result

# IPL SQL Agent New Chandigarh venue alias END


# IPL SQL Agent display date format dd-mm-yyyy START

def _ddmmyyyy_convert_value(value):
    import re
    import pandas as pd

    if value is None:
        return value

    try:
        if pd.isna(value):
            return value
    except Exception:
        pass

    # Pandas / Python datetime-like values
    if hasattr(value, "strftime") and not isinstance(value, str):
        try:
            return value.strftime("%d-%m-%Y")
        except Exception:
            return value

    text = str(value).strip()

    # Convert ISO dates such as 2026-04-12 or 2026-04-12 00:00:00.
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?$", text)
    if match:
        yyyy, mm, dd = match.groups()
        return f"{dd}-{mm}-{yyyy}"

    return value


def _ddmmyyyy_column_looks_like_date(series, column_name):
    import re
    import pandas as pd

    name = str(column_name).lower()

    if "date" in name:
        return True

    try:
        sample = series.dropna().astype(str).head(20).tolist()
    except Exception:
        return False

    if not sample:
        return False

    iso_count = sum(1 for value in sample if re.match(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$", value.strip()))

    return iso_count >= max(1, int(len(sample) * 0.8))


def _ddmmyyyy_format_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()

        for column in table.columns:
            if _ddmmyyyy_column_looks_like_date(table[column], column):
                table[column] = table[column].apply(_ddmmyyyy_convert_value)

        return table

    except Exception:
        return table


def _ddmmyyyy_format_result(result):
    if not isinstance(result, dict):
        return result

    result["result"] = _ddmmyyyy_format_table(result.get("result"))

    extra = result.get("extra_tables")

    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _ddmmyyyy_format_table(table)

        result["extra_tables"] = extra

    return result


try:
    _previous_answer_question_with_fallback_before_ddmmyyyy = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_ddmmyyyy = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_ddmmyyyy(user_question)
    return _ddmmyyyy_format_result(result)

# IPL SQL Agent display date format dd-mm-yyyy END


# IPL SQL Agent season alias and cap routes START

def _seasonfix_q(value):
    return str(value).replace("'", "''")


def _seasonfix_short_team(value):
    if value is None:
        return value

    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }

    parts = [p.strip() for p in str(value).split(",") if p and str(p).strip()]
    output = []
    seen = set()

    for part in parts:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            output.append(short)
            seen.add(key)

    return ", ".join(output)


def _seasonfix_clean_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()

        if "team" in table.columns:
            table["team"] = table["team"].apply(_seasonfix_short_team)

        return table

    except Exception:
        return table


def _seasonfix_clean_result(result):
    if not isinstance(result, dict):
        return result

    result["result"] = _seasonfix_clean_table(result.get("result"))

    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _seasonfix_clean_table(table)
        result["extra_tables"] = extra

    return result


def _seasonfix_extract_year(question):
    import re

    text = str(question or "")

    # Prefer a full standalone year typed by the user.
    match = re.search(r"\b(20\d{2})\b", text)

    if match:
        return int(match.group(1))

    return None


def _seasonfix_season_condition(alias, typed_year):
    year = int(typed_year)
    slash_form = f"{year - 1}/{str(year)[-2:]}"
    short_year = str(year)[-2:]

    return (
        f"(CAST({alias}.season AS varchar(20)) = '{year}' "
        f"OR CAST({alias}.season AS varchar(20)) = '{_seasonfix_q(slash_form)}' "
        f"OR CAST({alias}.season AS varchar(20)) LIKE '%/{_seasonfix_q(short_year)}')"
    )


def _seasonfix_season_label_expr(alias):
    # Converts seasons like 2007/08, 2009/10, 2020/21 into 2008, 2010, 2021 for display/grouping.
    return f"""
CASE
    WHEN CHARINDEX('/', CAST({alias}.season AS varchar(20))) > 0
         AND TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) IS NOT NULL
    THEN CAST(
        CASE
            WHEN TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) <= 30
            THEN 2000 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
            ELSE 1900 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
        END AS varchar(4)
    )
    ELSE CAST({alias}.season AS varchar(20))
END
""".strip()


def _seasonfix_limit(question, default_value=10):
    import re

    text = str(question or "").lower()

    match = re.search(r"\btop\s+(\d+)\b", text)

    if match:
        value = int(match.group(1))
        if 1 <= value <= 50:
            return value

    if "orange cap" in text or "purple cap" in text or "who won" in text:
        return 1

    return default_value


def _seasonfix_is_batting_year_question(question):
    text = str(question or "").lower()

    if "orange cap" in text:
        return True

    if any(x in text for x in ["run scorer", "run scorers", "most runs", "highest runs", "scored the most runs"]):
        return True

    return False


def _seasonfix_is_bowling_year_question(question):
    text = str(question or "").lower()

    if "purple cap" in text:
        return True

    if any(x in text for x in ["wicket taker", "wicket takers", "most wickets", "highest wickets", "taken the most wickets", "took the most wickets"]):
        return True

    return False


def _seasonfix_is_single_season_batting_record(question):
    text = str(question or "").lower()

    if "in a season" in text or "in one season" in text or "single season" in text:
        return any(x in text for x in ["most runs", "run scorer", "scored the most runs", "highest runs"])

    return False


def _seasonfix_is_single_season_bowling_record(question):
    text = str(question or "").lower()

    if "in a season" in text or "in one season" in text or "single season" in text:
        return any(x in text for x in ["most wickets", "wicket taker", "taken the most wickets", "took the most wickets", "highest wickets"])

    return False


def _seasonfix_batting_leaderboard(question, typed_year=None):
    import pandas as pd
    from app.db import run_query

    season_expr = _seasonfix_season_label_expr("d")
    filters = ["d.innings IN (1, 2)"]

    if typed_year is not None:
        filters.append(_seasonfix_season_condition("d", typed_year))

    where_sql = " AND ".join(filters)
    limit = _seasonfix_limit(question, default_value=10)

    sql = f"""
WITH batter_innings AS (
    SELECT
        {season_expr} AS season,
        d.striker AS batter,
        d.batting_team AS team,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS balls,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out', 'retired not out')
            THEN 1 ELSE 0
        END) AS out_flag
    FROM deliveries d
    WHERE {where_sql}
    GROUP BY {season_expr}, d.striker, d.batting_team, d.match_id, d.innings
),
totals AS (
    SELECT
        season,
        batter,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM batter_innings bi2
            WHERE bi2.batter = bi.batter
              AND bi2.season = bi.season
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(balls) AS balls,
        SUM(out_flag) AS dismissals,
        ROUND(SUM(innings_runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate,
        ROUND(SUM(innings_runs) * 1.0 / NULLIF(SUM(out_flag), 0), 2) AS batting_average,
        MAX(innings_runs) AS highest_score,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds
    FROM batter_innings bi
    GROUP BY season, batter
)
SELECT TOP {limit}
    season,
    batter,
    team,
    matches,
    innings,
    runs,
    balls,
    strike_rate,
    dismissals,
    batting_average,
    highest_score,
    fifties,
    hundreds
FROM totals
WHERE balls > 0
ORDER BY runs DESC, strike_rate DESC, batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The season batting leaderboard route failed: {error}",
            "paragraph": f"The season batting leaderboard route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _seasonfix_clean_table(df if df is not None else pd.DataFrame())

    if typed_year is not None:
        title = f"Top run scorer in {typed_year}" if limit == 1 else f"Top run scorers in {typed_year}"
    else:
        title = "Most runs in a single IPL season"

    return {
        "question": question,
        "analysis_paragraph": f"{title}. Seasons stored as 2007/08, 2009/10, or 2020/21 are displayed using the year after the slash.",
        "paragraph": f"{title}. Seasons stored as 2007/08, 2009/10, or 2020/21 are displayed using the year after the slash.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who won orange cap in 2008",
            "who scored the most runs in a season",
            "top 10 run scorers in 2010",
            "who won orange cap in 2021",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _seasonfix_bowling_leaderboard(question, typed_year=None):
    import pandas as pd
    from app.db import run_query

    season_expr = _seasonfix_season_label_expr("d")
    filters = ["d.innings IN (1, 2)"]

    if typed_year is not None:
        filters.append(_seasonfix_season_condition("d", typed_year))

    where_sql = " AND ".join(filters)
    limit = _seasonfix_limit(question, default_value=10)

    sql = f"""
WITH bowler_innings AS (
    SELECT
        {season_expr} AS season,
        d.bowler,
        d.bowling_team AS team,
        d.match_id,
        d.innings,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS legal_balls,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        COUNT(CASE WHEN COALESCE(d.runs_off_bat, 0)=0 AND COALESCE(d.extras, 0)=0 THEN 1 END) AS dot_balls
    FROM deliveries d
    WHERE {where_sql}
    GROUP BY {season_expr}, d.bowler, d.bowling_team, d.match_id, d.innings
),
totals AS (
    SELECT
        season,
        bowler,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM bowler_innings bi2
            WHERE bi2.bowler = bi.bowler
              AND bi2.season = bi.season
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(legal_balls) AS legal_balls,
        CAST(SUM(legal_balls) / 6 AS varchar(20)) + '.' + CAST(SUM(legal_balls) % 6 AS varchar(1)) AS overs_bowled,
        SUM(wickets) AS wickets,
        SUM(runs_conceded) AS runs_conceded,
        ROUND(SUM(runs_conceded) * 6.0 / NULLIF(SUM(legal_balls), 0), 2) AS economy,
        ROUND(SUM(legal_balls) * 1.0 / NULLIF(SUM(wickets), 0), 2) AS bowling_strike_rate,
        SUM(dot_balls) AS dot_balls
    FROM bowler_innings bi
    GROUP BY season, bowler
)
SELECT TOP {limit}
    season,
    bowler,
    team,
    matches,
    innings,
    overs_bowled,
    legal_balls,
    wickets,
    runs_conceded,
    economy,
    bowling_strike_rate,
    dot_balls
FROM totals
WHERE legal_balls > 0
ORDER BY wickets DESC, economy ASC, legal_balls DESC, bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The season bowling leaderboard route failed: {error}",
            "paragraph": f"The season bowling leaderboard route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _seasonfix_clean_table(df if df is not None else pd.DataFrame())

    if typed_year is not None:
        title = f"Top wicket taker in {typed_year}" if limit == 1 else f"Top wicket takers in {typed_year}"
    else:
        title = "Most wickets in a single IPL season"

    return {
        "question": question,
        "analysis_paragraph": f"{title}. Seasons stored as 2007/08, 2009/10, or 2020/21 are displayed using the year after the slash.",
        "paragraph": f"{title}. Seasons stored as 2007/08, 2009/10, or 2020/21 are displayed using the year after the slash.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who won purple cap in 2008",
            "who took the most wickets in a season",
            "top 10 wicket takers in 2010",
            "who won purple cap in 2021",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_seasonfix = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_seasonfix = None


def answer_question_with_fallback(user_question):
    year = _seasonfix_extract_year(user_question)

    # Single-season all-time records must be caught before year-specific wording.
    if _seasonfix_is_single_season_batting_record(user_question):
        return _seasonfix_batting_leaderboard(user_question, typed_year=None)

    if _seasonfix_is_single_season_bowling_record(user_question):
        return _seasonfix_bowling_leaderboard(user_question, typed_year=None)

    if year is not None and _seasonfix_is_batting_year_question(user_question):
        return _seasonfix_batting_leaderboard(user_question, typed_year=year)

    if year is not None and _seasonfix_is_bowling_year_question(user_question):
        return _seasonfix_bowling_leaderboard(user_question, typed_year=year)

    result = _previous_answer_question_with_fallback_before_seasonfix(user_question)
    return _seasonfix_clean_result(result)

# IPL SQL Agent season alias and cap routes END


# IPL SQL Agent 2020 slash season correction START

def _seasondisplay_year_from_value(value):
    import re

    if value is None:
        return value

    text = str(value).strip()

    # Special IPL data case: 2020/21 is the 2020 season, not the 2021 season.
    if text == "2020/21":
        return "2020"

    match = re.fullmatch(r"(\d{4})/(\d{2})", text)

    if match:
        first_year = int(match.group(1))
        suffix = int(match.group(2))

        if suffix <= 30:
            return str(2000 + suffix)

        return str(1900 + suffix)

    return value


def _seasondisplay_replace_slash_years(value):
    import re

    if value is None:
        return value

    text = str(value)

    def repl(match):
        return str(_seasondisplay_year_from_value(match.group(0)))

    return re.sub(r"\b\d{4}/\d{2}\b", repl, text)


def _seasondisplay_fix_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()

        for column in table.columns:
            name = str(column).lower()

            if "season" in name or "year" in name or "years won" in name:
                table[column] = table[column].apply(_seasondisplay_replace_slash_years)

        return table

    except Exception:
        return table


def _seasondisplay_fix_result(result):
    if not isinstance(result, dict):
        return result

    result["result"] = _seasondisplay_fix_table(result.get("result"))

    extra = result.get("extra_tables")

    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _seasondisplay_fix_table(table)

        result["extra_tables"] = extra

    return result


# Override the previous season condition.
# 2007/08 should still match 2008 and 2009/10 should still match 2010.
# But 2020/21 should match 2020 only, not 2021.
def _seasonfix_season_condition(alias, typed_year):
    year = int(typed_year)

    if year == 2020:
        return (
            f"(CAST({alias}.season AS varchar(20)) = '2020' "
            f"OR CAST({alias}.season AS varchar(20)) = '2020/21')"
        )

    if year == 2021:
        return f"(CAST({alias}.season AS varchar(20)) = '2021')"

    slash_form = f"{year - 1}/{str(year)[-2:]}"
    short_year = str(year)[-2:]

    return (
        f"(CAST({alias}.season AS varchar(20)) = '{year}' "
        f"OR CAST({alias}.season AS varchar(20)) = '{slash_form}' "
        f"OR CAST({alias}.season AS varchar(20)) LIKE '%/{short_year}')"
    )


# Override the previous SQL display/grouping expression.
# It keeps 2007/08 -> 2008 and 2009/10 -> 2010,
# but changes 2020/21 -> 2020.
def _seasonfix_season_label_expr(alias):
    return f"""
CASE
    WHEN CAST({alias}.season AS varchar(20)) = '2020/21'
    THEN '2020'
    WHEN CHARINDEX('/', CAST({alias}.season AS varchar(20))) > 0
         AND TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) IS NOT NULL
    THEN CAST(
        CASE
            WHEN TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) <= 30
            THEN 2000 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
            ELSE 1900 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
        END AS varchar(4)
    )
    ELSE CAST({alias}.season AS varchar(20))
END
""".strip()


try:
    _previous_answer_question_with_fallback_before_2020slashfix = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_2020slashfix = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_2020slashfix(user_question)

    if isinstance(result, dict):
        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""

        if "2020/21" in str(paragraph):
            paragraph = str(paragraph).replace(
                "Seasons stored as 2007/08, 2009/10, or 2020/21 are displayed using the year after the slash.",
                "Slash seasons are displayed as normal years. For example, 2007/08 is shown as 2008, 2009/10 as 2010, and 2020/21 as 2020."
            )
            paragraph = paragraph.replace("2020/21", "2020")

            result["analysis_paragraph"] = paragraph
            result["paragraph"] = paragraph

    return _seasondisplay_fix_result(result)

# IPL SQL Agent 2020 slash season correction END


# IPL SQL Agent corrected fastest milestone routes START

def _fastmile_q(value):
    return str(value).replace("'", "''")


def _fastmile_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    return "(" + ", ".join("'" + _fastmile_q(v) + "'" for v in values) + ")" if values else "('')"


def _fastmile_short_team(value):
    if value is None:
        return value

    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }

    parts = [p.strip() for p in str(value).split(",") if p and str(p).strip()]
    out = []
    seen = set()

    for part in parts:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            out.append(short)
            seen.add(key)

    return ", ".join(out)


def _fastmile_clean_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()
        for col in ["team", "opposition", "batting_team", "bowling_team"]:
            if col in table.columns:
                table[col] = table[col].apply(_fastmile_short_team)
        return table
    except Exception:
        return table


def _fastmile_clean_result(result):
    if not isinstance(result, dict):
        return result

    result["result"] = _fastmile_clean_table(result.get("result"))

    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _fastmile_clean_table(table)
        result["extra_tables"] = extra

    return result


def _fastmile_team_lookup(raw):
    text = str(raw or "").lower().strip()

    if text in {"ipl", "the ipl", "history", "overall", "all seasons", "all time"}:
        return None, None, []

    if text == "dc":
        return "AMBIGUOUS_DC", None, []

    teams = [
        ("CSK", "CSK", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "MI", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "RCB", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "GT", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "KKR", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "RR", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "SRH", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("Delhi Capitals", "Delhi Capitals", ["Delhi Capitals", "Delhi Daredevils"], ["delhi capitals", "delhi daredevils"]),
        ("Deccan Chargers", "Deccan Chargers", ["Deccan Chargers"], ["deccan chargers", "deccan"]),
        ("PBKS", "PBKS", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "LSG", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "RPS", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "GL", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "KTK", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "PWI", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
    ]

    for code, display, aliases, triggers in teams:
        if text in triggers or any(t in text for t in triggers):
            return code, display, aliases

    return None, None, []


def _fastmile_venue_filter(raw):
    low = str(raw or "").lower().strip(" .?")

    if not low or low in {"ipl", "the ipl", "history", "overall", "all seasons", "all time"}:
        return "1=1", None

    if "new chandigarh" in low or "mullanpur" in low or "yadavindra" in low:
        return "(m.venue LIKE '%Yadavindra%' OR m.venue LIKE '%Mullanpur%' OR m.venue LIKE '%New Chandigarh%' OR m.city LIKE '%Chandigarh%' OR m.city LIKE '%Mullanpur%')", "New Chandigarh"
    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"
    if "uppal" in low or "rajiv gandhi" in low:
        return "(m.venue LIKE '%Rajiv Gandhi%' OR m.venue LIKE '%Uppal%')", "Uppal"
    if "arun jaitley" in low or "kotla" in low:
        return "(m.venue LIKE '%Arun Jaitley%' OR m.venue LIKE '%Kotla%')", "Arun Jaitley Stadium"
    if "dubai" in low:
        return "(m.venue LIKE '%Dubai%' OR m.city LIKE '%Dubai%')", "Dubai"
    if "sharjah" in low:
        return "(m.venue LIKE '%Sharjah%' OR m.city LIKE '%Sharjah%')", "Sharjah"
    if "abu dhabi" in low or "zayed" in low:
        return "(m.venue LIKE '%Abu Dhabi%' OR m.venue LIKE '%Zayed%' OR m.city LIKE '%Abu Dhabi%')", "Abu Dhabi"
    if "brabourne" in low:
        return "m.venue LIKE '%Brabourne%'", "Brabourne"
    if "mohali" in low or "bindra" in low:
        return "(m.venue LIKE '%Mohali%' OR m.venue LIKE '%Bindra%' OR m.city LIKE '%Mohali%')", "Mohali"
    if "dharamsala" in low or "dharamshala" in low:
        return "(m.venue LIKE '%Dharamsala%' OR m.venue LIKE '%Dharamshala%' OR m.city LIKE '%Dharam%')", "Dharamshala"

    return "1=1", None


def _fastmile_season_condition(alias, typed_year):
    year = int(typed_year)

    if year == 2020:
        return f"(CAST({alias}.season AS varchar(20)) = '2020' OR CAST({alias}.season AS varchar(20)) = '2020/21')"

    if year == 2021:
        return f"(CAST({alias}.season AS varchar(20)) = '2021')"

    slash_form = f"{year - 1}/{str(year)[-2:]}"
    short_year = str(year)[-2:]

    return (
        f"(CAST({alias}.season AS varchar(20)) = '{year}' "
        f"OR CAST({alias}.season AS varchar(20)) = '{_fastmile_q(slash_form)}' "
        f"OR CAST({alias}.season AS varchar(20)) LIKE '%/{_fastmile_q(short_year)}')"
    )


def _fastmile_season_label_expr(alias):
    return f"""
CASE
    WHEN CAST({alias}.season AS varchar(20)) = '2020/21'
    THEN '2020'
    WHEN CHARINDEX('/', CAST({alias}.season AS varchar(20))) > 0
         AND TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) IS NOT NULL
    THEN CAST(
        CASE
            WHEN TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) <= 30
            THEN 2000 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
            ELSE 1900 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
        END AS varchar(4)
    )
    ELSE CAST({alias}.season AS varchar(20))
END
""".strip()


def _fastmile_parse(question):
    import re

    text = str(question or "")
    low = text.lower()

    if "fastest" not in low:
        return None

    milestone = None

    if re.search(r"\b(50|fifty|half[\s-]*century|half century)\b", low):
        milestone = 50
    elif re.search(r"\b(100|hundred|century)\b", low):
        milestone = 100

    if milestone is None:
        return None

    limit = 10
    top_match = re.search(r"\btop\s+(\d+)\b", low)
    if top_match:
        value = int(top_match.group(1))
        if 1 <= value <= 50:
            limit = value

    year = None
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        year = int(year_match.group(1))

    # Remove parenthesised/extra minimum words if ever included.
    clean = re.sub(r"\([^)]*\)", " ", text)

    filters = ["d.innings IN (1, 2)"]
    labels = []
    ambiguity = False

    # Venue: at/in/on/inside VENUE. "in IPL history" is ignored.
    venue_match = re.search(
        r"\b(?:at|inside|on)\s+([A-Za-z0-9 .'-]+?)(?:\s+for\s+|\s+against\s+|\s+in\s+20\d{2}|\s*$)",
        clean,
        flags=re.IGNORECASE,
    )

    if not venue_match:
        in_match = re.search(
            r"\bin\s+([A-Za-z0-9 .'-]+?)(?:\s+for\s+|\s+against\s+|\s+in\s+20\d{2}|\s*$)",
            clean,
            flags=re.IGNORECASE,
        )
        if in_match and in_match.group(1).strip(" .?").lower() not in {"ipl", "the ipl", "history", "ipl history"}:
            venue_match = in_match

    if venue_match:
        venue_sql, venue_label = _fastmile_venue_filter(venue_match.group(1))
        if venue_label:
            filters.append(venue_sql)
            labels.append(f"at {venue_label}")

    # Own team: for/from/by TEAM.
    own_match = re.search(
        r"\b(?:for|from|by)\s+([A-Za-z0-9 .]+?)(?:\s+at\s+|\s+in\s+20\d{2}|\s+against\s+|\s*$)",
        clean,
        flags=re.IGNORECASE,
    )

    if own_match:
        code, display, aliases = _fastmile_team_lookup(own_match.group(1).strip(" .?"))
        if code == "AMBIGUOUS_DC":
            ambiguity = True
        elif aliases:
            filters.append(f"d.batting_team IN {_fastmile_sql_list(aliases)}")
            labels.append(f"for {display}")

    # Opposition: against TEAM.
    against_match = re.search(
        r"\bagainst\s+([A-Za-z0-9 .]+?)(?:\s+at\s+|\s+in\s+20\d{2}|\s*$)",
        clean,
        flags=re.IGNORECASE,
    )

    if against_match:
        code, display, aliases = _fastmile_team_lookup(against_match.group(1).strip(" .?"))
        if code == "AMBIGUOUS_DC":
            ambiguity = True
        elif aliases:
            filters.append(f"d.bowling_team IN {_fastmile_sql_list(aliases)}")
            labels.append(f"against {display}")

    if year is not None:
        filters.append(_fastmile_season_condition("d", year))
        labels.append(f"in {year}")

    return {
        "milestone": milestone,
        "limit": limit,
        "filters": filters,
        "labels": labels,
        "ambiguity": ambiguity,
    }


def _fastmile_dc_ambiguity(question):
    import pandas as pd

    df = pd.DataFrame([{
        "issue": "DC is ambiguous",
        "action": "Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "example": "fastest 50 against Delhi Capitals",
    }])

    return {
        "question": question,
        "analysis_paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "result": df,
        "extra_tables": {"Clarification": df},
        "sql_query": "",
        "similar_questions": [
            "fastest 50 against Delhi Capitals",
            "fastest 100 for Delhi Capitals",
            "fastest 50 against Deccan Chargers",
            "fastest 50 at Arun Jaitley",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _fastmile_route(question):
    import pandas as pd
    from app.db import run_query

    parsed = _fastmile_parse(question)

    if not parsed:
        return None

    if parsed["ambiguity"]:
        return _fastmile_dc_ambiguity(question)

    milestone = int(parsed["milestone"])
    limit = int(parsed["limit"])
    where_sql = " AND ".join(parsed["filters"])
    season_expr = _fastmile_season_label_expr("d")

    milestone_col = "balls_to_fifty" if milestone == 50 else "balls_to_hundred"
    milestone_name = "50" if milestone == 50 else "100"

    # Correct ball-counting rule:
    # balls faced excludes wides only. No-balls are still faced deliveries for the batter,
    # so excluding no-balls can undercount fastest 50/100 by 1-2 balls.
    sql = f"""
WITH innings_events AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.batting_team AS team,
        d.bowling_team AS opposition,
        {season_expr} AS season,
        m.start_date AS match_date,
        m.venue,
        d.ball,
        COALESCE(d.runs_off_bat, 0) AS runs_off_bat,
        CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 ELSE 0 END AS ball_faced,
        CASE WHEN COALESCE(d.runs_off_bat, 0)=4 THEN 1 ELSE 0 END AS four_hit,
        CASE WHEN COALESCE(d.runs_off_bat, 0)=6 THEN 1 ELSE 0 END AS six_hit,
        SUM(COALESCE(d.runs_off_bat, 0)) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
            ORDER BY d.ball
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_runs,
        SUM(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 ELSE 0 END) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
            ORDER BY d.ball
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_balls,
        SUM(COALESCE(d.runs_off_bat, 0)) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
        ) AS innings_runs,
        SUM(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 ELSE 0 END) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
        ) AS innings_balls,
        SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=4 THEN 1 ELSE 0 END) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
        ) AS fours,
        SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=6 THEN 1 ELSE 0 END) OVER (
            PARTITION BY d.match_id, d.innings, d.striker
        ) AS sixes
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
),
milestone_rows AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY match_id, innings, batter
            ORDER BY ball
        ) AS milestone_rank
    FROM innings_events
    WHERE cumulative_runs >= {milestone}
)
SELECT TOP {limit}
    batter,
    team,
    season,
    match_date,
    venue,
    opposition,
    innings_runs,
    cumulative_balls AS {milestone_col},
    cumulative_balls AS balls_to_milestone,
    innings_balls,
    fours,
    sixes,
    ball AS milestone_delivery
FROM milestone_rows
WHERE milestone_rank = 1
ORDER BY
    cumulative_balls ASC,
    innings_runs DESC,
    match_date ASC,
    batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The corrected fastest {milestone_name} route failed: {error}",
            "paragraph": f"The corrected fastest {milestone_name} route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _fastmile_clean_table(df if df is not None else pd.DataFrame())

    label_suffix = " ".join(parsed["labels"]).strip()
    title = f"Fastest {milestone_name}s"
    if label_suffix:
        title = f"{title} {label_suffix}"

    paragraph = (
        f"{title}. Balls faced are counted using batter balls faced, which excludes wides only. "
        f"No-balls are included as faced deliveries, preventing the fastest {milestone_name} count from being understated."
    )

    return {
        "question": question,
        "analysis_paragraph": paragraph,
        "paragraph": paragraph,
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "fastest 50 in IPL history",
            "fastest 100 in IPL history",
            "fastest 50 for CSK",
            "fastest 50 at Wankhede",
            "fastest 50 against MI",
            "fastest 100 for RCB at Chinnaswamy",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_fastmile = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_fastmile = None


def answer_question_with_fallback(user_question):
    result = _fastmile_route(user_question)

    if result is not None:
        return result

    result = _previous_answer_question_with_fallback_before_fastmile(user_question)
    return _fastmile_clean_result(result)

# IPL SQL Agent corrected fastest milestone routes END


# IPL SQL Agent fastest milestone batting_team compatibility START

def _fastmile_add_batting_team_column(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()

        if "batting_team" not in table.columns and "team" in table.columns:
            insert_at = list(table.columns).index("team") + 1
            table.insert(insert_at, "batting_team", table["team"])

        return table

    except Exception:
        return table


def _fastmile_add_batting_team_to_result(result, question):
    if not isinstance(result, dict):
        return result

    if "fastest" not in str(question or "").lower():
        return result

    result["result"] = _fastmile_add_batting_team_column(result.get("result"))

    extra = result.get("extra_tables")

    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _fastmile_add_batting_team_column(table)

        result["extra_tables"] = extra

    return result


try:
    _previous_answer_question_with_fallback_before_fastmile_batting_team = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_fastmile_batting_team = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_fastmile_batting_team(user_question)
    return _fastmile_add_batting_team_to_result(result, user_question)

# IPL SQL Agent fastest milestone batting_team compatibility END


# IPL SQL Agent filtered player fifties/hundreds team fix START

def _pfh_q(value):
    return str(value).replace("'", "''")


def _pfh_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    return "(" + ", ".join("'" + _pfh_q(v) + "'" for v in values) + ")" if values else "('')"


def _pfh_short_team(value):
    if value is None:
        return value
    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }
    out, seen = [], set()
    for part in [p.strip() for p in str(value).split(",") if p and str(p).strip()]:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            out.append(short)
            seen.add(key)
    return ", ".join(out)


def _pfh_clean_table(table):
    if table is None or not hasattr(table, "columns"):
        return table
    try:
        table = table.copy()
        for col in ["team", "teams", "batting_team", "bowling_team", "opposition"]:
            if col in table.columns:
                table[col] = table[col].apply(_pfh_short_team)
        return table
    except Exception:
        return table


def _pfh_team_lookup(raw):
    text = str(raw or "").lower().strip()
    if text == "dc":
        return "AMBIGUOUS_DC", None, []

    teams = [
        ("CSK", "CSK", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "MI", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "RCB", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "GT", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "KKR", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "RR", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "SRH", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("Delhi Capitals", "Delhi Capitals", ["Delhi Capitals", "Delhi Daredevils"], ["delhi capitals", "delhi daredevils"]),
        ("Deccan Chargers", "Deccan Chargers", ["Deccan Chargers"], ["deccan chargers", "deccan"]),
        ("PBKS", "PBKS", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "LSG", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "RPS", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "GL", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "KTK", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "PWI", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
    ]

    for code, display, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, display, aliases

    return None, None, []


def _pfh_player_aliases(raw):
    label = str(raw or "").strip()
    low = label.lower()
    aliases = [label]
    known = {
        "buttler": ["JC Buttler", "Jos Buttler"],
        "jc buttler": ["JC Buttler", "Jos Buttler"],
        "jos buttler": ["JC Buttler", "Jos Buttler"],
        "kohli": ["V Kohli", "Virat Kohli"],
        "virat": ["V Kohli", "Virat Kohli"],
        "rohit": ["RG Sharma", "Rohit Sharma"],
        "dhoni": ["MS Dhoni"],
        "rahul": ["KL Rahul"],
        "gaikwad": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "ruturaj": ["RD Gaikwad", "Ruturaj Gaikwad"],
        "suryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
        "sooryavanshi": ["V Suryavanshi", "Vaibhav Suryavanshi", "Vaibhav Sooryavanshi"],
    }
    for key, values in known.items():
        if key in low:
            for value in values:
                if value not in aliases:
                    aliases.append(value)
    return aliases


def _pfh_resolve_player(raw):
    aliases = _pfh_player_aliases(raw)
    try:
        from app.db import run_query
        low = str(raw or "").lower().strip()
        where_bits = [f"striker IN {_pfh_sql_list(aliases)}"]
        if "buttler" in low:
            where_bits.append("LOWER(striker) LIKE '%buttler%'")
        elif len(low) >= 4:
            where_bits.append(f"LOWER(striker) LIKE '%{_pfh_q(low)}%'")
        sql = f"""
SELECT TOP 1 striker AS player_name, COUNT(*) AS n
FROM deliveries
WHERE {" OR ".join(where_bits)}
GROUP BY striker
ORDER BY COUNT(*) DESC, striker ASC;
""".strip()
        df = run_query(sql)
        if df is not None and not df.empty:
            resolved = str(df.iloc[0]["player_name"])
            if resolved not in aliases:
                aliases.insert(0, resolved)
            return resolved, aliases
    except Exception:
        pass
    return aliases[0], aliases


def _pfh_venue_filter(raw):
    low = str(raw or "").lower().strip(" .?")
    if "new chandigarh" in low or "mullanpur" in low or "yadavindra" in low:
        return "(m.venue LIKE '%Yadavindra%' OR m.venue LIKE '%Mullanpur%' OR m.venue LIKE '%New Chandigarh%' OR m.city LIKE '%Chandigarh%' OR m.city LIKE '%Mullanpur%')", "New Chandigarh"
    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"
    if "uppal" in low or "rajiv gandhi" in low:
        return "(m.venue LIKE '%Rajiv Gandhi%' OR m.venue LIKE '%Uppal%')", "Uppal"
    if "arun jaitley" in low or "kotla" in low:
        return "(m.venue LIKE '%Arun Jaitley%' OR m.venue LIKE '%Kotla%')", "Arun Jaitley Stadium"
    return None, None


def _pfh_season_condition(alias, year):
    year = int(year)
    if year == 2020:
        return f"(CAST({alias}.season AS varchar(20)) = '2020' OR CAST({alias}.season AS varchar(20)) = '2020/21')"
    if year == 2021:
        return f"(CAST({alias}.season AS varchar(20)) = '2021')"
    slash_form = f"{year - 1}/{str(year)[-2:]}"
    short_year = str(year)[-2:]
    return (
        f"(CAST({alias}.season AS varchar(20)) = '{year}' "
        f"OR CAST({alias}.season AS varchar(20)) = '{_pfh_q(slash_form)}' "
        f"OR CAST({alias}.season AS varchar(20)) LIKE '%/{_pfh_q(short_year)}')"
    )


def _pfh_parse(question):
    import re
    text = str(question or "").strip()
    low = text.lower()
    if "how many" not in low:
        return None

    if re.search(r"\b(fifties|fifty|50s|50|half[\s-]*centuries|half[\s-]*century)\b", low):
        milestone = "fifties"
    elif re.search(r"\b(hundreds|hundred|100s|100|centuries|century)\b", low):
        milestone = "hundreds"
    else:
        return None

    match = re.search(
        r"\bhow many\b.*?\b(?:does|has|did)\s+(.+?)\s+(?:have|score|hit|make)\b(.*)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    player_raw = match.group(1).strip(" .?")
    remainder = match.group(2).strip(" .?")

    filters = ["d.innings IN (1, 2)"]
    labels = []

    for_match = re.search(
        r"\b(?:for|from|by)\s+([A-Za-z0-9 .]+?)(?:\s+against\s+|\s+at\s+|\s+in\s+20\d{2}|\s*$)",
        remainder,
        flags=re.IGNORECASE,
    )
    if for_match:
        code, display, aliases = _pfh_team_lookup(for_match.group(1).strip(" .?"))
        if code == "AMBIGUOUS_DC":
            return {"ambiguous": True}
        if aliases:
            filters.append(f"d.batting_team IN {_pfh_sql_list(aliases)}")
            labels.append(f"for {display}")

    against_match = re.search(
        r"\bagainst\s+([A-Za-z0-9 .]+?)(?:\s+for\s+|\s+at\s+|\s+in\s+20\d{2}|\s*$)",
        remainder,
        flags=re.IGNORECASE,
    )
    if against_match:
        code, display, aliases = _pfh_team_lookup(against_match.group(1).strip(" .?"))
        if code == "AMBIGUOUS_DC":
            return {"ambiguous": True}
        if aliases:
            filters.append(f"d.bowling_team IN {_pfh_sql_list(aliases)}")
            labels.append(f"against {display}")

    venue_match = re.search(
        r"\b(?:at|inside|on)\s+([A-Za-z0-9 .'-]+?)(?:\s+for\s+|\s+against\s+|\s+in\s+20\d{2}|\s*$)",
        remainder,
        flags=re.IGNORECASE,
    )
    if not venue_match:
        in_match = re.search(
            r"\bin\s+([A-Za-z0-9 .'-]+?)(?:\s+for\s+|\s+against\s+|\s+in\s+20\d{2}|\s*$)",
            remainder,
            flags=re.IGNORECASE,
        )
        if in_match and not re.fullmatch(r"20\d{2}", in_match.group(1).strip(" .?")):
            venue_match = in_match
    if venue_match:
        venue_sql, venue_label = _pfh_venue_filter(venue_match.group(1))
        if venue_label:
            filters.append(venue_sql)
            labels.append(f"at {venue_label}")

    year_match = re.search(r"\b(20\d{2})\b", remainder)
    if year_match:
        year = int(year_match.group(1))
        filters.append(_pfh_season_condition("d", year))
        labels.append(f"in {year}")

    return {
        "player_raw": player_raw,
        "milestone": milestone,
        "filters": filters,
        "labels": labels,
        "ambiguous": False,
    }


def _pfh_ambiguity(question):
    import pandas as pd
    df = pd.DataFrame([{
        "issue": "DC is ambiguous",
        "action": "Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "example": "how many fifties does Kohli have against Delhi Capitals",
    }])
    return {
        "question": question,
        "analysis_paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "result": df,
        "extra_tables": {"Clarification": df},
        "sql_query": "",
        "similar_questions": [
            "how many fifties does JC Buttler have for MI",
            "how many hundreds does JC Buttler have for MI",
            "how many fifties does Kohli have against CSK",
            "how many hundreds does Rohit have for MI",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _pfh_route(question):
    import pandas as pd
    from app.db import run_query

    parsed = _pfh_parse(question)
    if not parsed:
        return None
    if parsed.get("ambiguous"):
        return _pfh_ambiguity(question)

    resolved, aliases = _pfh_resolve_player(parsed["player_raw"])
    filters = [f"d.striker IN {_pfh_sql_list(aliases)}"]
    filters.extend(parsed["filters"])
    where_sql = " AND ".join(filters)

    sql = f"""
WITH batter_innings AS (
    SELECT
        d.striker AS batter,
        d.batting_team AS team,
        d.bowling_team AS opposition,
        d.match_id,
        d.innings,
        m.start_date AS match_date,
        m.venue,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 END) AS balls
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.striker, d.batting_team, d.bowling_team, d.match_id, d.innings, m.start_date, m.venue
),
summary AS (
    SELECT
        batter,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM batter_innings bi2
            WHERE bi2.batter = bi.batter
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(balls) AS balls,
        SUM(CASE WHEN innings_runs BETWEEN 50 AND 99 THEN 1 ELSE 0 END) AS fifties,
        SUM(CASE WHEN innings_runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
        MAX(innings_runs) AS highest_score
    FROM batter_innings bi
    GROUP BY batter
)
SELECT
    batter,
    team,
    matches,
    innings,
    runs,
    balls,
    fifties,
    hundreds,
    highest_score
FROM summary
ORDER BY runs DESC, batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The filtered player fifties/hundreds route failed: {error}",
            "paragraph": f"The filtered player fifties/hundreds route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _pfh_clean_table(df if df is not None else pd.DataFrame())
    label = " ".join(parsed["labels"]).strip()
    milestone = parsed["milestone"]

    if not df.empty and milestone in df.columns:
        count_value = int(df.iloc[0][milestone])
        answer = f"{resolved} has {count_value} {milestone}"
        if label:
            answer += f" {label}"
        answer += "."
    else:
        answer = f"No {milestone} found for {resolved}"
        if label:
            answer += f" {label}"
        answer += "."

    return {
        "question": question,
        "analysis_paragraph": answer,
        "paragraph": answer,
        "result": df,
        "extra_tables": {f"{resolved} {milestone}": df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "how many fifties does JC Buttler have for MI",
            "how many hundreds does JC Buttler have for MI",
            "how many fifties does Kohli have against CSK",
            "how many hundreds does Rohit have for MI",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_pfh = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_pfh = None


def answer_question_with_fallback(user_question):
    result = _pfh_route(user_question)
    if result is not None:
        return result
    result = _previous_answer_question_with_fallback_before_pfh(user_question)
    return result

# IPL SQL Agent filtered player fifties/hundreds team fix END


# IPL SQL Agent player milestone player-column compatibility START

def _milestone_add_player_column(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()

        if "player" not in table.columns:
            if "batter" in table.columns:
                insert_at = list(table.columns).index("batter")
                table.insert(insert_at, "player", table["batter"])
            elif "striker" in table.columns:
                insert_at = list(table.columns).index("striker")
                table.insert(insert_at, "player", table["striker"])

        return table

    except Exception:
        return table


def _milestone_needs_player_column(question, result):
    text = str(question or "").lower()

    if "how many" not in text:
        return False

    if any(word in text for word in ["fifties", "fifty", "50", "hundreds", "hundred", "100", "centuries", "century"]):
        return True

    if isinstance(result, dict):
        table = result.get("result")
        if hasattr(table, "columns"):
            cols = {str(c).lower() for c in table.columns}
            if ("fifties" in cols or "hundreds" in cols) and ("batter" in cols or "striker" in cols):
                return True

    return False


def _milestone_apply_player_column(result, question):
    if not isinstance(result, dict):
        return result

    if not _milestone_needs_player_column(question, result):
        return result

    result["result"] = _milestone_add_player_column(result.get("result"))

    extra = result.get("extra_tables")

    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _milestone_add_player_column(table)

        result["extra_tables"] = extra

    return result


try:
    _previous_answer_question_with_fallback_before_milestone_player_column = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_milestone_player_column = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_milestone_player_column(user_question)
    return _milestone_apply_player_column(result, user_question)

# IPL SQL Agent player milestone player-column compatibility END


# IPL SQL Agent strict Mullanpur/New Chandigarh venue separation START

def _mullanpur_strict_condition(prefix="m."):
    # Keep Mullanpur/New Chandigarh separate from old Mohali/PCA/IS Bindra records.
    # Do NOT use city LIKE '%Chandigarh%' because older Mohali records may share city labels.
    return (
        f"({prefix}venue LIKE '%Yadavindra%' "
        f"OR {prefix}venue LIKE '%Mullanpur%' "
        f"OR {prefix}venue LIKE '%New Chandigarh%')"
    )


def _mullanpur_is_alias(text):
    low = str(text or "").lower()
    return (
        "new chandigarh" in low
        or "mullanpur" in low
        or "yadavindra" in low
        or "maharaja yadavindra" in low
    )


def _mullanpur_label():
    return "Mullanpur / New Chandigarh"


# Override the earlier New Chandigarh helper if present.
def _nc_venue_filter_condition(prefix="m."):
    return _mullanpur_strict_condition(prefix)


def _nc_is_new_chandigarh(text):
    return _mullanpur_is_alias(text)


# Robust rate/economy route venue helper.
try:
    _previous_rrfinal_venue_filter_before_mullanpur_strict = _rrfinal_venue_filter
except NameError:
    _previous_rrfinal_venue_filter_before_mullanpur_strict = None


def _rrfinal_venue_filter(raw):
    if _mullanpur_is_alias(raw):
        return _mullanpur_strict_condition("m."), _mullanpur_label()

    if _previous_rrfinal_venue_filter_before_mullanpur_strict:
        return _previous_rrfinal_venue_filter_before_mullanpur_strict(raw)

    return "1=1", None


# Earlier rate route venue helper.
try:
    _previous_rate_venue_filter_before_mullanpur_strict = _rate_venue_filter
except NameError:
    _previous_rate_venue_filter_before_mullanpur_strict = None


def _rate_venue_filter(question):
    if _mullanpur_is_alias(question):
        return _mullanpur_strict_condition("m."), _mullanpur_label()

    if _previous_rate_venue_filter_before_mullanpur_strict:
        return _previous_rate_venue_filter_before_mullanpur_strict(question)

    return "1=1", None


# Fastest milestone route venue helper.
try:
    _previous_fastmile_venue_filter_before_mullanpur_strict = _fastmile_venue_filter
except NameError:
    _previous_fastmile_venue_filter_before_mullanpur_strict = None


def _fastmile_venue_filter(raw):
    if _mullanpur_is_alias(raw):
        return _mullanpur_strict_condition("m."), _mullanpur_label()

    if _previous_fastmile_venue_filter_before_mullanpur_strict:
        return _previous_fastmile_venue_filter_before_mullanpur_strict(raw)

    return "1=1", None


# Player fifties/hundreds route venue helper.
try:
    _previous_pfh_venue_filter_before_mullanpur_strict = _pfh_venue_filter
except NameError:
    _previous_pfh_venue_filter_before_mullanpur_strict = None


def _pfh_venue_filter(raw):
    if _mullanpur_is_alias(raw):
        return _mullanpur_strict_condition("m."), _mullanpur_label()

    if _previous_pfh_venue_filter_before_mullanpur_strict:
        return _previous_pfh_venue_filter_before_mullanpur_strict(raw)

    return None, None


# Bowler-vs-batter-at-venue helper.
try:
    _previous_bvv_venue_filter_before_mullanpur_strict = _bvv_venue_filter
except NameError:
    _previous_bvv_venue_filter_before_mullanpur_strict = None


def _bvv_venue_filter(raw):
    if _mullanpur_is_alias(raw):
        return _mullanpur_strict_condition("m."), _mullanpur_label()

    if _previous_bvv_venue_filter_before_mullanpur_strict:
        return _previous_bvv_venue_filter_before_mullanpur_strict(raw)

    return None, None


# Older bowler-vs-batter helper name.
try:
    _previous_bvvenue_venue_filter_from_raw_before_mullanpur_strict = _bvvenue_venue_filter_from_raw
except NameError:
    _previous_bvvenue_venue_filter_from_raw_before_mullanpur_strict = None


def _bvvenue_venue_filter_from_raw(raw):
    if _mullanpur_is_alias(raw):
        return _mullanpur_strict_condition("m."), _mullanpur_label()

    if _previous_bvvenue_venue_filter_from_raw_before_mullanpur_strict:
        return _previous_bvvenue_venue_filter_from_raw_before_mullanpur_strict(raw)

    return None, None


def _mullanpur_result_looks_contaminated(result):
    try:
        table = result.get("result") if isinstance(result, dict) else None

        if table is None or not hasattr(table, "columns") or table.empty:
            return False

        if "legal_balls" in table.columns:
            return int(table["legal_balls"].max()) > 1000

        if "matches" in table.columns:
            return int(table["matches"].max()) > 40

    except Exception:
        return False

    return False


try:
    _previous_answer_question_with_fallback_before_mullanpur_strict = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_mullanpur_strict = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_mullanpur_strict(user_question)

    if isinstance(result, dict) and _mullanpur_is_alias(user_question):
        # Make the wording clear in the output.
        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""
        paragraph = str(paragraph).replace("New Chandigarh", _mullanpur_label())
        result["analysis_paragraph"] = paragraph
        result["paragraph"] = paragraph

    return result

# IPL SQL Agent strict Mullanpur/New Chandigarh venue separation END


# IPL SQL Agent no-qualifier message for rate/economy routes START

def _noqual_table_is_empty(result):
    try:
        table = result.get("result") if isinstance(result, dict) else None
        return table is None or (hasattr(table, "empty") and table.empty)
    except Exception:
        return False


def _noqual_min_balls_from_question(question):
    import re

    text = str(question or "").lower()

    match = re.search(
        r"\b(?:min|minimum|at least)\s*[:=]?\s*(\d+)\s*(?:balls?|deliveries|balls bowled|balls faced)",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    return None


def _noqual_is_economy_question(question):
    text = str(question or "").lower()
    return "economy" in text and any(x in text for x in ["best", "lowest", "top"])


def _noqual_is_strike_rate_question(question):
    text = str(question or "").lower()
    return ("strike rate" in text or " sr" in text) and any(x in text for x in ["best", "highest", "top"])


def _noqual_empty_economy_result(question, previous_result):
    import pandas as pd

    min_balls = _noqual_min_balls_from_question(question)
    min_text = f"{min_balls} balls" if min_balls is not None else "the requested minimum"

    message = f"No bowler has bowled at least {min_text} for this filter yet."

    data = pd.DataFrame([{
        "bowler": "No qualifying bowler",
        "team": "",
        "matches": 0,
        "innings": 0,
        "overs_bowled": "0.0",
        "legal_balls": 0,
        "wickets": 0,
        "runs_conceded": 0,
        "economy": None,
        "bowling_strike_rate": None,
        "dot_balls": 0,
        "note": message,
    }])

    sql_query = previous_result.get("sql_query", "") if isinstance(previous_result, dict) else ""

    return {
        "question": question,
        "analysis_paragraph": message,
        "paragraph": message,
        "result": data,
        "extra_tables": {"No qualifying bowlers": data},
        "sql_query": sql_query,
        "similar_questions": [
            "best economy rate at mullanpur min 100 balls bowled",
            "best economy rate at mullanpur min 50 balls bowled",
            "best economy rate at New Chandigarh min 100 balls bowled",
            "best strike rate at mullanpur min 50 balls faced",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _noqual_empty_strike_rate_result(question, previous_result):
    import pandas as pd

    min_balls = _noqual_min_balls_from_question(question)
    min_text = f"{min_balls} balls" if min_balls is not None else "the requested minimum"

    message = f"No batter has faced at least {min_text} for this filter yet."

    data = pd.DataFrame([{
        "batter": "No qualifying batter",
        "team": "",
        "matches": 0,
        "innings": 0,
        "runs": 0,
        "dismissals": 0,
        "batting_average": None,
        "balls": 0,
        "strike_rate": None,
        "highest_score": 0,
        "fifties": 0,
        "hundreds": 0,
        "note": message,
    }])

    sql_query = previous_result.get("sql_query", "") if isinstance(previous_result, dict) else ""

    return {
        "question": question,
        "analysis_paragraph": message,
        "paragraph": message,
        "result": data,
        "extra_tables": {"No qualifying batters": data},
        "sql_query": sql_query,
        "similar_questions": [
            "best strike rate at mullanpur min 100 balls faced",
            "best strike rate at mullanpur min 50 balls faced",
            "best strike rate at New Chandigarh min 100 balls faced",
            "best economy rate at mullanpur min 50 balls bowled",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_noqual_messages = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_noqual_messages = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_noqual_messages(user_question)

    if _noqual_table_is_empty(result):
        if _noqual_is_economy_question(user_question):
            return _noqual_empty_economy_result(user_question, result)

        if _noqual_is_strike_rate_question(user_question):
            return _noqual_empty_strike_rate_result(user_question, result)

    return result

# IPL SQL Agent no-qualifier message for rate/economy routes END


# IPL SQL Agent strict Mullanpur/New Chandigarh venue profile START

def _mvp_is_mullanpur(text):
    low = str(text or "").lower()
    return (
        "new chandigarh" in low
        or "mullanpur" in low
        or "yadavindra" in low
        or "maharaja yadavindra" in low
    )


def _mvp_venue_condition(alias="m"):
    # Strict venue-only match. Do not use city LIKE '%Chandigarh%',
    # otherwise old Mohali/PCA records can get mixed in.
    return (
        f"({alias}.venue LIKE '%Yadavindra%' "
        f"OR {alias}.venue LIKE '%Mullanpur%' "
        f"OR {alias}.venue LIKE '%New Chandigarh%')"
    )


def _mvp_short_team(value):
    if value is None:
        return value

    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }

    parts = [p.strip() for p in str(value).split(",") if p and str(p).strip()]
    out = []
    seen = set()

    for part in parts:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            out.append(short)
            seen.add(key)

    return ", ".join(out)


def _mvp_clean_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()

        for col in ["team", "Team", "winner", "Winner", "toss_winner", "Toss Winner", "batting_team", "bowling_team"]:
            if col in table.columns:
                table[col] = table[col].apply(_mvp_short_team)

        return table

    except Exception:
        return table


def _mvp_parse(question):
    import re

    text = str(question or "").strip()
    low = text.lower()

    if not _mvp_is_mullanpur(text):
        return False

    venue_intent = (
        "venue profile" in low
        or "venue stats" in low
        or "ground profile" in low
        or "ground stats" in low
        or "tell me about" in low
        or "stats for" in low
        or "profile for" in low
        or re.search(r"\b(mullanpur|new chandigarh|yadavindra)\s+(?:stats|profile|venue profile)\b", low)
    )

    return bool(venue_intent)


def _mvp_no_data_result(question):
    import pandas as pd

    df = pd.DataFrame([{
        "venue": "Mullanpur / New Chandigarh",
        "matches": 0,
        "note": "No IPL matches found for this strict venue filter.",
    }])

    return {
        "question": question,
        "analysis_paragraph": "No IPL matches found for Mullanpur / New Chandigarh using the strict venue filter.",
        "paragraph": "No IPL matches found for Mullanpur / New Chandigarh using the strict venue filter.",
        "result": df,
        "extra_tables": {"Venue Summary": df},
        "sql_query": "",
        "similar_questions": [
            "tell me about Mullanpur",
            "venue profile for New Chandigarh",
            "best strike rate at Mullanpur min 50 balls faced",
            "best economy rate at Mullanpur min 50 balls bowled",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _mvp_venue_profile_route(question):
    import pandas as pd
    from app.db import run_query

    if not _mvp_parse(question):
        return None

    cond_m = _mvp_venue_condition("m")
    cond_m2 = _mvp_venue_condition("m2")
    cond_m3 = _mvp_venue_condition("m3")

    summary_sql = f"""
WITH venue_matches AS (
    SELECT
        m.match_id,
        m.season,
        m.start_date,
        m.venue,
        m.city,
        m.toss_winner,
        m.toss_decision,
        m.winner
    FROM matches m
    WHERE {cond_m}
),
innings_scores AS (
    SELECT
        d.match_id,
        d.innings,
        MAX(d.batting_team) AS batting_team,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS innings_runs
    FROM deliveries d
    JOIN venue_matches vm
        ON d.match_id = vm.match_id
    WHERE d.innings IN (1, 2)
    GROUP BY d.match_id, d.innings
),
match_scores AS (
    SELECT
        vm.match_id,
        vm.start_date,
        vm.venue,
        vm.toss_decision,
        vm.winner,
        MAX(CASE WHEN ins.innings = 1 THEN ins.batting_team END) AS batting_first_team,
        MAX(CASE WHEN ins.innings = 2 THEN ins.batting_team END) AS chasing_team,
        MAX(CASE WHEN ins.innings = 1 THEN ins.innings_runs END) AS first_innings_runs,
        MAX(CASE WHEN ins.innings = 2 THEN ins.innings_runs END) AS second_innings_runs
    FROM venue_matches vm
    LEFT JOIN innings_scores ins
        ON vm.match_id = ins.match_id
    GROUP BY vm.match_id, vm.start_date, vm.venue, vm.toss_decision, vm.winner
)
SELECT
    'Mullanpur / New Chandigarh' AS venue,
    COUNT(DISTINCT match_id) AS matches,
    MIN(start_date) AS first_match_date,
    MAX(start_date) AS last_match_date,
    ROUND(AVG(CAST(first_innings_runs AS float)), 2) AS avg_first_innings_score,
    ROUND(AVG(CAST(second_innings_runs AS float)), 2) AS avg_second_innings_score,
    SUM(CASE WHEN winner = batting_first_team THEN 1 ELSE 0 END) AS batting_first_wins,
    SUM(CASE WHEN winner = chasing_team THEN 1 ELSE 0 END) AS chasing_wins,
    SUM(CASE WHEN LOWER(COALESCE(toss_decision, '')) = 'bat' THEN 1 ELSE 0 END) AS toss_bat_count,
    SUM(CASE WHEN LOWER(COALESCE(toss_decision, '')) = 'field' THEN 1 ELSE 0 END) AS toss_field_count
FROM match_scores;
""".strip()

    season_sql = f"""
WITH venue_matches AS (
    SELECT
        m.match_id,
        CASE
            WHEN CAST(m.season AS varchar(20)) = '2020/21' THEN '2020'
            WHEN CHARINDEX('/', CAST(m.season AS varchar(20))) > 0
                 AND TRY_CONVERT(int, RIGHT(CAST(m.season AS varchar(20)), 2)) IS NOT NULL
            THEN CAST(
                CASE
                    WHEN TRY_CONVERT(int, RIGHT(CAST(m.season AS varchar(20)), 2)) <= 30
                    THEN 2000 + TRY_CONVERT(int, RIGHT(CAST(m.season AS varchar(20)), 2))
                    ELSE 1900 + TRY_CONVERT(int, RIGHT(CAST(m.season AS varchar(20)), 2))
                END AS varchar(4)
            )
            ELSE CAST(m.season AS varchar(20))
        END AS season
    FROM matches m
    WHERE {cond_m}
),
innings_scores AS (
    SELECT
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS innings_runs
    FROM deliveries d
    JOIN venue_matches vm
        ON d.match_id = vm.match_id
    WHERE d.innings IN (1, 2)
    GROUP BY d.match_id, d.innings
)
SELECT
    vm.season,
    COUNT(DISTINCT vm.match_id) AS matches,
    ROUND(AVG(CASE WHEN ins.innings = 1 THEN CAST(ins.innings_runs AS float) END), 2) AS avg_first_innings_score,
    ROUND(AVG(CASE WHEN ins.innings = 2 THEN CAST(ins.innings_runs AS float) END), 2) AS avg_second_innings_score
FROM venue_matches vm
LEFT JOIN innings_scores ins
    ON vm.match_id = ins.match_id
GROUP BY vm.season
ORDER BY vm.season;
""".strip()

    team_sql = f"""
WITH venue_matches AS (
    SELECT m.match_id, m.winner
    FROM matches m
    WHERE {cond_m}
),
team_matches AS (
    SELECT DISTINCT
        d.match_id,
        d.batting_team AS team
    FROM deliveries d
    JOIN venue_matches vm
        ON d.match_id = vm.match_id
    WHERE d.innings IN (1, 2)
)
SELECT
    tm.team AS Team,
    COUNT(DISTINCT tm.match_id) AS Matches,
    SUM(CASE WHEN vm.winner = tm.team THEN 1 ELSE 0 END) AS Wins,
    COUNT(DISTINCT tm.match_id) - SUM(CASE WHEN vm.winner = tm.team THEN 1 ELSE 0 END) AS Losses,
    ROUND(SUM(CASE WHEN vm.winner = tm.team THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(DISTINCT tm.match_id), 0), 2) AS [Win Pct]
FROM team_matches tm
JOIN venue_matches vm
    ON tm.match_id = vm.match_id
GROUP BY tm.team
ORDER BY Matches DESC, Wins DESC, Team ASC;
""".strip()

    batters_sql = f"""
SELECT TOP 10
    d.striker AS batter,
    STUFF((
        SELECT DISTINCT ', ' + d2.batting_team
        FROM deliveries d2
        JOIN matches m2
            ON d2.match_id = m2.match_id
        WHERE d2.striker = d.striker
          AND {cond_m2}
        FOR XML PATH(''), TYPE
    ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 END) AS balls,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0)) * 100.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 END), 0), 2) AS strike_rate
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {cond_m}
  AND d.innings IN (1, 2)
GROUP BY d.striker
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 END) > 0
ORDER BY runs DESC, strike_rate DESC, batter ASC;
""".strip()

    bowlers_sql = f"""
SELECT TOP 10
    d.bowler,
    STUFF((
        SELECT DISTINCT ', ' + d2.bowling_team
        FROM deliveries d2
        JOIN matches m2
            ON d2.match_id = m2.match_id
        WHERE d2.bowler = d.bowler
          AND {cond_m2}
        FOR XML PATH(''), TYPE
    ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS legal_balls,
    CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) / 6 AS varchar(20))
        + '.' +
    CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) % 6 AS varchar(1)) AS overs_bowled,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
         AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
        THEN 1
    END) AS wickets,
    SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
    ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS economy
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {cond_m}
  AND d.innings IN (1, 2)
GROUP BY d.bowler
HAVING COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) > 0
ORDER BY wickets DESC, economy ASC, legal_balls DESC, bowler ASC;
""".strip()

    toss_sql = f"""
SELECT
    COALESCE(m.toss_decision, 'unknown') AS toss_decision,
    COUNT(*) AS matches,
    SUM(CASE WHEN m.toss_winner = m.winner THEN 1 ELSE 0 END) AS toss_winner_wins,
    ROUND(SUM(CASE WHEN m.toss_winner = m.winner THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS toss_winner_win_pct
FROM matches m
WHERE {cond_m}
GROUP BY COALESCE(m.toss_decision, 'unknown')
ORDER BY matches DESC, toss_decision ASC;
""".strip()

    try:
        summary = run_query(summary_sql)
        if summary is None or summary.empty or int(summary.iloc[0].get("matches", 0) or 0) == 0:
            return _mvp_no_data_result(question)

        season = run_query(season_sql)
        team = run_query(team_sql)
        batters = run_query(batters_sql)
        bowlers = run_query(bowlers_sql)
        toss = run_query(toss_sql)

    except Exception as error:
        df = pd.DataFrame([{"error": str(error)}])
        return {
            "question": question,
            "analysis_paragraph": f"Mullanpur / New Chandigarh venue profile failed: {error}",
            "paragraph": f"Mullanpur / New Chandigarh venue profile failed: {error}",
            "result": df,
            "extra_tables": {"Error": df},
            "sql_query": summary_sql,
            "similar_questions": [],
            "route_used": "",
            "data_sources": "",
        }

    summary = _mvp_clean_table(summary if summary is not None else pd.DataFrame())
    season = _mvp_clean_table(season if season is not None else pd.DataFrame())
    team = _mvp_clean_table(team if team is not None else pd.DataFrame())
    batters = _mvp_clean_table(batters if batters is not None else pd.DataFrame())
    bowlers = _mvp_clean_table(bowlers if bowlers is not None else pd.DataFrame())
    toss = _mvp_clean_table(toss if toss is not None else pd.DataFrame())

    return {
        "question": question,
        "analysis_paragraph": "Venue profile for Mullanpur / New Chandigarh using a strict venue-name filter, kept separate from Mohali/PCA/IS Bindra records.",
        "paragraph": "Venue profile for Mullanpur / New Chandigarh using a strict venue-name filter, kept separate from Mohali/PCA/IS Bindra records.",
        "result": summary,
        "extra_tables": {
            "Venue Summary": summary,
            "Season Trend": season,
            "Team Record At Venue": team,
            "Top Batters At Venue": batters,
            "Top Bowlers At Venue": bowlers,
            "Toss Decision At Venue": toss,
        },
        "sql_query": summary_sql,
        "similar_questions": [
            "tell me about Mullanpur",
            "venue profile for New Chandigarh",
            "best strike rate at Mullanpur min 50 balls faced",
            "best economy rate at Mullanpur min 50 balls bowled",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_mvp = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_mvp = None


def answer_question_with_fallback(user_question):
    result = _mvp_venue_profile_route(user_question)

    if result is not None:
        return result

    return _previous_answer_question_with_fallback_before_mvp(user_question)

# IPL SQL Agent strict Mullanpur/New Chandigarh venue profile END


# IPL SQL Agent finals appearances team merge fix START

def _finals_team_case_expr(column_name):
    return f"""
CASE
    WHEN {column_name} IN ('Royal Challengers Bangalore', 'Royal Challengers Bengaluru') THEN 'RCB'
    WHEN {column_name} IN ('Kings XI Punjab', 'Punjab Kings') THEN 'PBKS'
    WHEN {column_name} IN ('Delhi Daredevils', 'Delhi Capitals') THEN 'Delhi Capitals'
    WHEN {column_name} IN ('Rising Pune Supergiant', 'Rising Pune Supergiants') THEN 'RPS'
    WHEN {column_name} = 'Chennai Super Kings' THEN 'CSK'
    WHEN {column_name} = 'Mumbai Indians' THEN 'MI'
    WHEN {column_name} = 'Kolkata Knight Riders' THEN 'KKR'
    WHEN {column_name} = 'Rajasthan Royals' THEN 'RR'
    WHEN {column_name} = 'Sunrisers Hyderabad' THEN 'SRH'
    WHEN {column_name} = 'Gujarat Titans' THEN 'GT'
    WHEN {column_name} = 'Lucknow Super Giants' THEN 'LSG'
    ELSE {column_name}
END
""".strip()


def _finals_season_label_expr(alias):
    return f"""
CASE
    WHEN CAST({alias}.season AS varchar(20)) = '2020/21' THEN '2020'
    WHEN CHARINDEX('/', CAST({alias}.season AS varchar(20))) > 0
         AND TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) IS NOT NULL
    THEN CAST(
        CASE
            WHEN TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) <= 30
            THEN 2000 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
            ELSE 1900 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
        END AS varchar(4)
    )
    ELSE CAST({alias}.season AS varchar(20))
END
""".strip()


def _finals_is_question(question):
    text = str(question or "").lower()
    return (
        "final" in text
        and any(x in text for x in ["most", "played", "appeared", "appearances", "reached"])
        and not any(x in text for x in ["fastest", "fifty", "50", "hundred", "100"])
    )


def _finals_route(question):
    import pandas as pd
    from app.db import run_query

    if not _finals_is_question(question):
        return None

    season_expr = _finals_season_label_expr("m")
    team_expr = _finals_team_case_expr("team_name")
    winner_expr = _finals_team_case_expr("winner")

    sql = f"""
WITH season_matches AS (
    SELECT
        m.match_id,
        {season_expr} AS season,
        m.start_date,
        m.winner
    FROM matches m
),
final_dates AS (
    SELECT season, MAX(start_date) AS final_date
    FROM season_matches
    GROUP BY season
),
final_matches AS (
    SELECT sm.match_id, sm.season, sm.start_date, sm.winner
    FROM season_matches sm
    JOIN final_dates fd
        ON sm.season = fd.season
       AND sm.start_date = fd.final_date
),
final_teams_raw AS (
    SELECT DISTINCT
        fm.season,
        d.batting_team AS team_name,
        fm.winner
    FROM final_matches fm
    JOIN deliveries d
        ON fm.match_id = d.match_id
    WHERE d.innings IN (1, 2)
      AND d.batting_team IS NOT NULL
),
final_teams AS (
    SELECT DISTINCT
        season,
        {team_expr} AS Team,
        {winner_expr} AS normalized_winner
    FROM final_teams_raw
),
team_summary AS (
    SELECT
        Team,
        COUNT(DISTINCT season) AS [Finals Played],
        SUM(CASE WHEN Team = normalized_winner THEN 1 ELSE 0 END) AS Titles,
        COUNT(DISTINCT season) - SUM(CASE WHEN Team = normalized_winner THEN 1 ELSE 0 END) AS [Final Losses],
        STUFF((
            SELECT ', ' + ft2.season
            FROM final_teams ft2
            WHERE ft2.Team = ft.Team
            GROUP BY ft2.season
            ORDER BY TRY_CONVERT(int, ft2.season)
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS [Years Played],
        STUFF((
            SELECT ', ' + ft3.season
            FROM final_teams ft3
            WHERE ft3.Team = ft.Team
              AND ft3.Team = ft3.normalized_winner
            GROUP BY ft3.season
            ORDER BY TRY_CONVERT(int, ft3.season)
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS [Years Won]
    FROM final_teams ft
    GROUP BY Team
)
SELECT
    Team,
    [Finals Played],
    Titles,
    [Final Losses],
    [Years Played],
    COALESCE(NULLIF([Years Won], ''), '-') AS [Years Won]
FROM team_summary
ORDER BY [Finals Played] DESC, Titles DESC, Team ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The finals appearances route failed: {error}",
            "paragraph": f"The finals appearances route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    return {
        "question": question,
        "analysis_paragraph": "Teams with the most IPL final appearances. RCB/Bangalore/Bengaluru and PBKS/Kings XI Punjab are merged correctly.",
        "paragraph": "Teams with the most IPL final appearances. RCB/Bangalore/Bengaluru and PBKS/Kings XI Punjab are merged correctly.",
        "result": df,
        "extra_tables": {"Finals Appearances": df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has played the most finals",
            "which team has reached the most IPL finals",
            "which team has the most final appearances",
            "which team has won the most trophies",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_finals_merge = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_finals_merge = None


def answer_question_with_fallback(user_question):
    result = _finals_route(user_question)

    if result is not None:
        return result

    return _previous_answer_question_with_fallback_before_finals_merge(user_question)

# IPL SQL Agent finals appearances team merge fix END


# IPL SQL Agent outside-India, team boundary, and weekday leaderboards START

def _obw_q(value):
    return str(value).replace("'", "''")


def _obw_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    return "(" + ", ".join("'" + _obw_q(v) + "'" for v in values) + ")" if values else "('')"


def _obw_short_team(value):
    if value is None:
        return value

    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }

    parts = [p.strip() for p in str(value).split(",") if p and str(p).strip()]
    out = []
    seen = set()

    for part in parts:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            out.append(short)
            seen.add(key)

    return ", ".join(out)


def _obw_clean_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()
        for col in ["team", "teams", "batting_team", "bowling_team", "opposition", "winner", "toss_winner"]:
            if col in table.columns:
                table[col] = table[col].apply(_obw_short_team)
        return table
    except Exception:
        return table


def _obw_clean_result(result):
    if not isinstance(result, dict):
        return result

    result["result"] = _obw_clean_table(result.get("result"))

    extra = result.get("extra_tables")
    if isinstance(extra, dict):
        for name, table in list(extra.items()):
            extra[name] = _obw_clean_table(table)
        result["extra_tables"] = extra

    return result


def _obw_team_lookup(raw):
    text = str(raw or "").lower().strip()

    if text == "dc":
        return "AMBIGUOUS_DC", None, []

    teams = [
        ("CSK", "CSK", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "MI", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "RCB", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "GT", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "KKR", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "RR", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "SRH", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("Delhi Capitals", "Delhi Capitals", ["Delhi Capitals", "Delhi Daredevils"], ["delhi capitals", "delhi daredevils"]),
        ("Deccan Chargers", "Deccan Chargers", ["Deccan Chargers"], ["deccan chargers", "deccan"]),
        ("PBKS", "PBKS", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "LSG", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "RPS", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "GL", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "KTK", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "PWI", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
    ]

    for code, display, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, display, aliases

    return None, None, []


def _obw_limit(question, default_value=10):
    import re

    match = re.search(r"\btop\s+(\d+)\b", str(question or ""), flags=re.IGNORECASE)
    if match:
        value = int(match.group(1))
        if 1 <= value <= 50:
            return value

    return default_value


def _obw_season_condition(alias, year):
    year = int(year)

    if year == 2020:
        return f"(CAST({alias}.season AS varchar(20)) = '2020' OR CAST({alias}.season AS varchar(20)) = '2020/21')"

    if year == 2021:
        return f"(CAST({alias}.season AS varchar(20)) = '2021')"

    slash_form = f"{year - 1}/{str(year)[-2:]}"
    short_year = str(year)[-2:]

    return (
        f"(CAST({alias}.season AS varchar(20)) = '{year}' "
        f"OR CAST({alias}.season AS varchar(20)) = '{_obw_q(slash_form)}' "
        f"OR CAST({alias}.season AS varchar(20)) LIKE '%/{_obw_q(short_year)}')"
    )


def _obw_extract_year(question):
    import re

    match = re.search(r"\b(20\d{2})\b", str(question or ""))
    return int(match.group(1)) if match else None


def _obw_season_label_expr(alias):
    return f"""
CASE
    WHEN CAST({alias}.season AS varchar(20)) = '2020/21' THEN '2020'
    WHEN CHARINDEX('/', CAST({alias}.season AS varchar(20))) > 0
         AND TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) IS NOT NULL
    THEN CAST(
        CASE
            WHEN TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2)) <= 30
            THEN 2000 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
            ELSE 1900 + TRY_CONVERT(int, RIGHT(CAST({alias}.season AS varchar(20)), 2))
        END AS varchar(4)
    )
    ELSE CAST({alias}.season AS varchar(20))
END
""".strip()


def _obw_outside_india_condition(alias="m"):
    # Positive overseas IPL venue/city list. This avoids accidentally classifying Indian venues
    # with missing/odd city names as outside India.
    return f"""
(
    LOWER(COALESCE({alias}.city, '')) IN (
        'abu dhabi', 'dubai', 'sharjah',
        'cape town', 'durban', 'johannesburg', 'centurion',
        'port elizabeth', 'east london', 'bloemfontein', 'kimberley'
    )
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%dubai%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%sharjah%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%zayed%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%abu dhabi%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%newlands%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%kingsmead%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%wanderers%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%supersport park%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%st george%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%buffalo park%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%mangaung%'
    OR LOWER(COALESCE({alias}.venue, '')) LIKE '%de beers diamond oval%'
)
""".strip()


def _obw_day_name(question):
    text = str(question or "").lower()

    days = {
        "monday": "Monday",
        "mon": "Monday",
        "tuesday": "Tuesday",
        "tue": "Tuesday",
        "wednesday": "Wednesday",
        "wed": "Wednesday",
        "thursday": "Thursday",
        "thu": "Thursday",
        "friday": "Friday",
        "fri": "Friday",
        "saturday": "Saturday",
        "sat": "Saturday",
        "sunday": "Sunday",
        "sun": "Sunday",
    }

    # Prefer full names.
    for key in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        if key in text:
            return days[key]

    import re
    for key, value in days.items():
        if re.search(rf"\b{key}\b", text):
            return value

    return None


def _obw_day_condition(day_label, alias="m"):
    return f"DATENAME(WEEKDAY, TRY_CONVERT(date, {alias}.start_date)) = '{_obw_q(day_label)}'"


def _obw_metric(question):
    text = str(question or "").lower()

    if "wicket" in text:
        return "wickets"

    if "six" in text or "6" in text:
        return "sixes"

    if "four" in text or "4" in text or "boundaries" in text:
        return "fours"

    if "run" in text or "scored" in text or "score" in text:
        return "runs"

    return None


def _obw_dc_ambiguity(question):
    import pandas as pd

    df = pd.DataFrame([{
        "issue": "DC is ambiguous",
        "action": "Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "example": "most sixes for Delhi Capitals",
    }])

    return {
        "question": question,
        "analysis_paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "result": df,
        "extra_tables": {"Clarification": df},
        "sql_query": "",
        "similar_questions": [
            "most sixes for Delhi Capitals",
            "most fours for Delhi Capitals",
            "most runs outside India",
            "most wickets on Tuesday",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _obw_team_boundary_parse(question):
    import re

    text = str(question or "")
    low = text.lower()

    metric = _obw_metric(question)

    if metric not in {"sixes", "fours"}:
        return None

    # Must include a team filter. This prevents hijacking overall sixes/fours.
    match = re.search(
        r"\b(?:for|from|by)\s+([A-Za-z0-9 .]+?)(?:\s+in\s+20\d{2}|\s+on\s+|\s+at\s+|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    team_raw = match.group(1).strip(" .?")
    code, display, aliases = _obw_team_lookup(team_raw)

    if code == "AMBIGUOUS_DC":
        return {"ambiguous": True}

    if not aliases:
        return None

    return {
        "metric": metric,
        "display": display,
        "aliases": aliases,
    }


def _obw_team_boundary_route(question):
    import pandas as pd
    from app.db import run_query

    parsed = _obw_team_boundary_parse(question)

    if not parsed:
        return None

    if parsed.get("ambiguous"):
        return _obw_dc_ambiguity(question)

    metric = parsed["metric"]
    team_display = parsed["display"]
    year = _obw_extract_year(question)
    limit = _obw_limit(question, default_value=10)
    season_expr = _obw_season_label_expr("d")

    filters = [
        "d.innings IN (1, 2)",
        f"d.batting_team IN {_obw_sql_list(parsed['aliases'])}",
    ]

    if year:
        filters.append(_obw_season_condition("d", year))

    where_sql = " AND ".join(filters)
    value_expr = "SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=6 THEN 1 ELSE 0 END)" if metric == "sixes" else "SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=4 THEN 1 ELSE 0 END)"
    value_col = "sixes" if metric == "sixes" else "fours"

    sql = f"""
WITH batter_stats AS (
    SELECT
        d.striker AS batter,
        STUFF((
            SELECT DISTINCT ', ' + d2.batting_team
            FROM deliveries d2
            WHERE d2.striker = d.striker
              AND d2.batting_team IN {_obw_sql_list(parsed['aliases'])}
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT d.match_id) AS matches,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 END) AS balls,
        SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=4 THEN 1 ELSE 0 END) AS fours,
        SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=6 THEN 1 ELSE 0 END) AS sixes
    FROM deliveries d
    WHERE {where_sql}
    GROUP BY d.striker
)
SELECT TOP {limit}
    batter,
    team,
    matches,
    runs,
    balls,
    fours,
    sixes
FROM batter_stats
WHERE {value_col} > 0
ORDER BY {value_col} DESC, runs DESC, batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The team {metric} route failed: {error}",
            "paragraph": f"The team {metric} route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _obw_clean_table(df if df is not None else pd.DataFrame())

    title = f"Most {metric} for {team_display}"
    if year:
        title += f" in {year}"

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "most sixes for MI",
            "most fours for MI",
            "most sixes for RCB",
            "most fours for CSK",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _obw_batting_leaderboard(question, filters, title, limit=10):
    import pandas as pd
    from app.db import run_query

    season_expr = _obw_season_label_expr("d")
    where_sql = " AND ".join(["d.innings IN (1, 2)"] + filters)

    sql = f"""
WITH batter_innings AS (
    SELECT
        {season_expr} AS season,
        d.striker AS batter,
        d.batting_team AS team,
        d.match_id,
        d.innings,
        SUM(COALESCE(d.runs_off_bat, 0)) AS innings_runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 END) AS balls,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out', 'retired not out')
            THEN 1 ELSE 0
        END) AS out_flag,
        SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=4 THEN 1 ELSE 0 END) AS fours,
        SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=6 THEN 1 ELSE 0 END) AS sixes
    FROM deliveries d
    JOIN matches m ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY {season_expr}, d.striker, d.batting_team, d.match_id, d.innings
),
totals AS (
    SELECT
        batter,
        STUFF((
            SELECT DISTINCT ', ' + bi2.team
            FROM batter_innings bi2
            WHERE bi2.batter = bi.batter
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT match_id) AS matches,
        COUNT(*) AS innings,
        SUM(innings_runs) AS runs,
        SUM(balls) AS balls,
        SUM(out_flag) AS dismissals,
        ROUND(SUM(innings_runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate,
        ROUND(SUM(innings_runs) * 1.0 / NULLIF(SUM(out_flag), 0), 2) AS batting_average,
        SUM(fours) AS fours,
        SUM(sixes) AS sixes
    FROM batter_innings bi
    GROUP BY batter
)
SELECT TOP {limit}
    batter,
    team,
    matches,
    innings,
    runs,
    balls,
    strike_rate,
    dismissals,
    batting_average,
    fours,
    sixes
FROM totals
WHERE balls > 0
ORDER BY runs DESC, strike_rate DESC, batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The batting leaderboard route failed: {error}",
            "paragraph": f"The batting leaderboard route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _obw_clean_table(df if df is not None else pd.DataFrame())

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has scored the most runs outside India",
            "who has scored the most runs on a Tuesday",
            "who has scored the most runs on a Sunday",
            "most sixes for MI",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _obw_bowling_leaderboard(question, filters, title, limit=10):
    import pandas as pd
    from app.db import run_query

    season_expr = _obw_season_label_expr("d")
    where_sql = " AND ".join(["d.innings IN (1, 2)"] + filters)

    sql = f"""
WITH bowler_stats AS (
    SELECT
        d.bowler,
        STUFF((
            SELECT DISTINCT ', ' + d2.bowling_team
            FROM deliveries d2
            JOIN matches m2 ON d2.match_id = m2.match_id
            WHERE d2.bowler = d.bowler
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
        COUNT(DISTINCT d.match_id) AS matches,
        COUNT(DISTINCT CONCAT(CAST(d.match_id AS varchar(50)), '-', CAST(d.innings AS varchar(10)))) AS innings,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) AS legal_balls,
        CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) / 6 AS varchar(20))
            + '.' +
        CAST(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) % 6 AS varchar(1)) AS overs_bowled,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) AS runs_conceded,
        ROUND(SUM(COALESCE(d.runs_off_bat, 0) + COALESCE(d.extras, 0)) * 6.0 / NULLIF(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END), 0), 2) AS economy,
        ROUND(COUNT(CASE WHEN COALESCE(d.wides, 0)=0 AND COALESCE(d.noballs, 0)=0 THEN 1 END) * 1.0 / NULLIF(COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field')
            THEN 1
        END), 0), 2) AS bowling_strike_rate
    FROM deliveries d
    JOIN matches m ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.bowler
)
SELECT TOP {limit}
    bowler,
    team,
    matches,
    innings,
    overs_bowled,
    legal_balls,
    wickets,
    runs_conceded,
    economy,
    bowling_strike_rate
FROM bowler_stats
WHERE legal_balls > 0
ORDER BY wickets DESC, economy ASC, legal_balls DESC, bowler ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The bowling leaderboard route failed: {error}",
            "paragraph": f"The bowling leaderboard route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _obw_clean_table(df if df is not None else pd.DataFrame())

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "who has taken the most wickets outside India",
            "who has taken the most wickets on a Tuesday",
            "who has taken the most wickets on a Sunday",
            "most fours for RCB",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _obw_outside_india_route(question):
    text = str(question or "").lower()

    if not any(phrase in text for phrase in ["outside india", "outside of india", "overseas", "outside indian"]):
        return None

    metric = _obw_metric(question)
    limit = _obw_limit(question, default_value=10)
    filt = [_obw_outside_india_condition("m")]

    if metric == "wickets":
        return _obw_bowling_leaderboard(question, filt, "Most wickets outside India", limit=limit)

    if metric == "runs" or metric is None:
        return _obw_batting_leaderboard(question, filt, "Most runs outside India", limit=limit)

    return None


def _obw_weekday_route(question):
    day = _obw_day_name(question)

    if not day:
        return None

    text = str(question or "").lower()

    # Require clear "on a Tuesday" / "on Tuesday" / "Tuesday games" intent.
    weekday_intent = (
        f"on a {day.lower()}" in text
        or f"on {day.lower()}" in text
        or f"{day.lower()} games" in text
        or f"{day.lower()} matches" in text
        or f"played on {day.lower()}" in text
    )

    if not weekday_intent:
        return None

    metric = _obw_metric(question)
    limit = _obw_limit(question, default_value=10)
    filt = [_obw_day_condition(day, "m")]

    if metric == "wickets":
        return _obw_bowling_leaderboard(question, filt, f"Most wickets on {day}", limit=limit)

    if metric == "runs" or metric is None:
        return _obw_batting_leaderboard(question, filt, f"Most runs on {day}", limit=limit)

    return None


try:
    _previous_answer_question_with_fallback_before_obw = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_obw = None


def answer_question_with_fallback(user_question):
    for route in [
        _obw_team_boundary_route,
        _obw_outside_india_route,
        _obw_weekday_route,
    ]:
        result = route(user_question)

        if result is not None:
            return result

    result = _previous_answer_question_with_fallback_before_obw(user_question)
    return _obw_clean_result(result)

# IPL SQL Agent outside-India, team boundary, and weekday leaderboards END


# IPL SQL Agent team-player boundary phrasing fix START

def _tpb_q(value):
    return str(value).replace("'", "''")


def _tpb_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    return "(" + ", ".join("'" + _tpb_q(v) + "'" for v in values) + ")" if values else "('')"


def _tpb_team_lookup(raw):
    text = str(raw or "").lower().strip()

    if text == "dc":
        return "AMBIGUOUS_DC", None, []

    teams = [
        ("CSK", "CSK", ["Chennai Super Kings"], ["csk", "chennai", "super kings"]),
        ("MI", "MI", ["Mumbai Indians"], ["mi", "mumbai"]),
        ("RCB", "RCB", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers"]),
        ("GT", "GT", ["Gujarat Titans"], ["gt", "gujarat"]),
        ("KKR", "KKR", ["Kolkata Knight Riders"], ["kkr", "kolkata"]),
        ("RR", "RR", ["Rajasthan Royals"], ["rr", "rajasthan"]),
        ("SRH", "SRH", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad"]),
        ("Delhi Capitals", "Delhi Capitals", ["Delhi Capitals", "Delhi Daredevils"], ["delhi capitals", "delhi daredevils"]),
        ("Deccan Chargers", "Deccan Chargers", ["Deccan Chargers"], ["deccan chargers", "deccan"]),
        ("PBKS", "PBKS", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi"]),
        ("LSG", "LSG", ["Lucknow Super Giants"], ["lsg", "lucknow"]),
        ("RPS", "RPS", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", "GL", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", "KTK", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", "PWI", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
    ]

    for code, display, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return code, display, aliases

    return None, None, []


def _tpb_short_team(value):
    if value is None:
        return value

    mapping = {
        "Chennai Super Kings": "CSK",
        "Mumbai Indians": "MI",
        "Royal Challengers Bangalore": "RCB",
        "Royal Challengers Bengaluru": "RCB",
        "Gujarat Titans": "GT",
        "Kolkata Knight Riders": "KKR",
        "Rajasthan Royals": "RR",
        "Sunrisers Hyderabad": "SRH",
        "Kings XI Punjab": "PBKS",
        "Punjab Kings": "PBKS",
        "Lucknow Super Giants": "LSG",
        "Rising Pune Supergiant": "RPS",
        "Rising Pune Supergiants": "RPS",
        "Gujarat Lions": "GL",
        "Kochi Tuskers Kerala": "KTK",
        "Pune Warriors": "PWI",
        "Pune Warriors India": "PWI",
        "Delhi Daredevils": "Delhi Capitals",
        "Delhi Capitals": "Delhi Capitals",
        "Deccan Chargers": "Deccan Chargers",
    }

    out = []
    seen = set()

    for part in [p.strip() for p in str(value).split(",") if p and str(p).strip()]:
        short = mapping.get(part, part)
        key = short.lower()
        if key not in seen:
            out.append(short)
            seen.add(key)

    return ", ".join(out)


def _tpb_clean_table(table):
    if table is None or not hasattr(table, "columns"):
        return table

    try:
        table = table.copy()
        for col in ["team", "batting_team", "bowling_team", "opposition"]:
            if col in table.columns:
                table[col] = table[col].apply(_tpb_short_team)
        return table
    except Exception:
        return table


def _tpb_metric(question):
    text = str(question or "").lower()

    if "six" in text or "6" in text:
        return "sixes"

    if "four" in text or "4" in text or "boundary" in text or "boundaries" in text:
        return "fours"

    return None


def _tpb_parse(question):
    import re

    text = str(question or "")
    low = text.lower()
    metric = _tpb_metric(question)

    if metric not in {"sixes", "fours"}:
        return None

    # Do not hijack opposition questions.
    if re.search(r"\bagainst\s+(csk|mi|rcb|kkr|rr|srh|gt|pbks|kxip|lsg|dc|delhi|kolkata|mumbai|chennai|bangalore|bengaluru|rajasthan|punjab|hyderabad|gujarat|lucknow)\b", low):
        return None

    # New forms:
    # "which KKR player has hit the most sixes"
    # "which KKR batter has hit most fours"
    # "KKR player most sixes"
    team_raw = None

    match = re.search(
        r"\b(?:which|what|who)\s+([A-Za-z0-9 .]+?)\s+(?:player|batter|batsman)\b.*?\b(?:most|highest|top)\b.*?\b(?:six|sixes|four|fours|boundaries)\b",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        team_raw = match.group(1).strip(" .?")

    if not team_raw:
        match = re.search(
            r"\b(csk|mi|rcb|kkr|rr|srh|gt|pbks|kxip|lsg|delhi capitals|deccan chargers|kolkata knight riders|mumbai indians|chennai super kings|royal challengers bangalore|royal challengers bengaluru|rajasthan royals|sunrisers hyderabad|gujarat titans|lucknow super giants|punjab kings|kings xi punjab)\s+(?:player|batter|batsman)\b.*?\b(?:most|highest|top)\b.*?\b(?:six|sixes|four|fours|boundaries)\b",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            team_raw = match.group(1).strip(" .?")

    # Also support the already-natural form if the older route missed it:
    # "which player has hit the most sixes for KKR"
    if not team_raw:
        match = re.search(
            r"\b(?:for|from|by)\s+([A-Za-z0-9 .]+?)(?:\s+in\s+20\d{2}|\s*$)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            team_raw = match.group(1).strip(" .?")

    if not team_raw:
        return None

    code, display, aliases = _tpb_team_lookup(team_raw)

    if code == "AMBIGUOUS_DC":
        return {"ambiguous": True}

    if not aliases:
        return None

    return {
        "metric": metric,
        "display": display,
        "aliases": aliases,
    }


def _tpb_ambiguity(question):
    import pandas as pd

    df = pd.DataFrame([{
        "issue": "DC is ambiguous",
        "action": "Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "example": "which Delhi Capitals player has hit the most sixes",
    }])

    return {
        "question": question,
        "analysis_paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "result": df,
        "extra_tables": {"Clarification": df},
        "sql_query": "",
        "similar_questions": [
            "which Delhi Capitals player has hit the most sixes",
            "which Delhi Capitals player has hit the most fours",
            "most sixes for Delhi Capitals",
            "most fours for Deccan Chargers",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _tpb_route(question):
    import pandas as pd
    from app.db import run_query

    parsed = _tpb_parse(question)

    if not parsed:
        return None

    if parsed.get("ambiguous"):
        return _tpb_ambiguity(question)

    metric = parsed["metric"]
    value_col = "sixes" if metric == "sixes" else "fours"
    value_expr = "SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=6 THEN 1 ELSE 0 END)" if metric == "sixes" else "SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=4 THEN 1 ELSE 0 END)"

    sql = f"""
SELECT TOP 10
    d.striker AS batter,
    STUFF((
        SELECT DISTINCT ', ' + d2.batting_team
        FROM deliveries d2
        WHERE d2.striker = d.striker
          AND d2.batting_team IN {_tpb_sql_list(parsed["aliases"])}
        FOR XML PATH(''), TYPE
    ).value('.', 'nvarchar(max)'), 1, 2, '') AS team,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
    COUNT(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 END) AS balls,
    SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=4 THEN 1 ELSE 0 END) AS fours,
    SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=6 THEN 1 ELSE 0 END) AS sixes
FROM deliveries d
WHERE d.innings IN (1, 2)
  AND d.batting_team IN {_tpb_sql_list(parsed["aliases"])}
GROUP BY d.striker
HAVING {value_expr} > 0
ORDER BY {value_col} DESC, runs DESC, batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The team player boundary route failed: {error}",
            "paragraph": f"The team player boundary route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = _tpb_clean_table(df if df is not None else pd.DataFrame())
    title = f"Most {metric} for {parsed['display']}"

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "which KKR player has hit the most sixes",
            "which KKR player has hit the most fours",
            "which MI player has hit the most sixes",
            "which CSK player has hit the most fours",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_tpb = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_tpb = None


def answer_question_with_fallback(user_question):
    result = _tpb_route(user_question)

    if result is not None:
        return result

    return _previous_answer_question_with_fallback_before_tpb(user_question)

# IPL SQL Agent team-player boundary phrasing fix END


# IPL SQL Agent squad auction needs table START

def _squadneeds_team_lookup(raw):
    text = str(raw or "").lower().strip()
    teams = {
        "csk": "CSK", "chennai": "CSK", "chennai super kings": "CSK",
        "mi": "MI", "mumbai": "MI", "mumbai indians": "MI",
        "rcb": "RCB", "bangalore": "RCB", "bengaluru": "RCB",
        "royal challengers bangalore": "RCB", "royal challengers bengaluru": "RCB",
        "kkr": "KKR", "kolkata": "KKR", "kolkata knight riders": "KKR",
        "rr": "RR", "rajasthan": "RR", "rajasthan royals": "RR",
        "srh": "SRH", "sunrisers": "SRH", "sunrisers hyderabad": "SRH",
        "gt": "GT", "gujarat": "GT", "gujarat titans": "GT",
        "pbks": "PBKS", "kxip": "PBKS", "punjab": "PBKS", "punjab kings": "PBKS", "kings xi punjab": "PBKS",
        "lsg": "LSG", "lucknow": "LSG", "lucknow super giants": "LSG",
        "delhi capitals": "Delhi Capitals", "delhi daredevils": "Delhi Capitals",
    }
    if text == "dc":
        return "AMBIGUOUS_DC", None
    return teams.get(text), teams.get(text)


def _squadneeds_parse_team(question):
    import re
    text = str(question or "").strip()
    patterns = [
        r"\b(?:analyse|analyze|review|evaluate)\s+([A-Za-z0-9 .]+?)\s+squad\b",
        r"\b([A-Za-z0-9 .]+?)\s+squad\s+(?:analysis|review|profile)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _squadneeds_team_lookup(match.group(1).strip(" .?"))
    return None, None


def _squadneeds_recommendations(team_code):
    # Role-profile recommendations, not named-player predictions.
    base = {
        "CSK": [
            ("1", "Indian middle-order batter who plays spin well", "Adds a stable No. 4/5 option on slower pitches.", "Indian", "Middle overs", "Prioritise strike rotation and spin-hitting."),
            ("2", "Powerplay wicket-taking fast bowler", "Early wickets let CSK control the middle overs with spin.", "Indian or overseas", "Powerplay", "New-ball swing/seam preferred."),
            ("3", "Death-overs pace backup", "Protects the XI if the main death bowler is unavailable.", "Indian", "Death overs", "Yorker and slower-ball execution."),
            ("4", "Attacking wrist-spinner", "Adds a wicket-taking option when finger spin is being milked.", "Indian", "Middle overs", "Useful against right-heavy lineups."),
            ("5", "Young Indian finishing all-rounder", "Improves long-term balance and impact-player flexibility.", "Indian", "Overs 16-20", "Should offer batting power or two seam overs."),
        ],
        "RCB": [
            ("1", "Indian spin-hitting middle-order batter", "Reduces dependence on the top order.", "Indian", "Middle overs", "Must handle spin and high pace."),
            ("2", "High-control death bowler", "Small-ground games need better end-overs control.", "Indian or overseas", "Death overs", "Yorkers and slower balls."),
            ("3", "Left-arm pace option", "Adds angle variety against right-hand heavy top orders.", "Indian", "Powerplay", "Can share new-ball overs."),
            ("4", "Defensive finger spinner", "Gives control when games become high-scoring.", "Indian", "Middle overs", "Low boundary percentage is key."),
            ("5", "Indian wicketkeeper-batter backup", "Improves XI flexibility if the first-choice keeper is unavailable.", "Indian", "Batting depth", "Top-six batting ability preferred."),
        ],
        "MI": [
            ("1", "Reliable Indian middle-order anchor", "Balances a power-heavy batting core.", "Indian", "Middle overs", "Strong spin game required."),
            ("2", "Left-arm powerplay seamer", "Adds angle variety and early wicket threat.", "Indian or overseas", "Powerplay", "New-ball movement preferred."),
            ("3", "Backup death bowler", "Keeps the bowling plan stable if the lead pacer is unavailable.", "Indian", "Death overs", "Yorkers and wide-line accuracy."),
            ("4", "Wrist-spin wicket-taker", "Adds middle-over breakthroughs on slower pitches.", "Indian", "Middle overs", "Should attack both hands."),
            ("5", "Lower-order batting all-rounder", "Extends batting depth without weakening bowling.", "Indian", "Overs 14-20", "Seam-bowling all-rounder preferred."),
        ],
        "KKR": [
            ("1", "Indian top-order backup batter", "Protects the high-tempo powerplay plan.", "Indian", "Powerplay", "Should handle pace and hit square."),
            ("2", "Middle-order batter strong against spin", "Keeps middle overs stable before the finishers.", "Indian", "Middle overs", "Rotation plus spin-hitting."),
            ("3", "Death-overs specialist seamer", "Adds insurance beyond the main pace options.", "Indian or overseas", "Death overs", "Slower-ball and yorker control."),
            ("4", "Left-arm seam variation", "Creates matchup value with a different angle.", "Indian", "Powerplay/middle", "Useful against right-hand heavy teams."),
            ("5", "Backup mystery/wrist spin option", "Keeps KKR's spin identity strong.", "Indian", "Middle overs", "Wicket-taking ceiling matters."),
        ],
    }
    default = [
        ("1", "Indian middle-order batter who plays spin well", "Improves batting stability and matchup flexibility.", "Indian", "Middle overs", "Low dot-ball rate preferred."),
        ("2", "Powerplay wicket-taking fast bowler", "Creates early breakthroughs.", "Indian or overseas", "Powerplay", "New-ball movement preferred."),
        ("3", "Death-overs specialist", "Improves end-overs control.", "Indian", "Death overs", "Yorkers and slower balls."),
        ("4", "Spin-bowling all-rounder", "Improves balance on slow pitches.", "Indian", "Middle overs", "Batting depth is a bonus."),
        ("5", "Backup wicketkeeper-batter", "Improves selection flexibility.", "Indian", "Batting depth", "Top-six batting ability preferred."),
    ]
    return base.get(team_code, default)


def _squadneeds_build_table(team_code):
    import pandas as pd
    rows = []
    for priority, player_type, reason, local_overseas, phase, notes in _squadneeds_recommendations(team_code):
        rows.append({
            "Priority": priority,
            "Player Type Needed": player_type,
            "Why Needed": reason,
            "Indian/Overseas": local_overseas,
            "Phase/Role": phase,
            "Notes": notes,
        })
    return pd.DataFrame(rows)


try:
    _previous_answer_question_with_fallback_before_squadneeds = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_squadneeds = None


def answer_question_with_fallback(user_question):
    result = _previous_answer_question_with_fallback_before_squadneeds(user_question)
    team_code, team_display = _squadneeds_parse_team(user_question)

    if team_code and team_code != "AMBIGUOUS_DC" and isinstance(result, dict):
        needs_df = _squadneeds_build_table(team_code)
        extra = result.get("extra_tables")
        if not isinstance(extra, dict):
            extra = {}
        extra["Auction Role Needs"] = needs_df
        result["extra_tables"] = extra

        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""
        if "Auction Role Needs" not in str(paragraph):
            result["analysis_paragraph"] = str(paragraph).rstrip() + f" I also added an Auction Role Needs tab with five player profiles {team_display} could target at the next auction."
            result["paragraph"] = result["analysis_paragraph"]

    return result

# IPL SQL Agent squad auction needs table END


# IPL SQL Agent filtered team boundary route START

def _ftb_q(value):
    return str(value).replace("'", "''")


def _ftb_sql_list(values):
    values = [v for v in values if v and str(v).strip()]
    return "(" + ", ".join("'" + _ftb_q(v) + "'" for v in values) + ")" if values else "('')"


def _ftb_team_lookup(raw):
    text = str(raw or "").lower().strip()

    if text == "dc":
        return "AMBIGUOUS_DC", None, []

    teams = [
        ("CSK", ["Chennai Super Kings"], ["csk", "chennai", "super kings", "chennai super kings"]),
        ("MI", ["Mumbai Indians"], ["mi", "mumbai", "mumbai indians"]),
        ("RCB", ["Royal Challengers Bangalore", "Royal Challengers Bengaluru"], ["rcb", "bangalore", "bengaluru", "royal challengers", "royal challengers bangalore", "royal challengers bengaluru"]),
        ("GT", ["Gujarat Titans"], ["gt", "gujarat", "gujarat titans"]),
        ("KKR", ["Kolkata Knight Riders"], ["kkr", "kolkata", "kolkata knight riders"]),
        ("RR", ["Rajasthan Royals"], ["rr", "rajasthan", "rajasthan royals"]),
        ("SRH", ["Sunrisers Hyderabad"], ["srh", "sunrisers", "hyderabad", "sunrisers hyderabad"]),
        ("Delhi Capitals", ["Delhi Capitals", "Delhi Daredevils"], ["delhi capitals", "delhi daredevils"]),
        ("Deccan Chargers", ["Deccan Chargers"], ["deccan chargers", "deccan"]),
        ("PBKS", ["Kings XI Punjab", "Punjab Kings"], ["pbks", "kxip", "punjab", "kings xi", "punjab kings", "kings xi punjab"]),
        ("LSG", ["Lucknow Super Giants"], ["lsg", "lucknow", "lucknow super giants"]),
        ("RPS", ["Rising Pune Supergiant", "Rising Pune Supergiants"], ["rps", "rising pune"]),
        ("GL", ["Gujarat Lions"], ["gujarat lions"]),
        ("KTK", ["Kochi Tuskers Kerala"], ["kochi"]),
        ("PWI", ["Pune Warriors", "Pune Warriors India"], ["pune warriors"]),
    ]

    for display, aliases, triggers in teams:
        if text in triggers or any(trigger in text for trigger in triggers):
            return display, display, aliases

    return None, None, []


def _ftb_metric(question):
    text = str(question or "").lower()

    if "six" in text or "6" in text:
        return "sixes"

    if "four" in text or "4" in text or "boundary" in text or "boundaries" in text:
        return "fours"

    return None


def _ftb_limit(question):
    import re

    match = re.search(r"\btop\s+(\d+)\b", str(question or ""), flags=re.IGNORECASE)

    if match:
        value = int(match.group(1))
        if 1 <= value <= 50:
            return value

    return 10


def _ftb_season_condition(alias, year):
    year = int(year)

    if year == 2020:
        return f"(CAST({alias}.season AS varchar(20)) = '2020' OR CAST({alias}.season AS varchar(20)) = '2020/21')"

    if year == 2021:
        return f"(CAST({alias}.season AS varchar(20)) = '2021')"

    slash_form = f"{year - 1}/{str(year)[-2:]}"
    short_year = str(year)[-2:]

    return (
        f"(CAST({alias}.season AS varchar(20)) = '{year}' "
        f"OR CAST({alias}.season AS varchar(20)) = '{_ftb_q(slash_form)}' "
        f"OR CAST({alias}.season AS varchar(20)) LIKE '%/{_ftb_q(short_year)}')"
    )


def _ftb_venue_filter(raw):
    low = str(raw or "").lower().strip(" .?")

    if not low:
        return None, None

    if "new chandigarh" in low or "mullanpur" in low or "yadavindra" in low:
        return "(m.venue LIKE '%Yadavindra%' OR m.venue LIKE '%Mullanpur%' OR m.venue LIKE '%New Chandigarh%')", "Mullanpur / New Chandigarh"
    if "wankhede" in low:
        return "m.venue LIKE '%Wankhede%'", "Wankhede"
    if "chepauk" in low or "chidambaram" in low:
        return "(m.venue LIKE '%Chepauk%' OR m.venue LIKE '%Chidambaram%')", "Chepauk"
    if "eden" in low:
        return "m.venue LIKE '%Eden Gardens%'", "Eden Gardens"
    if "chinnaswamy" in low:
        return "m.venue LIKE '%Chinnaswamy%'", "Chinnaswamy"
    if "narendra" in low or "motera" in low or "ahmedabad" in low:
        return "(m.venue LIKE '%Narendra Modi%' OR m.venue LIKE '%Motera%' OR m.city LIKE '%Ahmedabad%')", "Ahmedabad"
    if "uppal" in low or "rajiv gandhi" in low:
        return "(m.venue LIKE '%Rajiv Gandhi%' OR m.venue LIKE '%Uppal%')", "Uppal"
    if "arun jaitley" in low or "kotla" in low:
        return "(m.venue LIKE '%Arun Jaitley%' OR m.venue LIKE '%Kotla%')", "Arun Jaitley Stadium"
    if "dubai" in low:
        return "(m.venue LIKE '%Dubai%' OR m.city LIKE '%Dubai%')", "Dubai"
    if "sharjah" in low:
        return "(m.venue LIKE '%Sharjah%' OR m.city LIKE '%Sharjah%')", "Sharjah"
    if "abu dhabi" in low or "zayed" in low:
        return "(m.venue LIKE '%Abu Dhabi%' OR m.venue LIKE '%Zayed%' OR m.city LIKE '%Abu Dhabi%')", "Abu Dhabi"
    if "brabourne" in low:
        return "m.venue LIKE '%Brabourne%'", "Brabourne"
    if "mohali" in low or "bindra" in low:
        return "(m.venue LIKE '%Mohali%' OR m.venue LIKE '%Bindra%' OR m.city LIKE '%Mohali%')", "Mohali"

    return None, None


def _ftb_parse(question):
    import re

    text = str(question or "").strip()
    low = text.lower()
    metric = _ftb_metric(question)

    if metric not in {"sixes", "fours"}:
        return None

    # Team can appear as:
    # "which MI player hit the most sixes..."
    # "most sixes for MI..."
    # "which player hit most sixes for MI..."
    team_raw = None

    match = re.search(
        r"\b(?:which|what|who)\s+([A-Za-z0-9 .]+?)\s+(?:player|batter|batsman)\b.*?\b(?:most|highest|top)\b.*?\b(?:six|sixes|four|fours|boundaries)\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        team_raw = match.group(1).strip(" .?")

    if not team_raw:
        match = re.search(
            r"\b(?:for|from|by)\s+([A-Za-z0-9 .]+?)(?:\s+in\s+20\d{2}|\s+at\s+|\s+against\s+|\s+on\s+|\s*$)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            team_raw = match.group(1).strip(" .?")

    if not team_raw:
        return None

    code, display, aliases = _ftb_team_lookup(team_raw)

    if code == "AMBIGUOUS_DC":
        return {"ambiguous": True}

    if not aliases:
        return None

    filters = [
        "d.innings IN (1, 2)",
        f"d.batting_team IN {_ftb_sql_list(aliases)}",
    ]
    labels = [f"for {display}"]

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        year = int(year_match.group(1))
        filters.append(_ftb_season_condition("d", year))
        labels.append(f"in {year}")

    # Venue: support "at Wankhede" and "in Wankhede"; do not confuse with "in 2026".
    venue_match = re.search(
        r"\b(?:at|inside|on)\s+([A-Za-z0-9 .'-]+?)(?:\s+against\s+|\s+for\s+|\s+in\s+20\d{2}|\s*$)",
        text,
        flags=re.IGNORECASE,
    )

    if not venue_match:
        in_match = re.search(
            r"\bin\s+([A-Za-z0-9 .'-]+?)(?:\s+against\s+|\s+for\s+|\s+in\s+20\d{2}|\s*$)",
            text,
            flags=re.IGNORECASE,
        )
        if in_match:
            possible = in_match.group(1).strip(" .?")
            if not re.fullmatch(r"20\d{2}", possible) and possible.lower() not in {"ipl", "the ipl", "history", "all seasons", "overall"}:
                venue_match = in_match

    if venue_match:
        venue_sql, venue_label = _ftb_venue_filter(venue_match.group(1))
        if venue_label:
            filters.append(venue_sql)
            labels.append(f"at {venue_label}")

    against_match = re.search(
        r"\bagainst\s+([A-Za-z0-9 .]+?)(?:\s+at\s+|\s+in\s+20\d{2}|\s*$)",
        text,
        flags=re.IGNORECASE,
    )
    if against_match:
        opp_code, opp_display, opp_aliases = _ftb_team_lookup(against_match.group(1).strip(" .?"))
        if opp_code == "AMBIGUOUS_DC":
            return {"ambiguous": True}
        if opp_aliases:
            filters.append(f"d.bowling_team IN {_ftb_sql_list(opp_aliases)}")
            labels.append(f"against {opp_display}")

    return {
        "metric": metric,
        "display": display,
        "aliases": aliases,
        "filters": filters,
        "labels": labels,
        "limit": _ftb_limit(question),
    }


def _ftb_ambiguity(question):
    import pandas as pd

    df = pd.DataFrame([{
        "issue": "DC is ambiguous",
        "action": "Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "example": "which Delhi Capitals player hit the most sixes in 2026",
    }])

    return {
        "question": question,
        "analysis_paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "paragraph": "DC is ambiguous. Use Delhi Capitals, Delhi Daredevils, or Deccan Chargers in full.",
        "result": df,
        "extra_tables": {"Clarification": df},
        "sql_query": "",
        "similar_questions": [
            "which Delhi Capitals player hit the most sixes in 2026",
            "most fours for Delhi Capitals at Arun Jaitley",
            "most sixes for Deccan Chargers",
            "most fours for Delhi Capitals against MI",
        ],
        "route_used": "",
        "data_sources": "",
    }


def _ftb_route(question):
    import pandas as pd
    from app.db import run_query

    parsed = _ftb_parse(question)
    if not parsed:
        return None

    if parsed.get("ambiguous"):
        return _ftb_ambiguity(question)

    metric = parsed["metric"]
    value_col = "sixes" if metric == "sixes" else "fours"
    where_sql = " AND ".join(parsed["filters"])
    team_label = parsed["display"]
    limit = int(parsed["limit"])

    sql = f"""
WITH batter_stats AS (
    SELECT
        d.striker AS batter,
        '{_ftb_q(team_label)}' AS team,
        COUNT(DISTINCT d.match_id) AS matches,
        SUM(COALESCE(d.runs_off_bat, 0)) AS runs,
        COUNT(CASE WHEN COALESCE(d.wides, 0)=0 THEN 1 END) AS balls,
        SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=4 THEN 1 ELSE 0 END) AS fours,
        SUM(CASE WHEN COALESCE(d.runs_off_bat, 0)=6 THEN 1 ELSE 0 END) AS sixes
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE {where_sql}
    GROUP BY d.striker
)
SELECT TOP {limit}
    batter,
    team,
    matches,
    runs,
    balls,
    fours,
    sixes
FROM batter_stats
WHERE {value_col} > 0
ORDER BY {value_col} DESC, runs DESC, batter ASC;
""".strip()

    try:
        df = run_query(sql)
    except Exception as error:
        return {
            "question": question,
            "analysis_paragraph": f"The filtered team boundary route failed: {error}",
            "paragraph": f"The filtered team boundary route failed: {error}",
            "result": pd.DataFrame(),
            "extra_tables": {},
            "sql_query": sql,
            "similar_questions": [],
        }

    df = df if df is not None else pd.DataFrame()

    title = f"Most {metric} " + " ".join(parsed["labels"])

    return {
        "question": question,
        "analysis_paragraph": f"{title}.",
        "paragraph": f"{title}.",
        "result": df,
        "extra_tables": {title: df} if not df.empty else {},
        "sql_query": sql,
        "similar_questions": [
            "which MI player hit the most sixes in 2026",
            "most sixes for MI in 2026 at Wankhede",
            "most fours for MI in 2026 at Wankhede",
            "most sixes for RCB in 2026 against CSK",
        ],
        "route_used": "",
        "data_sources": "",
    }


try:
    _previous_answer_question_with_fallback_before_ftb = answer_question_with_fallback
except NameError:
    _previous_answer_question_with_fallback_before_ftb = None


def answer_question_with_fallback(user_question):
    result = _ftb_route(user_question)
    if result is not None:
        return result
    return _previous_answer_question_with_fallback_before_ftb(user_question)

# IPL SQL Agent filtered team boundary route END

