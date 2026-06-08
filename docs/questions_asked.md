which players have the most ducks?
SELECT TOP 10
    striker AS player,
    COUNT(*) AS ducks
FROM deliveries
WHERE runs_off_bat = 0
GROUP BY striker
ORDER BY ducks DESC;
seems it counted most dot balls played by batsman because kohli is number 1 with 2455 ducks which is impossible

what is the most expensive spell by a bowler
SELECT TOP 10
    bowler,
    SUM(runs_off_bat + extras) AS total_runs_conceded,
    SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls_bowled,
    ROUND(
        SUM(runs_off_bat + extras) * 6.0 /
        NULLIF(SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy_rate
FROM deliveries
GROUP BY bowler
ORDER BY total_runs_conceded DESC;
wrong again,gave b kumar as number 1,it took total runs conceded rather than in one innings

who has the highest number of sixes in a single season
SELECT TOP 10
    striker AS batter,
    COUNT(CASE WHEN runs_off_bat = 6 THEN 1 ELSE NULL END) AS sixes_count
FROM deliveries
GROUP BY striker
ORDER BY sixes_count DESC;
ans is correct but it gave total sixes ever, not in a single season

what are the top 5 highest successful chases
SELECT TOP 5
    d.batting_team AS chasing_team,
    COUNT(*) AS successful_chases
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings = 2
    AND d.batting_team = m.winner
GROUP BY d.batting_team
ORDER BY successful_chases DESC;
wrong,it gave kkr as number one but 9010 successful run chases is impossible

who has the lowest strike rate(min 500 balls faced)
answered correctly

need to add support for orange cap and purple cap winner
orange cap= most runs in the season
purple cap= most wickets in the season

need to add support for short form of team names also such as csk,rcb,mi etc

what game had the highest number of sixes in it
SELECT TOP 1 
    match_id,
    SUM(CASE WHEN runs_off_bat = 6 THEN 1 ELSE 0 END) AS total_sixes
FROM deliveries
GROUP BY match_id
ORDER BY total_sixes DESC;
seems to be correct but it gives match id...not the teams that played in it...so need to add support for teams that played in that match and what year,preferably what ground as well

add support for chepauk also(nickname of ma chidabaram stadium in chennai)

which team has the best win percentage in the playoffs
SELECT TOP 10
    m.winner AS winning_team,
    CAST(COUNT(CASE WHEN m.season = 'Playoffs' THEN 1 ELSE NULL END) AS REAL) * 100 / COUNT(*) AS win_percentage
FROM matches m
GROUP BY m.winner
ORDER BY win_percentage DESC;
wrong as it gave 0 for all

which players have the most hundreds(list the top 5)
went to fallback ques bank: which teams have the most wins while chasing

which player has scored the most runs against the chennai super kings
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS total_runs
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.batting_team = 'Chennai Super Kings'
GROUP BY d.striker
ORDER BY total_runs DESC;
took the ques as which player has the most runs FOR csk not against them

which player has the highest score for kt
SELECT TOP 1
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
WHERE batting_team = 'KT'
GROUP BY striker
ORDER BY total_runs DESC;
maybe no data for kochi tuskers?

which player has the highest score for mi
SELECT TOP 1
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
WHERE batting_team = 'Mumbai Indians'
GROUP BY striker
ORDER BY total_runs DESC;
gave most runs for MI, not highest score
also no need for charts in such questions where only one player result is given...charts only for when top 5 or top 10 asked etc

what is the biggest win margin for csk
used fallback ques: who scored the most runs in death overs

add support for chinnaswamy stadium=m chinnaswamy stadium

who has the most runs for rps
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
WHERE batting_team = 'Royal Challengers Bangalore'
GROUP BY striker
ORDER BY total_runs DESC;
took it as rcb not rps

who has the most death over wickets for csk
SELECT TOP 10
    bowler,
    SUM(CASE WHEN FLOOR(ball) BETWEEN 15 AND 19 THEN 1 ELSE 0 END) AS death_over_wickets
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE d.bowling_team = 'Chennai Super Kings'
GROUP BY bowler
ORDER BY death_over_wickets DESC;
wrong ans,dj bravo doesnt have 1166 wickets

what is the lowest team score
SELECT MIN(total_team_runs) AS lowest_team_score
FROM (
    SELECT match_id, SUM(runs_off_bat + extras) AS total_team_runs
    FROM deliveries
    GROUP BY match_id
) AS team_scores;
wrong ans, ans is rcb with 49,it gave 25...also needs to give name of team,which season and against whom

what is the highest team score
SELECT MAX(total_team_runs) AS highest_team_score
FROM (
    SELECT match_id, SUM(runs_off_bat + extras) AS total_team_runs
    FROM deliveries
    GROUP BY match_id
) AS team_scores;
wrong again,gave 549

who has the most runs at the narendra modi stadium
wrong ans,went to fallback: who scored the most runs in death overs

we should ask it to create a list of the stadium names it uses,and then we can add support for their short names...i have a feeling the data uses the full names which no one uses in real life

which player hit the most fours in a single innings
SELECT TOP 10
    d.striker AS batter,
    SUM(CASE WHEN runs_off_bat = 4 THEN 1 ELSE 0 END) AS fours_in_innings
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
GROUP BY d.match_id, d.innings, d.striker, m.start_date, m.venue
ORDER BY fours_in_innings DESC;
correct ans, but i would love more details in such ques such as which year,against whom,what was the player's final score in the innings

which player hit the most sixes in a single innings
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
gave me highest runs in the innings...in that manner the ans was correct,but we need to remove match id,i dont need to see that in the answer...also against whom is needed to be given

what is the fastest hundred of all time
WITH first_hundred_runs AS (
    SELECT
        match_id,
        innings,
        striker AS batter,
        SUM(runs_off_bat) AS runs_in_innings
    FROM deliveries
    GROUP BY match_id, innings, striker
),
ranked_first_hundreds AS (
    SELECT
        batter,
        runs_in_innings,
        RANK() OVER (ORDER BY runs_in_innings ASC) AS rank
    FROM first_hundred_runs
)
SELECT
    batter,
    runs_in_innings
FROM ranked_first_hundreds
WHERE rank = 1;
wrong ans

which player hit the fastest fifty and in how many balls
SELECT TOP 1
    striker AS batter,
    SUM(runs_off_bat) AS runs_in_innings,
    COUNT(*) AS balls_faced
FROM deliveries d
JOIN matches m ON d.match_id = m.match_id
WHERE innings = 2
GROUP BY d.match_id, d.innings, d.striker
HAVING SUM(runs_off_bat) >= 50
ORDER BY balls_faced ASC;
ans is wrong,because urvil patel and jaiswal have the fastest fifty not pat cummins

