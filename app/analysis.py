import pandas as pd
from app.db import run_query


def safe_first_value(df, column_name, default=None):
    if df is None or df.empty or column_name not in df.columns:
        return default

    return df.iloc[0][column_name]


def analyze_player_dismissals(player_condition):
    """
    Analyse how a batter gets dismissed using the player_dismissals view.

    player_condition should be something like:
    pd.batter = 'V Kohli'
    """
    player_condition = player_condition.replace("d.striker", "pd.batter")
    player_condition = player_condition.replace("d.player_dismissed", "pd.player_dismissed")

    wicket_type_sql = f"""
SELECT
    pd.wicket_type,
    COUNT(*) AS dismissals
FROM player_dismissals pd
WHERE {player_condition}
  AND pd.player_dismissed = pd.batter
GROUP BY pd.wicket_type
ORDER BY dismissals DESC;
""".strip()

    phase_sql = f"""
SELECT
    pd.phase,
    COUNT(*) AS dismissals
FROM player_dismissals pd
WHERE {player_condition}
  AND pd.player_dismissed = pd.batter
GROUP BY pd.phase
ORDER BY dismissals DESC;
""".strip()

    bowler_sql = f"""
SELECT TOP 10
    pd.bowler,
    COUNT(*) AS dismissals
FROM player_dismissals pd
WHERE {player_condition}
  AND pd.player_dismissed = pd.batter
  AND pd.is_bowler_credit_wicket = 1
GROUP BY pd.bowler
ORDER BY dismissals DESC;
""".strip()

    opponent_sql = f"""
SELECT TOP 10
    pd.bowling_team AS opponent,
    COUNT(*) AS dismissals
FROM player_dismissals pd
WHERE {player_condition}
  AND pd.player_dismissed = pd.batter
GROUP BY pd.bowling_team
ORDER BY dismissals DESC;
""".strip()

    venue_sql = f"""
SELECT TOP 10
    pd.venue,
    COUNT(*) AS dismissals
FROM player_dismissals pd
WHERE {player_condition}
  AND pd.player_dismissed = pd.batter
GROUP BY pd.venue
ORDER BY dismissals DESC;
""".strip()

    season_sql = f"""
SELECT
    pd.season_year,
    COUNT(*) AS dismissals
FROM player_dismissals pd
WHERE {player_condition}
  AND pd.player_dismissed = pd.batter
GROUP BY pd.season_year
ORDER BY pd.season_year;
""".strip()

    wicket_type_df = run_query(wicket_type_sql)
    phase_df = run_query(phase_sql)
    bowler_df = run_query(bowler_sql)
    opponent_df = run_query(opponent_sql)
    venue_df = run_query(venue_sql)
    season_df = run_query(season_sql)

    top_wicket_type = safe_first_value(wicket_type_df, "wicket_type", "unknown")
    top_phase = safe_first_value(phase_df, "phase", "unknown")
    top_bowler = safe_first_value(bowler_df, "bowler", "unknown")
    top_opponent = safe_first_value(opponent_df, "opponent", "unknown")
    top_venue = safe_first_value(venue_df, "venue", "unknown")

    summary_rows = [
        {
            "analysis_area": "Main dismissal type",
            "insight": f"Most dismissals are by {top_wicket_type}.",
        },
        {
            "analysis_area": "Phase pattern",
            "insight": f"Most dismissals happen in the {top_phase}.",
        },
        {
            "analysis_area": "Bowler matchup",
            "insight": f"The bowler with the most dismissals is {top_bowler}.",
        },
        {
            "analysis_area": "Opponent pattern",
            "insight": f"The opponent with the most dismissals is {top_opponent}.",
        },
        {
            "analysis_area": "Venue pattern",
            "insight": f"The venue with the most dismissals is {top_venue}.",
        },
    ]

    summary_df = pd.DataFrame(summary_rows)

    return {
        "summary": summary_df,
        "wicket_types": wicket_type_df,
        "phases": phase_df,
        "bowlers": bowler_df,
        "opponents": opponent_df,
        "venues": venue_df,
        "seasons": season_df,
        "sql_queries": {
            "wicket_types": wicket_type_sql,
            "phases": phase_sql,
            "bowlers": bowler_sql,
            "opponents": opponent_sql,
            "venues": venue_sql,
            "seasons": season_sql,
        },
    }

def analyze_bowler_matchups(bowler_condition):
    """
    Analyse a bowler's matchups against batters.

    bowler_condition should be something like:
    d.bowler = 'JJ Bumrah'
    """

    most_dismissed_sql = f"""
SELECT TOP 10
    d.striker AS batter,
    COUNT(*) AS dismissals
FROM deliveries d
WHERE {bowler_condition}
  AND d.player_dismissed = d.striker
  AND d.wicket_type IS NOT NULL
  AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY d.striker
ORDER BY dismissals DESC;
""".strip()

    most_runs_sql = f"""
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS runs_scored,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
WHERE {bowler_condition}
GROUP BY d.striker
HAVING SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) >= 10
ORDER BY runs_scored DESC;
""".strip()

    highest_average_sql = f"""
WITH batter_vs_bowler AS (
    SELECT
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs_scored,
        SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        COUNT(CASE
            WHEN d.player_dismissed = d.striker
                 AND d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS dismissals
    FROM deliveries d
    WHERE {bowler_condition}
    GROUP BY d.striker
)
SELECT TOP 10
    batter,
    runs_scored,
    balls_faced,
    dismissals,
    ROUND(runs_scored * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average,
    ROUND(runs_scored * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate
FROM batter_vs_bowler
WHERE balls_faced >= 10
  AND dismissals > 0
ORDER BY batting_average DESC, strike_rate DESC;
""".strip()

    highest_strike_rate_sql = f"""
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS runs_scored,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
WHERE {bowler_condition}
GROUP BY d.striker
HAVING SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) >= 10
ORDER BY strike_rate DESC, runs_scored DESC;
""".strip()

    phase_sql = f"""
SELECT
    CASE
        WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(d.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(d.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END AS phase,
    SUM(d.runs_off_bat) AS runs_conceded,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS wickets,
    ROUND(
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) * 6.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy_rate
FROM deliveries d
WHERE {bowler_condition}
GROUP BY
    CASE
        WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(d.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(d.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END
ORDER BY wickets DESC, economy_rate ASC;
""".strip()

    most_dismissed_df = run_query(most_dismissed_sql)
    most_runs_df = run_query(most_runs_sql)
    highest_average_df = run_query(highest_average_sql)
    highest_strike_rate_df = run_query(highest_strike_rate_sql)
    phase_df = run_query(phase_sql)

    top_success_batter = safe_first_value(most_dismissed_df, "batter", "unknown")
    top_runs_batter = safe_first_value(most_runs_df, "batter", "unknown")
    top_average_batter = safe_first_value(highest_average_df, "batter", "unknown")
    top_strike_rate_batter = safe_first_value(highest_strike_rate_df, "batter", "unknown")
    best_phase = safe_first_value(phase_df, "phase", "unknown")

    summary_rows = [
        {
            "analysis_area": "Best matchup",
            "insight": f"The bowler has dismissed {top_success_batter} the most times.",
        },
        {
            "analysis_area": "Most expensive matchup",
            "insight": f"{top_runs_batter} has scored the most runs against this bowler.",
        },
        {
            "analysis_area": "Highest average against bowler",
            "insight": f"{top_average_batter} has the highest batting average against this bowler among filtered batters.",
        },
        {
            "analysis_area": "Highest strike rate against bowler",
            "insight": f"{top_strike_rate_batter} scores fastest against this bowler among filtered batters.",
        },
        {
            "analysis_area": "Best phase",
            "insight": f"The bowler's strongest wicket-taking phase appears to be the {best_phase}.",
        },
    ]

    summary_df = pd.DataFrame(summary_rows)

    return {
        "summary": summary_df,
        "most_dismissed": most_dismissed_df,
        "most_runs": most_runs_df,
        "highest_average": highest_average_df,
        "highest_strike_rate": highest_strike_rate_df,
        "phases": phase_df,
        "sql_queries": {
            "most_dismissed": most_dismissed_sql,
            "most_runs": most_runs_sql,
            "highest_average": highest_average_sql,
            "highest_strike_rate": highest_strike_rate_sql,
            "phases": phase_sql,
        },
    }
def analyze_team_title_chances():
    """
    Simple explainable team rating based on recent wins, playoff record,
    batting strength, and bowling strength.
    """

    sql_query = """
WITH recent_matches AS (
    SELECT *
    FROM matches
    WHERE TRY_CAST(season AS VARCHAR(20)) IS NOT NULL
),
team_matches AS (
    SELECT DISTINCT
        d.match_id,
        d.batting_team AS team,
        m.winner,
        m.season,
        m.start_date
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
),
team_win_rates AS (
    SELECT
        team,
        COUNT(*) AS matches_played,
        SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) AS wins,
        ROUND(
            SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS win_percentage
    FROM team_matches
    GROUP BY team
),
batting_strength AS (
    SELECT
        batting_team AS team,
        ROUND(AVG(team_score * 1.0), 2) AS avg_score
    FROM (
        SELECT
            match_id,
            innings,
            batting_team,
            SUM(runs_off_bat + extras) AS team_score
        FROM deliveries
        WHERE innings IN (1, 2)
        GROUP BY match_id, innings, batting_team
    ) AS innings_scores
    GROUP BY batting_team
),
bowling_strength AS (
    SELECT
        bowling_team AS team,
        ROUND(AVG(team_score * 1.0), 2) AS avg_runs_conceded
    FROM (
        SELECT
            match_id,
            innings,
            bowling_team,
            SUM(runs_off_bat + extras) AS team_score
        FROM deliveries
        WHERE innings IN (1, 2)
        GROUP BY match_id, innings, bowling_team
    ) AS innings_scores
    GROUP BY bowling_team
),
playoff_strength AS (
    SELECT
        team,
        COUNT(*) AS playoff_matches,
        SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) AS playoff_wins
    FROM (
        SELECT
            ms.match_id,
            ms.winner,
            ms.team_1 AS team
        FROM match_stages ms
        WHERE ms.is_playoff = 1

        UNION ALL

        SELECT
            ms.match_id,
            ms.winner,
            ms.team_2 AS team
        FROM match_stages ms
        WHERE ms.is_playoff = 1
    ) AS playoff_teams
    GROUP BY team
)
SELECT TOP 10
    tw.team,
    tw.matches_played,
    tw.wins,
    tw.win_percentage,
    bs.avg_score,
    bw.avg_runs_conceded,
    COALESCE(ps.playoff_matches, 0) AS playoff_matches,
    COALESCE(ps.playoff_wins, 0) AS playoff_wins,
    ROUND(
        tw.win_percentage * 0.40
        + bs.avg_score * 0.20
        - bw.avg_runs_conceded * 0.15
        + COALESCE(ps.playoff_wins, 0) * 2.5,
        2
    ) AS title_chance_score
FROM team_win_rates tw
JOIN batting_strength bs
    ON tw.team = bs.team
JOIN bowling_strength bw
    ON tw.team = bw.team
LEFT JOIN playoff_strength ps
    ON tw.team = ps.team
ORDER BY title_chance_score DESC;
""".strip()

    result = run_query(sql_query)

    return {
        "summary": result,
        "sql_query": sql_query,
    }