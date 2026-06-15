import pandas as pd
from app.db import run_query
import re
import pandas as pd
from app.db import run_query

def safe_first_value(df, column_name, default=None):
    if df is None or df.empty or column_name not in df.columns:
        return default

    return df.iloc[0][column_name]

def extract_player_name_from_condition(player_condition):
    match = re.search(r"=\s*'([^']+)'", player_condition)

    if match is not None:
        return match.group(1)

    return "selected player"



def format_metric(value, decimals=2):
    if value is None:
        return "N/A"

    try:
        if pd.isna(value):
            return "N/A"
    except Exception:
        pass

    try:
        return f"{float(value):.{decimals}f}"
    except Exception:
        return str(value)
    
def convert_team_condition(team_condition, new_column_name):
    """
    Convert a team condition from one SQL alias/column to another.

    Example:
    d.batting_team = 'Chennai Super Kings'
    becomes:
    tm.team = 'Chennai Super Kings'
    """

    replacements = [
        "d.batting_team",
        "d.bowling_team",
        "m.winner",
        "ms.team_1",
        "ms.team_2",
        "tm.team",
        "innings_scores.batting_team",
        "innings_scores.bowling_team",
    ]

    converted_condition = team_condition

    for old_column in replacements:
        converted_condition = converted_condition.replace(old_column, new_column_name)

    return converted_condition


def convert_team_condition_two_columns(team_condition, column_one, column_two):
    condition_one = convert_team_condition(team_condition, column_one)
    condition_two = convert_team_condition(team_condition, column_two)

    return f"({condition_one} OR {condition_two})"


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
    player_name = extract_player_name_from_condition(player_condition)

    if wicket_type_df is not None and not wicket_type_df.empty:
        total_dismissals = int(wicket_type_df["dismissals"].sum())
    else:
        total_dismissals = 0

    paragraph = (
        f"{player_name}'s dismissal profile shows {total_dismissals} recorded dismissals in the dataset. "
        f"The most common dismissal type is {top_wicket_type}, and most dismissals happen in the {top_phase}. "
        f"The bowler with the most dismissals is {top_bowler}, while the opponent and venue patterns point to "
        f"{top_opponent} and {top_venue}. This is based on dismissal type, phase, bowler, opponent, and venue data, "
        f"not shot-type video data."
    )
    summary_rows = [
        {
            "analysis_area": "Overall insight",
            "insight": paragraph,
        },
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
        "paragraph": paragraph,
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
    bowler_name = extract_player_name_from_condition(bowler_condition)

    paragraph = (
        f"{bowler_name}'s bowler matchup profile suggests that {top_success_batter} is the batter he has dismissed "
        f"most often. {top_runs_batter} has scored the most runs against him, while {top_average_batter} has the "
        f"highest batting average and {top_strike_rate_batter} has the highest strike rate against him among the "
        f"filtered batters. Phase-wise, his strongest wicket-taking phase appears to be the {best_phase}."
    )
    summary_rows = [
        {
            "analysis_area": "Overall insight",
            "insight": paragraph,
        },
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
        "paragraph": paragraph,
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

def analyze_player_profile(player_condition):
    """
    Full batting profile analysis for a player.

    player_condition should be something like:
    d.striker = 'V Kohli'
    """

    condition_d = player_condition.replace("pd.batter", "d.striker")
    condition_pd = condition_d.replace("d.striker", "pd.batter")

    player_name = extract_player_name_from_condition(condition_d)

    career_sql = f"""
WITH batter_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.batting_team,
        SUM(d.runs_off_bat) AS runs,
        SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls,
        SUM(CASE WHEN d.runs_off_bat = 4 THEN 1 ELSE 0 END) AS fours,
        SUM(CASE WHEN d.runs_off_bat = 6 THEN 1 ELSE 0 END) AS sixes,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
                 AND d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('retired hurt', 'retired out')
            THEN 1
            ELSE 0
        END) AS dismissed
    FROM deliveries d
    WHERE {condition_d}
    GROUP BY d.match_id, d.innings, d.striker, d.batting_team
)
SELECT
    batter,
    COUNT(*) AS innings,
    SUM(runs) AS total_runs,
    MAX(runs) AS highest_score,
    SUM(balls) AS balls_faced,
    SUM(dismissed) AS dismissals,
    ROUND(SUM(runs) * 1.0 / NULLIF(SUM(dismissed), 0), 2) AS batting_average,
    ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate,
    SUM(fours) AS fours,
    SUM(sixes) AS sixes,
    COUNT(CASE WHEN runs >= 50 AND runs < 100 THEN 1 END) AS fifties,
    COUNT(CASE WHEN runs >= 100 THEN 1 END) AS hundreds
FROM batter_innings
GROUP BY batter;
""".strip()

    season_sql = f"""
WITH batter_innings AS (
    SELECT
        d.match_id,
        d.innings,
        YEAR(CAST(m.start_date AS date)) AS season_year,
        d.striker AS batter,
        SUM(d.runs_off_bat) AS runs,
        SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls,
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
    WHERE {condition_d}
    GROUP BY d.match_id, d.innings, YEAR(CAST(m.start_date AS date)), d.striker
)
SELECT
    season_year,
    COUNT(*) AS innings,
    SUM(runs) AS runs,
    MAX(runs) AS highest_score,
    SUM(balls) AS balls_faced,
    SUM(dismissed) AS dismissals,
    ROUND(SUM(runs) * 1.0 / NULLIF(SUM(dismissed), 0), 2) AS batting_average,
    ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate
FROM batter_innings
GROUP BY season_year
ORDER BY season_year;
""".strip()

    phase_sql = f"""
SELECT
    CASE
        WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(d.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(d.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END AS phase,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    COUNT(CASE
        WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
WHERE {condition_d}
GROUP BY
    CASE
        WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(d.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(d.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END
ORDER BY runs DESC;
""".strip()

    opponent_sql = f"""
SELECT TOP 10
    d.bowling_team AS opponent,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    COUNT(CASE
        WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(d.runs_off_bat) * 1.0 /
        NULLIF(COUNT(CASE
            WHEN d.player_dismissed = d.striker
                 AND d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('retired hurt', 'retired out')
            THEN 1
        END), 0),
        2
    ) AS batting_average,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
WHERE {condition_d}
GROUP BY d.bowling_team
HAVING SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) >= 20
ORDER BY runs DESC;
""".strip()

    venue_sql = f"""
SELECT TOP 10
    m.venue,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    COUNT(CASE
        WHEN d.player_dismissed = d.striker
             AND d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('retired hurt', 'retired out')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE {condition_d}
GROUP BY m.venue
HAVING SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) >= 20
ORDER BY runs DESC;
""".strip()

    playoff_sql = f"""
WITH batter_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        ms.match_stage,
        ms.is_playoff,
        ms.is_final,
        SUM(d.runs_off_bat) AS runs,
        SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls,
        MAX(CASE
            WHEN d.player_dismissed = d.striker
                 AND d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('retired hurt', 'retired out')
            THEN 1
            ELSE 0
        END) AS dismissed
    FROM deliveries d
    JOIN match_stages ms
        ON d.match_id = ms.match_id
    WHERE {condition_d}
    GROUP BY d.match_id, d.innings, d.striker, ms.match_stage, ms.is_playoff, ms.is_final
),
combined_context AS (
    SELECT
        'Playoffs' AS context,
        runs,
        balls,
        dismissed
    FROM batter_innings
    WHERE is_playoff = 1

    UNION ALL

    SELECT
        'Finals' AS context,
        runs,
        balls,
        dismissed
    FROM batter_innings
    WHERE is_final = 1
)
SELECT
    context,
    COUNT(*) AS innings,
    SUM(runs) AS runs,
    MAX(runs) AS highest_score,
    SUM(balls) AS balls_faced,
    SUM(dismissed) AS dismissals,
    ROUND(SUM(runs) * 1.0 / NULLIF(SUM(dismissed), 0), 2) AS batting_average,
    ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate
FROM combined_context
GROUP BY context
ORDER BY
    CASE
        WHEN context = 'Playoffs' THEN 1
        WHEN context = 'Finals' THEN 2
        ELSE 3
    END;
""".strip()

    dismissal_sql = f"""
SELECT
    pd.wicket_type,
    COUNT(*) AS dismissals
FROM player_dismissals pd
WHERE {condition_pd}
  AND pd.player_dismissed = pd.batter
GROUP BY pd.wicket_type
ORDER BY dismissals DESC;
""".strip()

    career_df = run_query(career_sql)
    season_df = run_query(season_sql)
    phase_df = run_query(phase_sql)
    opponent_df = run_query(opponent_sql)
    venue_df = run_query(venue_sql)
    playoff_df = run_query(playoff_sql)
    dismissal_df = run_query(dismissal_sql)

    total_runs = safe_first_value(career_df, "total_runs", 0)
    batting_average = safe_first_value(career_df, "batting_average", None)
    strike_rate = safe_first_value(career_df, "strike_rate", None)
    highest_score = safe_first_value(career_df, "highest_score", None)
    hundreds = safe_first_value(career_df, "hundreds", 0)
    fifties = safe_first_value(career_df, "fifties", 0)

    top_phase = safe_first_value(phase_df, "phase", "unknown phase")
    top_opponent = safe_first_value(opponent_df, "opponent", "unknown opponent")
    top_venue = safe_first_value(venue_df, "venue", "unknown venue")
    main_dismissal = safe_first_value(dismissal_df, "wicket_type", "unknown dismissal type")

    paragraph = (
        f"{player_name}'s IPL profile shows {total_runs} runs, a highest score of {highest_score}, "
        f"{fifties} fifties and {hundreds} hundreds. The overall batting average is "
        f"{format_metric(batting_average)} with a strike rate of {format_metric(strike_rate)}. "
        f"The data suggests the strongest scoring phase is {top_phase}, with the most runs coming against "
        f"{top_opponent} and at {top_venue}. The most common dismissal type is {main_dismissal}, "
        f"which helps identify the player's main dismissal pattern."
    )

    summary_rows = [
        {
            "analysis_area": "Overall profile",
            "insight": paragraph,
        },
        {
            "analysis_area": "Scoring strength",
            "insight": f"Most runs by phase are in the {top_phase}.",
        },
        {
            "analysis_area": "Best opponent pattern",
            "insight": f"Most runs have come against {top_opponent}.",
        },
        {
            "analysis_area": "Venue pattern",
            "insight": f"Most runs have come at {top_venue}.",
        },
        {
            "analysis_area": "Dismissal pattern",
            "insight": f"Most common dismissal type is {main_dismissal}.",
        },
    ]

    summary_df = pd.DataFrame(summary_rows)

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "career": career_df,
        "season_trend": season_df,
        "phase_performance": phase_df,
        "opponent_performance": opponent_df,
        "venue_performance": venue_df,
        "playoff_performance": playoff_df,
        "dismissal_types": dismissal_df,
        "sql_queries": {
            "career": career_sql,
            "season_trend": season_sql,
            "phase_performance": phase_sql,
            "opponent_performance": opponent_sql,
            "venue_performance": venue_sql,
            "playoff_performance": playoff_sql,
            "dismissal_types": dismissal_sql,
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

    top_team = safe_first_value(result, "team", "unknown team")
    top_score = safe_first_value(result, "title_chance_score", None)
    top_win_percentage = safe_first_value(result, "win_percentage", None)
    top_avg_score = safe_first_value(result, "avg_score", None)
    top_avg_runs_conceded = safe_first_value(result, "avg_runs_conceded", None)
    top_playoff_wins = safe_first_value(result, "playoff_wins", 0)

    paragraph = (
        f"The explainable title-chance model ranks {top_team} highest with a score of "
        f"{format_metric(top_score)}. This is not a guaranteed prediction; it is a data-based ranking using "
        f"historical win percentage, batting strength, bowling strength, and playoff wins. {top_team}'s profile "
        f"includes a win rate of {format_metric(top_win_percentage)}%, an average score of "
        f"{format_metric(top_avg_score)}, average runs conceded of {format_metric(top_avg_runs_conceded)}, "
        f"and {format_metric(top_playoff_wins, 0)} playoff wins."
    )

    return {
        "paragraph": paragraph,
        "summary": result,
        "sql_query": sql_query,
    }

def analyze_team_profile(team_condition, team_label):
    """
    Full team profile analysis.

    team_condition should be something like:
    d.batting_team = 'Chennai Super Kings'
    """

    team_match_condition = convert_team_condition(team_condition, "tm.team")
    batting_condition = convert_team_condition(team_condition, "d.batting_team")
    bowling_condition = convert_team_condition(team_condition, "d.bowling_team")
    playoff_condition = convert_team_condition_two_columns(team_condition, "ms.team_1", "ms.team_2")

    overall_sql = f"""
WITH team_matches AS (
    SELECT DISTINCT
        d.match_id,
        d.batting_team AS team,
        m.winner,
        YEAR(CAST(m.start_date AS date)) AS season_year,
        m.venue
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
)
SELECT
    '{team_label}' AS team_group,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) AS wins,
    COUNT(*) - SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) AS losses_or_no_results,
    ROUND(
        SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS win_percentage
FROM team_matches tm
WHERE {team_match_condition};
""".strip()

    season_sql = f"""
WITH team_matches AS (
    SELECT DISTINCT
        d.match_id,
        d.batting_team AS team,
        m.winner,
        YEAR(CAST(m.start_date AS date)) AS season_year
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
)
SELECT
    tm.season_year,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) AS wins,
    ROUND(
        SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS win_percentage
FROM team_matches tm
WHERE {team_match_condition}
GROUP BY tm.season_year
ORDER BY tm.season_year;
""".strip()

    batting_sql = f"""
WITH innings_scores AS (
    SELECT
        d.match_id,
        d.innings,
        d.batting_team,
        SUM(d.runs_off_bat + d.extras) AS team_score,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
    FROM deliveries d
    WHERE d.innings IN (1, 2)
      AND {batting_condition}
    GROUP BY d.match_id, d.innings, d.batting_team
)
SELECT
    '{team_label}' AS team_group,
    COUNT(*) AS batting_innings,
    ROUND(AVG(team_score * 1.0), 2) AS avg_score,
    MAX(team_score) AS highest_score,
    COUNT(CASE WHEN team_score >= 200 THEN 1 END) AS scores_200_plus,
    ROUND(
        SUM(team_score) * 6.0 /
        NULLIF(SUM(legal_balls), 0),
        2
    ) AS run_rate
FROM innings_scores;
""".strip()

    bowling_sql = f"""
WITH innings_scores AS (
    SELECT
        d.match_id,
        d.innings,
        d.bowling_team,
        SUM(d.runs_off_bat + d.extras) AS runs_conceded,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets
    FROM deliveries d
    WHERE d.innings IN (1, 2)
      AND {bowling_condition}
    GROUP BY d.match_id, d.innings, d.bowling_team
)
SELECT
    '{team_label}' AS team_group,
    COUNT(*) AS bowling_innings,
    ROUND(AVG(runs_conceded * 1.0), 2) AS avg_runs_conceded,
    MIN(runs_conceded) AS lowest_score_conceded,
    SUM(wickets) AS wickets,
    ROUND(
        SUM(runs_conceded) * 6.0 /
        NULLIF(SUM(legal_balls), 0),
        2
    ) AS economy_rate
FROM innings_scores;
""".strip()

    chase_defend_sql = f"""
WITH innings_scores AS (
    SELECT
        d.match_id,
        d.innings,
        d.batting_team,
        d.bowling_team,
        m.winner,
        SUM(d.runs_off_bat + d.extras) AS team_score
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
    WHERE d.innings IN (1, 2)
    GROUP BY d.match_id, d.innings, d.batting_team, d.bowling_team, m.winner
),
contexts AS (
    SELECT
        'Chasing' AS context,
        batting_team AS team,
        winner
    FROM innings_scores
    WHERE innings = 2

    UNION ALL

    SELECT
        'Defending' AS context,
        batting_team AS team,
        winner
    FROM innings_scores
    WHERE innings = 1
)
SELECT
    context,
    COUNT(*) AS matches,
    SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) AS wins,
    ROUND(
        SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS win_percentage
FROM contexts tm
WHERE {team_match_condition}
GROUP BY context
ORDER BY context;
""".strip()

    playoff_sql = f"""
WITH playoff_team_matches AS (
    SELECT
        ms.match_id,
        ms.season_year,
        ms.match_stage,
        ms.team_1 AS team,
        ms.winner,
        ms.is_playoff,
        ms.is_final
    FROM match_stages ms
    WHERE ms.is_playoff = 1

    UNION ALL

    SELECT
        ms.match_id,
        ms.season_year,
        ms.match_stage,
        ms.team_2 AS team,
        ms.winner,
        ms.is_playoff,
        ms.is_final
    FROM match_stages ms
    WHERE ms.is_playoff = 1
)
SELECT
    '{team_label}' AS team_group,
    COUNT(*) AS playoff_matches,
    SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) AS playoff_wins,
    SUM(CASE WHEN is_final = 1 THEN 1 ELSE 0 END) AS finals_played,
    SUM(CASE WHEN is_final = 1 AND winner = team THEN 1 ELSE 0 END) AS titles,
    ROUND(
        SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS playoff_win_percentage
FROM playoff_team_matches tm
WHERE {team_match_condition};
""".strip()

    venue_sql = f"""
WITH team_matches AS (
    SELECT DISTINCT
        d.match_id,
        d.batting_team AS team,
        m.winner,
        m.venue
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
)
SELECT TOP 10
    tm.venue,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) AS wins,
    ROUND(
        SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS win_percentage
FROM team_matches tm
WHERE {team_match_condition}
GROUP BY tm.venue
HAVING COUNT(*) >= 3
ORDER BY wins DESC, win_percentage DESC;
""".strip()

    phase_batting_sql = f"""
SELECT
    CASE
        WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(d.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(d.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END AS phase,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    ROUND(
        SUM(d.runs_off_bat) * 6.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS run_rate
FROM deliveries d
WHERE {batting_condition}
GROUP BY
    CASE
        WHEN FLOOR(d.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(d.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(d.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END
ORDER BY runs DESC;
""".strip()

    overall_df = run_query(overall_sql)
    season_df = run_query(season_sql)
    batting_df = run_query(batting_sql)
    bowling_df = run_query(bowling_sql)
    chase_defend_df = run_query(chase_defend_sql)
    playoff_df = run_query(playoff_sql)
    venue_df = run_query(venue_sql)
    phase_batting_df = run_query(phase_batting_sql)

    matches_played = safe_first_value(overall_df, "matches_played", 0)
    wins = safe_first_value(overall_df, "wins", 0)
    win_percentage = safe_first_value(overall_df, "win_percentage", None)

    avg_score = safe_first_value(batting_df, "avg_score", None)
    run_rate = safe_first_value(batting_df, "run_rate", None)

    avg_runs_conceded = safe_first_value(bowling_df, "avg_runs_conceded", None)
    economy_rate = safe_first_value(bowling_df, "economy_rate", None)

    playoff_matches = safe_first_value(playoff_df, "playoff_matches", 0)
    playoff_wins = safe_first_value(playoff_df, "playoff_wins", 0)
    titles = safe_first_value(playoff_df, "titles", 0)

    best_venue = safe_first_value(venue_df, "venue", "unknown venue")
    best_phase = safe_first_value(phase_batting_df, "phase", "unknown phase")

    paragraph = (
        f"{team_label}'s team profile shows {matches_played} matches and {wins} wins, giving a win percentage of "
        f"{format_metric(win_percentage)}%. The batting profile shows an average score of {format_metric(avg_score)} "
        f"and a run rate of {format_metric(run_rate)}, while the bowling profile shows average runs conceded of "
        f"{format_metric(avg_runs_conceded)} with an economy rate of {format_metric(economy_rate)}. In playoff matches, "
        f"the team has played {format_metric(playoff_matches, 0)} matches, won {format_metric(playoff_wins, 0)}, and won "
        f"{format_metric(titles, 0)} titles. The strongest venue pattern appears to be {best_venue}, and the strongest "
        f"batting phase by runs is {best_phase}."
    )

    summary_rows = [
        {
            "analysis_area": "Overall insight",
            "insight": paragraph,
        },
        {
            "analysis_area": "Win record",
            "insight": f"{team_label} has a win percentage of {format_metric(win_percentage)}%.",
        },
        {
            "analysis_area": "Batting profile",
            "insight": f"The team averages {format_metric(avg_score)} runs per innings at a run rate of {format_metric(run_rate)}.",
        },
        {
            "analysis_area": "Bowling profile",
            "insight": f"The team concedes {format_metric(avg_runs_conceded)} runs per innings at an economy rate of {format_metric(economy_rate)}.",
        },
        {
            "analysis_area": "Playoff profile",
            "insight": f"The team has {format_metric(playoff_wins, 0)} playoff wins and {format_metric(titles, 0)} titles in the dataset.",
        },
        {
            "analysis_area": "Venue pattern",
            "insight": f"The best venue pattern appears to be {best_venue}.",
        },
    ]

    summary_df = pd.DataFrame(summary_rows)

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "overall": overall_df,
        "season_trend": season_df,
        "batting": batting_df,
        "bowling": bowling_df,
        "chase_defend": chase_defend_df,
        "playoff": playoff_df,
        "venues": venue_df,
        "phase_batting": phase_batting_df,
        "sql_queries": {
            "overall": overall_sql,
            "season_trend": season_sql,
            "batting": batting_sql,
            "bowling": bowling_sql,
            "chase_defend": chase_defend_sql,
            "playoff": playoff_sql,
            "venues": venue_sql,
            "phase_batting": phase_batting_sql,
        },
    }

def analyze_player_shots(player_condition):
    """
    Analyse a batter's shot selection using shot_events.

    player_condition should be something like:
    se.striker = 'V Kohli'
    """

    condition_se = player_condition
    condition_se = condition_se.replace("d.striker", "se.striker")
    condition_se = condition_se.replace("pd.batter", "se.striker")

    player_name = extract_player_name_from_condition(condition_se)

    shot_summary_sql = f"""
WITH shot_stats AS (
    SELECT
        se.shot_played,
        COUNT(*) AS deliveries,
        SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        SUM(se.runs_off_bat) AS runs,
        SUM(CASE WHEN se.runs_off_bat IN (4, 6) THEN 1 ELSE 0 END) AS boundaries,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('retired hurt', 'retired out')
            THEN 1
        END) AS dismissals
    FROM dbo.shot_events se
    WHERE {condition_se}
      AND se.shot_played IS NOT NULL
      AND se.shot_played <> ''
    GROUP BY se.shot_played
)
SELECT TOP 15
    shot_played,
    deliveries,
    balls_faced,
    runs,
    boundaries,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
    ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average
FROM shot_stats
ORDER BY runs DESC, balls_faced DESC;
""".strip()

    shot_dismissal_sql = f"""
SELECT TOP 15
    se.shot_played,
    se.wicket_type,
    COUNT(*) AS dismissals
FROM dbo.shot_events se
WHERE {condition_se}
  AND se.shot_played IS NOT NULL
  AND se.shot_played <> ''
  AND se.player_dismissed = se.striker
  AND se.wicket_type IS NOT NULL
  AND se.wicket_type NOT IN ('retired hurt', 'retired out')
GROUP BY se.shot_played, se.wicket_type
ORDER BY dismissals DESC;
""".strip()

    risky_shots_sql = f"""
WITH shot_stats AS (
    SELECT
        se.shot_played,
        SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        SUM(se.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('retired hurt', 'retired out')
            THEN 1
        END) AS dismissals
    FROM dbo.shot_events se
    WHERE {condition_se}
      AND se.shot_played IS NOT NULL
      AND se.shot_played <> ''
    GROUP BY se.shot_played
)
SELECT TOP 10
    shot_played,
    balls_faced,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
    ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average
FROM shot_stats
WHERE balls_faced >= 10
  AND dismissals > 0
ORDER BY dismissals DESC, batting_average ASC, strike_rate ASC;
""".strip()

    best_shots_sql = f"""
WITH shot_stats AS (
    SELECT
        se.shot_played,
        SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        SUM(se.runs_off_bat) AS runs,
        SUM(CASE WHEN se.runs_off_bat IN (4, 6) THEN 1 ELSE 0 END) AS boundaries
    FROM dbo.shot_events se
    WHERE {condition_se}
      AND se.shot_played IS NOT NULL
      AND se.shot_played <> ''
    GROUP BY se.shot_played
)
SELECT TOP 10
    shot_played,
    balls_faced,
    runs,
    boundaries,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate
FROM shot_stats
WHERE balls_faced >= 10
ORDER BY strike_rate DESC, runs DESC;
""".strip()

    line_length_sql = f"""
SELECT TOP 15
    se.ball_length,
    se.ball_line,
    COUNT(*) AS deliveries,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('retired hurt', 'retired out')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
WHERE {condition_se}
  AND se.ball_length IS NOT NULL
  AND se.ball_line IS NOT NULL
GROUP BY se.ball_length, se.ball_line
ORDER BY dismissals DESC, strike_rate ASC;
""".strip()

    phase_shot_sql = f"""
SELECT TOP 20
    CASE
        WHEN FLOOR(se.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(se.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(se.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END AS phase,
    se.shot_played,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('retired hurt', 'retired out')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
WHERE {condition_se}
  AND se.shot_played IS NOT NULL
  AND se.shot_played <> ''
GROUP BY
    CASE
        WHEN FLOOR(se.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(se.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(se.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END,
    se.shot_played
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 5
ORDER BY dismissals DESC, runs DESC;
""".strip()

    shot_summary_df = run_query(shot_summary_sql)
    shot_dismissal_df = run_query(shot_dismissal_sql)
    risky_shots_df = run_query(risky_shots_sql)
    best_shots_df = run_query(best_shots_sql)
    line_length_df = run_query(line_length_sql)
    phase_shot_df = run_query(phase_shot_sql)

    most_used_shot = safe_first_value(shot_summary_df, "shot_played", "unknown shot")
    most_dismissal_shot = safe_first_value(shot_dismissal_df, "shot_played", "unknown shot")
    riskiest_shot = safe_first_value(risky_shots_df, "shot_played", "unknown shot")
    best_shot = safe_first_value(best_shots_df, "shot_played", "unknown shot")
    problem_length = safe_first_value(line_length_df, "ball_length", "unknown length")
    problem_line = safe_first_value(line_length_df, "ball_line", "unknown line")

    paragraph = (
        f"{player_name}'s shot analysis suggests that the most used scoring shot in the dataset is {most_used_shot}. "
        f"The shot linked with the most dismissals is {most_dismissal_shot}, while the risk table flags {riskiest_shot} "
        f"as the shot to be most careful with based on dismissals, batting average, and strike rate. The most productive "
        f"shot by strike rate appears to be {best_shot}. The line-and-length pattern causing the most problems is "
        f"{problem_length} on {problem_line}. This is a data-based batting pattern, so it should be read as a tactical "
        f"suggestion rather than a guaranteed coaching rule."
    )

    summary_rows = [
        {
            "analysis_area": "Overall shot insight",
            "insight": paragraph,
        },
        {
            "analysis_area": "Most used shot",
            "insight": f"The most common scoring shot is {most_used_shot}.",
        },
        {
            "analysis_area": "Dismissal risk",
            "insight": f"The shot most linked with dismissals is {most_dismissal_shot}.",
        },
        {
            "analysis_area": "Shot to be careful with",
            "insight": f"The risk table suggests being careful with {riskiest_shot}.",
        },
        {
            "analysis_area": "Best attacking option",
            "insight": f"The highest strike-rate shot is {best_shot}.",
        },
        {
            "analysis_area": "Problem ball type",
            "insight": f"The most difficult ball pattern appears to be {problem_length} on {problem_line}.",
        },
    ]

    summary_df = pd.DataFrame(summary_rows)

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "shot_summary": shot_summary_df,
        "shot_dismissals": shot_dismissal_df,
        "risky_shots": risky_shots_df,
        "best_shots": best_shots_df,
        "line_length": line_length_df,
        "phase_shots": phase_shot_df,
        "sql_queries": {
            "shot_summary": shot_summary_sql,
            "shot_dismissals": shot_dismissal_sql,
            "risky_shots": risky_shots_sql,
            "best_shots": best_shots_sql,
            "line_length": line_length_sql,
            "phase_shots": phase_shot_sql,
        },
    }