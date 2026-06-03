use CricketAnalytics;
go   
-- check total matches
select count(*) as total_matches
from matches;

--check total deliveries
select count(*) as total_deliveries
from deliveries;

--matches by season
SELECT
    season,
    count(*) as total_matches
from matches
group by season
order by season;

--top 10 run scorers
SELECT top 10
    striker as batter
    sum(runs_off_bat) as total_runs
from deliveries
group by striker
order by total_runs desc;

--top 10 batters by strike rate,exclude wides and no balls
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS runs,
    SUM(CASE 
            WHEN wides IS NULL AND noballs IS NULL THEN 1 
            ELSE 0 
        END) AS balls_faced,
    ROUND(
        SUM(runs_off_bat) * 100.0 / 
        NULLIF(SUM(CASE 
                    WHEN wides IS NULL AND noballs IS NULL THEN 1 
                    ELSE 0 
                END), 0),
        2
    ) AS strike_rate
FROM deliveries
GROUP BY striker
HAVING SUM(CASE 
            WHEN wides IS NULL AND noballs IS NULL THEN 1 
            ELSE 0 
        END) >= 300
ORDER BY strike_rate DESC;

--top 10 wicket takers excluding run out etc
select top 10
    bowler,
    count(*) as wickets
from deliveries
where wicket_type is not null
and wicket_type not in ('run out','retired out','obstructing the field')
group by bowler
order by wickets DESC;

--best economy rates excluding wides and no balls
select top 10
    bowler,
    sum(runs_off_bat + extras) as runs_conceded,
    sum(CASE
    when wides is null and noballs is null then 1
    else 0
    end) as legal_balls,
    round(
        sum(runs_off_bat+extras) * 6.0/
        nulliff(sum(CASE
        when wides is null and noballs is null then 1
        else 0
        end),0),
        2
    )as economy_rate

FROM deliveries
GROUP BY bowler
HAVING SUM(CASE 
            WHEN wides IS NULL AND noballs IS NULL THEN 1 
            ELSE 0 
        END) >= 300
ORDER BY economy_rate ASC;

-- Death overs top run scorers

SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS death_overs_runs
FROM deliveries
WHERE FLOOR(ball) BETWEEN 15 AND 19
GROUP BY striker
ORDER BY death_overs_runs DESC;

-- Death overs strike rate
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS runs,
    SUM(CASE 
            WHEN wides IS NULL AND noballs IS NULL THEN 1 
            ELSE 0 
        END) AS balls_faced,
    ROUND(
        SUM(runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE 
                    WHEN wides IS NULL AND noballs IS NULL THEN 1 
                    ELSE 0 
                END), 0),
        2
    ) AS death_overs_strike_rate
FROM deliveries
WHERE FLOOR(ball) BETWEEN 15 AND 19
GROUP BY striker
HAVING SUM(CASE 
            WHEN wides IS NULL AND noballs IS NULL THEN 1 
            ELSE 0 
        END) >= 100
ORDER BY death_overs_strike_rate DESC;

-- Powerplay wicket takers
-- 
SELECT TOP 10
    bowler,
    COUNT(*) AS powerplay_wickets
FROM deliveries
WHERE FLOOR(ball) BETWEEN 0 AND 5
  AND wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY bowler
ORDER BY powerplay_wickets DESC;

Team chasing wins
SELECT
    batting_team AS chasing_team,
    COUNT(DISTINCT d.match_id) AS chasing_wins
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings = 2
  AND d.batting_team = m.winner
GROUP BY batting_team
ORDER BY chasing_wins DESC;

--Average first innings score by venue
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