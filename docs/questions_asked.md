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

who has the highest score for csk
wrong again,gave most runs for csk,switched to mi and same result,most runs for mi not highest score

which players have the most ducks ques failed again
SELECT striker AS batter, COUNT(*) AS wickets FROM deliveries WHERE player_dismissed IS NOT NULL GROUP BY striker ORDER BY wickets DESC

what is the highest team score failed as well
went to fallback ques: which venues have the highest average first innings score
reason: llm error,model produced unsafe or invalid query

how many hundreds does kohli have
SELECT COUNT(*) AS hundreds FROM deliveries WHERE striker = 'Kohli' AND runs_off_bat >= 100
sql looks correct but result came as 0

how many ducks does kohli have
gave me entire list of players with most ducks,no mention of kohli in the sql or the result

what is csk win percentage
llm error: unsafe or invalid query

how many wickets does chahal have for rcb
used llm
SELECT COUNT(*) AS wickets FROM deliveries WHERE bowler = 'Chahal' AND batting_team = 'Royal Challengers Bangalore'
sql was wrong,batting team should be everyone other than rcb

who has the most fifties ever
failed,used fallback question bank

how many fifties does kohli have
SELECT COUNT(*) AS fifties FROM deliveries WHERE striker = 'Kohli' AND runs_off_bat >= 50
again sql seems correct but result came as 0

what is kohli's highest score against csk
used curated template for csk's highest scores...ive seen a strong tendency for the model to use curated templates if it sees any keywords...we need to improve this

what seasons did csk win the title
SELECT season FROM matches WHERE winner = 'Chennai Super Kings'
maybe this is a bad ques coz match id doesnt include its a final etc,so we can fix this later

how many runs does abd have for rcb
SELECT SUM(runs_off_bat) AS total_runs FROM deliveries WHERE striker = 'ABD' AND batting_team = 'Royal Challengers Bangalore';
got no ans

what is msd strike rate
used fallback question bank

csk win percentage failed again

how many fifties does kohli have worked but then i asked how many fifties does kohli have against csk failed because it used the curated template for kohli fifties

what is kohli strike rate was correct then i asked what is kohli strike rate in death overs,used curated template but didnt account for my ques
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
WHERE d.striker='V Kohli'
GROUP BY d.striker;

who has bowled the most balls ever
used fallback ques bank

who has the most fifties for csk
gave curated template of most fifties

also people can write suryavanshi as sooryavanshi...need to add that to rules also

who was the orange cap winner in the 2014 season
used fallback,couldnt ans

who has the best average(min 500 runs scored)
couldnt ans,used fallback

who won the purple cap in 2024 couldnt be answered
who has the best strike rate for csk(min 800 balls faced) couldnt be answered
who has the best average for csk(min 1000 runs scored) gave me best average for min 500 runs scored,so template must be edited to allow for any runs user specifies
who has scored the most runs in a single season went to fallback ques,need to add support for most wickets in a season also
who has the most five wicket hauls couldnt be answered...need to add fifer to rules
most hundreds in a single season couldnt be answered
highest total aggregrate in a match? (as in add both innings totals and list the highest total)
most sixes in a single match couldnt be answered(went to fallback)
not sure if we can add largest victory by runs and also by balls
same with smallest victory 

need to use player surnames also not specific names

who scored the most hundreds in 2016 season
couldnt ans
who has scored the most hundreds at chepauk
took it as most wickets at chepauk,wrong ans obv
who has scored most fifties at chepauk...gave most fifties overall
so yest we added support for sixes and fours at grounds,now we add other milestones such as fifties and hundreds and also fifers etc
what are the best bowling figures ever...couldnt ans,used fallback ques...so we have highest batting scores now we add best bowling figures overall and per ground as well...bowling figures matter on wickets taken...if wickets taken are the same then tiebreaker is economy rate.
what is csk's highest score ever...couldnt ans,so we add support for this also,as well as lowest score..overall and per venue as well
who has the most hundreds for csk...couldnt ans went to fallback
also need to add support for gujarat lions and pune warriors

lowest score by csk works but it gave 55 which i couldnt find in official records so it must be a rain curtailed game because according to the records,csk lowest score is 79 which appeared as num 3 in my ans...in the ans it gave first result as 55 second as 71 which csk chased against rcb...so i suppose technically it does count as lowest score but we can try and fix this

who has the most runs for deccan chargers failed
how many runs has dhoni scored against delhi worked but gave 2 ans,so runs against daredevils and runs against capitals...these 2 results must be totalled into 1 since both teams are the same,just name change...same issue with punjab also
who has the highest individual score for csk gave csk highest ever score...so we need to add support for individual highest score per team and highest score for the team overall...diff is the keyword individual..also support for best score for a team at venues...same with best figures for a team...and best figures for a team at a venue...same with fifties and hundreds,so who has the most fifties for csk at wankhede etc


who has the highest individual score for csk failed,tried other teams and it also failed,went to fallback
who has the most runs for deccan chargers failed...other defunct team such as rps works so idk y deccan chargers is failing again
what are the best bowling figures for csk against mi failed...so now we add against also...we added per team and venue,now against also so best score for csk against mi...this means any ground..but we also add support for venue here so best score for csk against kkr at eden gardens like that


who has scored the fastest fifty for csk needs to be added...so fastest fifty for a team like fastest fifty for mi...fastest fifty against a team so who has scored the fastest fifty against csk,and fastest fifty for csk at chepauk,so venue based also...and venue plus against also so fastest fifty for csk against mi at wankhede...same support needs to be added for fastests 100 also

other than fastest fifty,simply fifty and hundred against a team needs to be added also...so who has the most fifties against csk,same with most hundreds against csk...who has scored the most fifties for csk against mi is working correctly so we added support for that already and also venue wise we added...

also if i ask list all the hundreds scored in the 2014 season,it should be able to,same with fifties...and if i say list all the hundreds ever scored,it should list that...fifties are too long so no need
same with list all the fifers ever taken...if no fifer was taken in a season it should say no fifer taken this season etc

when i search who has scored the fastest fifty for rcb,romario shepard doesnt show up even tho he is num 1,but when i search fastest fifty overall,he comes up there
we also add highest score against a team,so who has the highest score against csk...also list the top 5 highest individual scores for csk against mi,team score comes but we need individual also...
also when i search list the 5 highest scores for rcb against csk,the 250 scored this year doesnt show up...also list the top 5 highest scores against csk doesnt work,it gives csk's highest scores...so we add this...also top 5 highest scores against csk at chepauk etc as well