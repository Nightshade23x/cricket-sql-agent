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

def canonical_team_sql(column_name):
    clean_column = f"LOWER(LTRIM(RTRIM(CAST({column_name} AS NVARCHAR(255)))))"

    return f"""
CASE
    WHEN {clean_column} IN ('delhi capitals', 'delhi daredevils') THEN 'Delhi Capitals'
    WHEN {clean_column} IN ('punjab kings', 'kings xi punjab') THEN 'Punjab Kings'
    WHEN {clean_column} IN ('royal challengers bangalore', 'royal challengers bengaluru') THEN 'Royal Challengers Bengaluru'

    WHEN {clean_column} IN ('rising pune supergiant', 'rising pune supergiants') THEN 'Rising Pune Supergiant'
    WHEN {clean_column} IN ('pune warriors', 'pune warriors india') THEN 'Pune Warriors'
    WHEN {clean_column} = 'kochi tuskers kerala' THEN 'Kochi Tuskers Kerala'
    WHEN {clean_column} = 'gujarat lions' THEN 'Gujarat Lions'
    WHEN {clean_column} = 'deccan chargers' THEN 'Deccan Chargers'

    ELSE {column_name}
END
""".strip()


def canonical_venue_sql(column_name):
    return f"""
CASE
    WHEN LOWER({column_name}) LIKE '%chinnaswamy%' THEN 'M Chinnaswamy Stadium'
    WHEN LOWER({column_name}) LIKE '%m chinnaswamy%' THEN 'M Chinnaswamy Stadium'
    WHEN LOWER({column_name}) LIKE '%bengaluru%' AND LOWER({column_name}) LIKE '%chinnaswamy%' THEN 'M Chinnaswamy Stadium'

    WHEN LOWER({column_name}) LIKE '%chidambaram%' THEN 'MA Chidambaram Stadium, Chepauk'
    WHEN LOWER({column_name}) LIKE '%chepauk%' THEN 'MA Chidambaram Stadium, Chepauk'

    WHEN LOWER({column_name}) LIKE '%wankhede%' THEN 'Wankhede Stadium'
    WHEN LOWER({column_name}) LIKE '%eden gardens%' THEN 'Eden Gardens'
    WHEN LOWER({column_name}) LIKE '%arun jaitley%' THEN 'Arun Jaitley Stadium'
    WHEN LOWER({column_name}) LIKE '%feroz shah kotla%' THEN 'Arun Jaitley Stadium'
    WHEN LOWER({column_name}) LIKE '%kotla%' THEN 'Arun Jaitley Stadium'

    WHEN LOWER({column_name}) LIKE '%rajiv gandhi%' THEN 'Rajiv Gandhi International Stadium, Uppal'
    WHEN LOWER({column_name}) LIKE '%uppal%' THEN 'Rajiv Gandhi International Stadium, Uppal'

    WHEN LOWER({column_name}) LIKE '%narendra modi%' THEN 'Narendra Modi Stadium'
    WHEN LOWER({column_name}) LIKE '%motera%' THEN 'Narendra Modi Stadium'
    WHEN LOWER({column_name}) LIKE '%sardar patel%' THEN 'Narendra Modi Stadium'

    WHEN LOWER({column_name}) LIKE '%dy patil%' THEN 'Dr DY Patil Sports Academy'
    WHEN LOWER({column_name}) LIKE '%d y patil%' THEN 'Dr DY Patil Sports Academy'

    WHEN LOWER({column_name}) LIKE '%punjab cricket association%' THEN 'Punjab Cricket Association Stadium'
    WHEN LOWER({column_name}) LIKE '%mohali%' THEN 'Punjab Cricket Association Stadium'
    WHEN LOWER({column_name}) LIKE '%mullanpur%' THEN 'Maharaja Yadavindra Singh International Cricket Stadium, Mullanpur'

    ELSE {column_name}
END
""".strip()


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
    condition_se = condition_d.replace("d.striker", "se.striker")

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
    opponent_team_name = canonical_team_sql("d.bowling_team")
    opponent_sql = f"""
SELECT
    {opponent_team_name} AS opponent,
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
GROUP BY {opponent_team_name}
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
    bowler_matchup_result = analyze_batter_bowler_matchups(condition_se)

    bowler_success_df = bowler_matchup_result["bowler_success"]
    bowler_dismissals_df = bowler_matchup_result["bowler_dismissals"]
    quiet_bowlers_df = bowler_matchup_result["quiet_bowlers"]
    active_quiet_bowlers_df = bowler_matchup_result["active_quiet_bowlers"]
    active_quiet_bowler = safe_first_value(active_quiet_bowlers_df, "bowler", "unknown active/recent bowler")
    preferred_bowler_types_df = bowler_matchup_result["preferred_bowler_types"]
    difficult_bowler_types_df = bowler_matchup_result["difficult_bowler_types"]

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
    top_success_bowler = safe_first_value(bowler_success_df, "bowler", "unknown bowler")
    top_dismissal_bowler = safe_first_value(bowler_dismissals_df, "bowler", "unknown bowler")
    quiet_bowler = safe_first_value(quiet_bowlers_df, "bowler", "unknown bowler")
    preferred_bowler_type = safe_first_value(preferred_bowler_types_df, "bowling_style", "unknown bowling type")
    difficult_bowler_type = safe_first_value(difficult_bowler_types_df, "bowling_style", "unknown bowling type")
    paragraph = (
        f"{player_name}'s IPL profile shows {total_runs} runs, a highest score of {highest_score}, "
        f"{fifties} fifties and {hundreds} hundreds. The overall batting average is "
        f"{format_metric(batting_average)} with a strike rate of {format_metric(strike_rate)}. "
        f"The data suggests the strongest scoring phase is {top_phase}, with the most runs coming against "
        f"{top_opponent} and at {top_venue}. The most common dismissal type is {main_dismissal}. "
        f"Against individual bowlers, the strongest scoring matchup appears to be against {top_success_bowler}, "
        f"while {top_dismissal_bowler} has dismissed the player most often. The bowler who keeps the player quietest "
        f"Historically, the bowler who keeps the player quietest by strike rate is {quiet_bowler}. "
        f"Among bowlers active in the latest database seasons, the most restrictive option is {active_quiet_bowler}."
        f" By bowling type, the player scores fastest against {preferred_bowler_type}. "
        f"while {difficult_bowler_type} appears to be the most restrictive bowling type."
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
            "analysis_area": "Best bowler matchup",
            "insight": f"The strongest scoring matchup appears to be against {top_success_bowler}.",
        },
        {
            "analysis_area": "Most difficult bowler",
            "insight": f"{top_dismissal_bowler} has dismissed the player most often, while {quiet_bowler} keeps the scoring rate lowest.",
        },
        {
            "analysis_area": "Bowling type preference",
            "insight": f"The player scores fastest against {preferred_bowler_type} and is most restricted by {difficult_bowler_type}.",
        },
        {
            "analysis_area": "Dismissal pattern",
            "insight": f"Most common dismissal type is {main_dismissal}.",
        },
        {
            "analysis_area": "Active/recent bowling matchup",
            "insight": f"Among bowlers active in the latest database seasons, {active_quiet_bowler} has kept the player quietest by strike rate.",
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
        "bowler_success": bowler_success_df,
        "bowler_dismissals": bowler_dismissals_df,
        "quiet_bowlers": quiet_bowlers_df,
        "preferred_bowler_types": preferred_bowler_types_df,
        "difficult_bowler_types": difficult_bowler_types_df,
        "active_quiet_bowlers": active_quiet_bowlers_df,
        "sql_queries": {
            "career": career_sql,
            "season_trend": season_sql,
            "phase_performance": phase_sql,
            "opponent_performance": opponent_sql,
            "venue_performance": venue_sql,
            "playoff_performance": playoff_sql,
            "dismissal_types": dismissal_sql,
            "bowler_success": bowler_matchup_result["sql_queries"]["bowler_success"],
            "bowler_dismissals": bowler_matchup_result["sql_queries"]["bowler_dismissals"],
            "quiet_bowlers": bowler_matchup_result["sql_queries"]["quiet_bowlers"],
            "preferred_bowler_types": bowler_matchup_result["sql_queries"]["preferred_bowler_types"],
            "difficult_bowler_types": bowler_matchup_result["sql_queries"]["difficult_bowler_types"],
            "active_quiet_bowlers": bowler_matchup_result["sql_queries"]["active_quiet_bowlers"],
        },
    }

def analyze_batter_bowler_matchups(player_condition):
    """
    Analyse which bowlers a batter succeeds against, struggles against,
    gets dismissed by, and which bowling styles suit/limit the batter.

    player_condition should be something like:
    se.striker = 'V Kohli'
    """

    condition_se = player_condition
    condition_se = condition_se.replace("d.striker", "se.striker")
    condition_se = condition_se.replace("pd.batter", "se.striker")

    bowler_success_sql = f"""
WITH bowler_matchups AS (
    SELECT
        se.bowler,
        COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
        SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        SUM(se.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS dismissals
    FROM dbo.shot_events se
    WHERE {condition_se}
    GROUP BY se.bowler, COALESCE(se.bowling_style_bowler, 'Unknown')
)
SELECT TOP 10
    bowler,
    bowling_style,
    balls_faced,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
    ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average
FROM bowler_matchups
WHERE balls_faced >= 15
ORDER BY runs DESC, strike_rate DESC;
""".strip()

    bowler_dismissals_sql = f"""
SELECT TOP 10
    se.bowler,
    COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
    COUNT(*) AS dismissals
FROM dbo.shot_events se
WHERE {condition_se}
  AND se.player_dismissed = se.striker
  AND se.wicket_type IS NOT NULL
  AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY se.bowler, COALESCE(se.bowling_style_bowler, 'Unknown')
ORDER BY dismissals DESC;
""".strip()

    quiet_bowlers_sql = f"""
WITH bowler_matchups AS (
    SELECT
        se.bowler,
        COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
        SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        SUM(se.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS dismissals
    FROM dbo.shot_events se
    WHERE {condition_se}
    GROUP BY se.bowler, COALESCE(se.bowling_style_bowler, 'Unknown')
)
SELECT TOP 10
    bowler,
    bowling_style,
    balls_faced,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
    ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average
FROM bowler_matchups
WHERE balls_faced >= 15
ORDER BY strike_rate ASC, balls_faced DESC;
""".strip()

    active_quiet_bowlers_sql = f"""
WITH bowler_matchups AS (
    SELECT
        se.bowler,
        COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
        SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        SUM(se.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS dismissals
    FROM dbo.shot_events se
    WHERE {condition_se}
      AND {active_recent_bowler_condition_sql("se.bowler")}
    GROUP BY se.bowler, COALESCE(se.bowling_style_bowler, 'Unknown')
)
SELECT TOP 10
    bowler,
    bowling_style,
    balls_faced,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
    ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average
FROM bowler_matchups
WHERE balls_faced >= 10
ORDER BY strike_rate ASC, balls_faced DESC;
""".strip()

    preferred_bowler_types_sql = f"""
WITH type_matchups AS (
    SELECT
        COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
        SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        SUM(se.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS dismissals
    FROM dbo.shot_events se
    WHERE {condition_se}
      AND se.bowling_style_bowler IS NOT NULL
    GROUP BY COALESCE(se.bowling_style_bowler, 'Unknown')
)
SELECT
    bowling_style,
    balls_faced,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
    ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average
FROM type_matchups
WHERE balls_faced >= 30
ORDER BY strike_rate DESC, runs DESC;
""".strip()

    difficult_bowler_types_sql = f"""
WITH type_matchups AS (
    SELECT
        COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
        SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        SUM(se.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS dismissals
    FROM dbo.shot_events se
    WHERE {condition_se}
      AND se.bowling_style_bowler IS NOT NULL
    GROUP BY COALESCE(se.bowling_style_bowler, 'Unknown')
)
SELECT
    bowling_style,
    balls_faced,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
    ROUND(runs * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average
FROM type_matchups
WHERE balls_faced >= 30
ORDER BY strike_rate ASC, dismissals DESC;
""".strip()

    bowler_success_df = run_query(bowler_success_sql)
    bowler_dismissals_df = run_query(bowler_dismissals_sql)
    quiet_bowlers_df = run_query(quiet_bowlers_sql)
    preferred_bowler_types_df = run_query(preferred_bowler_types_sql)
    difficult_bowler_types_df = run_query(difficult_bowler_types_sql)
    active_quiet_bowlers_df = run_query(active_quiet_bowlers_sql)

    return {
        "bowler_success": bowler_success_df,
        "bowler_dismissals": bowler_dismissals_df,
        "quiet_bowlers": quiet_bowlers_df,
        "preferred_bowler_types": preferred_bowler_types_df,
        "difficult_bowler_types": difficult_bowler_types_df,
        "active_quiet_bowlers": active_quiet_bowlers_df,
        "sql_queries": {
            "bowler_success": bowler_success_sql,
            "bowler_dismissals": bowler_dismissals_sql,
            "quiet_bowlers": quiet_bowlers_sql,
            "preferred_bowler_types": preferred_bowler_types_sql,
            "difficult_bowler_types": difficult_bowler_types_sql,
            "active_quiet_bowlers": active_quiet_bowlers_sql,
        },
    }

def bowling_arm_sql(style_column):
    clean_style = f"LOWER(COALESCE({style_column}, 'unknown'))"

    return f"""
CASE
    WHEN {clean_style} LIKE '%left%' THEN 'Left-arm'
    WHEN {clean_style} LIKE '%right%' THEN 'Right-arm'
    ELSE 'Unknown arm'
END
""".strip()


def bowling_category_sql(style_column):
    clean_style = f"LOWER(COALESCE({style_column}, 'unknown'))"

    return f"""
CASE
    WHEN {clean_style} LIKE '%legbreak%' OR {clean_style} LIKE '%leg break%' THEN 'Leg spin'
    WHEN {clean_style} LIKE '%googly%' THEN 'Leg spin'
    WHEN {clean_style} LIKE '%offbreak%' OR {clean_style} LIKE '%off break%' THEN 'Off spin'
    WHEN {clean_style} LIKE '%slow left%' OR {clean_style} LIKE '%orthodox%' THEN 'Left-arm orthodox spin'
    WHEN {clean_style} LIKE '%chinaman%' OR {clean_style} LIKE '%left arm wrist%' THEN 'Left-arm wrist spin'

    WHEN {clean_style} LIKE '%fast%' THEN 'Pace'
    WHEN {clean_style} LIKE '%medium%' THEN 'Pace'

    ELSE 'Unknown type'
END
""".strip()


def active_recent_bowler_condition_sql(bowler_column):
    """
    Local-only definition of active:
    bowlers who appeared in the latest two IPL seasons available in the database.
    """
    return f"""
{bowler_column} IN (
    SELECT DISTINCT d2.bowler
    FROM deliveries d2
    JOIN matches m2
        ON d2.match_id = m2.match_id
    WHERE YEAR(CAST(m2.start_date AS date)) >= (
        SELECT MAX(YEAR(CAST(start_date AS date))) - 1
        FROM matches
    )
)
""".strip()

def analyze_team_title_chances():
    """
    Explainable team rating based on all-time record, recent form,
    batting strength, bowling strength, and playoff/title record.

    Recent form is weighted more strongly than historical record.
    """

    sql_query = """
WITH match_years AS (
    SELECT
        match_id,
        YEAR(CAST(start_date AS date)) AS season_year
    FROM matches
),
max_year AS (
    SELECT MAX(season_year) AS latest_season_year
    FROM match_years
),
team_matches AS (
    SELECT DISTINCT
        d.match_id,
        d.batting_team AS team,
        m.winner,
        YEAR(CAST(m.start_date AS date)) AS season_year
    FROM deliveries d
    JOIN matches m
        ON d.match_id = m.match_id
),
all_time_win_rates AS (
    SELECT
        team,
        COUNT(*) AS all_time_matches,
        SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) AS all_time_wins,
        ROUND(
            SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS all_time_win_percentage
    FROM team_matches
    GROUP BY team
),
recent_win_rates AS (
    SELECT
        tm.team,
        COUNT(*) AS recent_matches,
        SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) AS recent_wins,
        ROUND(
            SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) * 100.0 /
            NULLIF(COUNT(*), 0),
            2
        ) AS recent_win_percentage
    FROM team_matches tm
    CROSS JOIN max_year my
    WHERE tm.season_year >= my.latest_season_year - 1
    GROUP BY tm.team
),
recent_batting_strength AS (
    SELECT
        batting_team AS team,
        ROUND(AVG(team_score * 1.0), 2) AS recent_avg_score
    FROM (
        SELECT
            d.match_id,
            d.innings,
            d.batting_team,
            YEAR(CAST(m.start_date AS date)) AS season_year,
            SUM(d.runs_off_bat + d.extras) AS team_score
        FROM deliveries d
        JOIN matches m
            ON d.match_id = m.match_id
        CROSS JOIN max_year my
        WHERE d.innings IN (1, 2)
          AND YEAR(CAST(m.start_date AS date)) >= my.latest_season_year - 1
        GROUP BY d.match_id, d.innings, d.batting_team, YEAR(CAST(m.start_date AS date))
    ) AS innings_scores
    GROUP BY batting_team
),
recent_bowling_strength AS (
    SELECT
        bowling_team AS team,
        ROUND(AVG(team_score * 1.0), 2) AS recent_avg_runs_conceded
    FROM (
        SELECT
            d.match_id,
            d.innings,
            d.bowling_team,
            YEAR(CAST(m.start_date AS date)) AS season_year,
            SUM(d.runs_off_bat + d.extras) AS team_score
        FROM deliveries d
        JOIN matches m
            ON d.match_id = m.match_id
        CROSS JOIN max_year my
        WHERE d.innings IN (1, 2)
          AND YEAR(CAST(m.start_date AS date)) >= my.latest_season_year - 1
        GROUP BY d.match_id, d.innings, d.bowling_team, YEAR(CAST(m.start_date AS date))
    ) AS innings_scores
    GROUP BY bowling_team
),
recent_playoff_strength AS (
    SELECT
        team,
        COUNT(*) AS recent_playoff_matches,
        SUM(CASE WHEN winner = team THEN 1 ELSE 0 END) AS recent_playoff_wins,
        SUM(CASE WHEN is_final = 1 AND winner = team THEN 1 ELSE 0 END) AS recent_titles
    FROM (
        SELECT
            ms.match_id,
            ms.season_year,
            ms.winner,
            ms.team_1 AS team,
            ms.is_final
        FROM match_stages ms
        CROSS JOIN max_year my
        WHERE ms.is_playoff = 1
          AND ms.season_year >= my.latest_season_year - 1

        UNION ALL

        SELECT
            ms.match_id,
            ms.season_year,
            ms.winner,
            ms.team_2 AS team,
            ms.is_final
        FROM match_stages ms
        CROSS JOIN max_year my
        WHERE ms.is_playoff = 1
          AND ms.season_year >= my.latest_season_year - 1
    ) AS playoff_teams
    GROUP BY team
)
SELECT TOP 10
    aw.team,
    aw.all_time_matches,
    aw.all_time_wins,
    aw.all_time_win_percentage,
    COALESCE(rw.recent_matches, 0) AS recent_matches,
    COALESCE(rw.recent_wins, 0) AS recent_wins,
    COALESCE(rw.recent_win_percentage, 0) AS recent_win_percentage,
    COALESCE(rb.recent_avg_score, 0) AS recent_avg_score,
    COALESCE(rbo.recent_avg_runs_conceded, 0) AS recent_avg_runs_conceded,
    COALESCE(rp.recent_playoff_matches, 0) AS recent_playoff_matches,
    COALESCE(rp.recent_playoff_wins, 0) AS recent_playoff_wins,
    COALESCE(rp.recent_titles, 0) AS recent_titles,
    ROUND(
        COALESCE(rw.recent_win_percentage, 0) * 0.45
        + aw.all_time_win_percentage * 0.15
        + COALESCE(rb.recent_avg_score, 0) * 0.12
        - COALESCE(rbo.recent_avg_runs_conceded, 0) * 0.10
        + COALESCE(rp.recent_playoff_wins, 0) * 3.0
        + COALESCE(rp.recent_titles, 0) * 8.0,
        2
    ) AS title_chance_score
FROM all_time_win_rates aw
LEFT JOIN recent_win_rates rw
    ON aw.team = rw.team
LEFT JOIN recent_batting_strength rb
    ON aw.team = rb.team
LEFT JOIN recent_bowling_strength rbo
    ON aw.team = rbo.team
LEFT JOIN recent_playoff_strength rp
    ON aw.team = rp.team
WHERE COALESCE(rw.recent_matches, 0) > 0
ORDER BY title_chance_score DESC;
""".strip()

    result = run_query(sql_query)

    top_team = safe_first_value(result, "team", "unknown team")
    top_score = safe_first_value(result, "title_chance_score", None)
    recent_win_percentage = safe_first_value(result, "recent_win_percentage", None)
    all_time_win_percentage = safe_first_value(result, "all_time_win_percentage", None)
    recent_avg_score = safe_first_value(result, "recent_avg_score", None)
    recent_avg_runs_conceded = safe_first_value(result, "recent_avg_runs_conceded", None)
    recent_titles = safe_first_value(result, "recent_titles", 0)

    paragraph = (
        f"The updated title-chance model ranks {top_team} highest with a score of "
        f"{format_metric(top_score)}. This version gives more weight to recent seasons than all-time history, "
        f"so recent wins, recent batting strength, recent bowling strength, and recent playoff/title performance "
        f"matter more than older dominance. {top_team}'s recent win rate is {format_metric(recent_win_percentage)}%, "
        f"compared with an all-time win rate of {format_metric(all_time_win_percentage)}%. The team has a recent "
        f"average score of {format_metric(recent_avg_score)}, recent average runs conceded of "
        f"{format_metric(recent_avg_runs_conceded)}, and {format_metric(recent_titles, 0)} recent titles. "
        f"This is an explainable ranking, not a guaranteed prediction."
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

    venue_name = canonical_venue_sql("tm.venue")

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
    {venue_name} AS venue,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) AS wins,
    ROUND(
        SUM(CASE WHEN tm.winner = tm.team THEN 1 ELSE 0 END) * 100.0 /
        NULLIF(COUNT(*), 0),
        2
    ) AS win_percentage
FROM team_matches tm
WHERE {team_match_condition}
GROUP BY {venue_name}
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
    
    top_run_scorers_sql = f"""
SELECT TOP 10
    d.striker AS batter,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    COUNT(DISTINCT d.match_id) AS matches,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
WHERE {batting_condition}
GROUP BY d.striker
ORDER BY runs DESC;
""".strip()

    top_wicket_takers_sql = f"""
SELECT TOP 10
    d.bowler,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS wickets,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
    ROUND(
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) * 6.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy_rate
FROM deliveries d
WHERE {bowling_condition}
GROUP BY d.bowler
HAVING COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) > 0
ORDER BY wickets DESC, economy_rate ASC;
""".strip()

    overall_df = run_query(overall_sql)
    season_df = run_query(season_sql)
    batting_df = run_query(batting_sql)
    bowling_df = run_query(bowling_sql)
    chase_defend_df = run_query(chase_defend_sql)
    playoff_df = run_query(playoff_sql)
    venue_df = run_query(venue_sql)
    phase_batting_df = run_query(phase_batting_sql)
    top_run_scorers_df = run_query(top_run_scorers_sql)
    top_wicket_takers_df = run_query(top_wicket_takers_sql)

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
        "top_run_scorers": top_run_scorers_df,
        "top_wicket_takers": top_wicket_takers_df,
        "sql_queries": {
            "overall": overall_sql,
            "season_trend": season_sql,
            "batting": batting_sql,
            "bowling": bowling_sql,
            "chase_defend": chase_defend_sql,
            "playoff": playoff_sql,
            "venues": venue_sql,
            "phase_batting": phase_batting_sql,
            "top_run_scorers": top_run_scorers_sql,
            "top_wicket_takers": top_wicket_takers_sql,
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

def analyze_bowler_strategy(bowler_condition):
    """
    Analyse a bowler's strategy using shot_events.

    bowler_condition should be something like:
    se.bowler = 'JJ Bumrah'
    """

    condition_se = bowler_condition
    condition_se = condition_se.replace("d.bowler", "se.bowler")

    bowler_name = extract_player_name_from_condition(condition_se)

    effective_line_length_sql = f"""
WITH line_length_stats AS (
    SELECT
        se.ball_length,
        se.ball_line,
        COUNT(*) AS deliveries,
        SUM(CASE WHEN se.wides IS NULL AND se.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
        SUM(se.runs_off_bat + COALESCE(se.wides, 0) + COALESCE(se.noballs, 0)) AS runs_conceded,
        COUNT(CASE
            WHEN se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets
    FROM dbo.shot_events se
    WHERE {condition_se}
      AND se.ball_length IS NOT NULL
      AND se.ball_line IS NOT NULL
    GROUP BY se.ball_length, se.ball_line
)
SELECT TOP 10
    ball_length,
    ball_line,
    deliveries,
    legal_balls,
    runs_conceded,
    wickets,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy_rate,
    ROUND(legal_balls * 1.0 / NULLIF(wickets, 0), 2) AS balls_per_wicket
FROM line_length_stats
WHERE legal_balls >= 10
ORDER BY wickets DESC, economy_rate ASC, balls_per_wicket ASC;
""".strip()

    expensive_line_length_sql = f"""
WITH line_length_stats AS (
    SELECT
        se.ball_length,
        se.ball_line,
        COUNT(*) AS deliveries,
        SUM(CASE WHEN se.wides IS NULL AND se.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
        SUM(se.runs_off_bat + COALESCE(se.wides, 0) + COALESCE(se.noballs, 0)) AS runs_conceded,
        COUNT(CASE
            WHEN se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets
    FROM dbo.shot_events se
    WHERE {condition_se}
      AND se.ball_length IS NOT NULL
      AND se.ball_line IS NOT NULL
    GROUP BY se.ball_length, se.ball_line
)
SELECT TOP 10
    ball_length,
    ball_line,
    deliveries,
    legal_balls,
    runs_conceded,
    wickets,
    ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy_rate
FROM line_length_stats
WHERE legal_balls >= 10
ORDER BY economy_rate DESC, runs_conceded DESC;
""".strip()

    shots_conceded_sql = f"""
SELECT TOP 15
    se.shot_played,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    SUM(se.runs_off_bat) AS runs_scored,
    SUM(CASE WHEN se.runs_off_bat IN (4, 6) THEN 1 ELSE 0 END) AS boundaries,
    COUNT(CASE
        WHEN se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS wickets,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS batting_strike_rate_against
FROM dbo.shot_events se
WHERE {condition_se}
  AND se.shot_played IS NOT NULL
  AND se.shot_played <> ''
GROUP BY se.shot_played
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 10
ORDER BY runs_scored DESC, batting_strike_rate_against DESC;
""".strip()

    wicket_shots_sql = f"""
SELECT TOP 15
    se.shot_played,
    se.wicket_type,
    COUNT(*) AS wickets
FROM dbo.shot_events se
WHERE {condition_se}
  AND se.shot_played IS NOT NULL
  AND se.shot_played <> ''
  AND se.wicket_type IS NOT NULL
  AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY se.shot_played, se.wicket_type
ORDER BY wickets DESC;
""".strip()

    handedness_sql = f"""
SELECT
    se.batting_style_striker AS batter_type,
    SUM(CASE WHEN se.wides IS NULL AND se.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat + COALESCE(se.wides, 0) + COALESCE(se.noballs, 0)) AS runs_conceded,
    COUNT(CASE
        WHEN se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS wickets,
    ROUND(
        SUM(se.runs_off_bat + COALESCE(se.wides, 0) + COALESCE(se.noballs, 0)) * 6.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL AND se.noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy_rate,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS batting_strike_rate_against
FROM dbo.shot_events se
WHERE {condition_se}
  AND se.batting_style_striker IS NOT NULL
GROUP BY se.batting_style_striker
ORDER BY wickets DESC, economy_rate ASC;
""".strip()

    phase_sql = f"""
SELECT
    CASE
        WHEN FLOOR(se.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(se.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(se.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END AS phase,
    SUM(CASE WHEN se.wides IS NULL AND se.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat + COALESCE(se.wides, 0) + COALESCE(se.noballs, 0)) AS runs_conceded,
    COUNT(CASE
        WHEN se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS wickets,
    ROUND(
        SUM(se.runs_off_bat + COALESCE(se.wides, 0) + COALESCE(se.noballs, 0)) * 6.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL AND se.noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy_rate,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS batting_strike_rate_against
FROM dbo.shot_events se
WHERE {condition_se}
GROUP BY
    CASE
        WHEN FLOOR(se.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(se.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(se.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END
ORDER BY wickets DESC, economy_rate ASC;
""".strip()

    effective_line_length_df = run_query(effective_line_length_sql)
    expensive_line_length_df = run_query(expensive_line_length_sql)
    shots_conceded_df = run_query(shots_conceded_sql)
    wicket_shots_df = run_query(wicket_shots_sql)
    handedness_df = run_query(handedness_sql)
    phase_df = run_query(phase_sql)

    best_length = safe_first_value(effective_line_length_df, "ball_length", "unknown length")
    best_line = safe_first_value(effective_line_length_df, "ball_line", "unknown line")

    worst_length = safe_first_value(expensive_line_length_df, "ball_length", "unknown length")
    worst_line = safe_first_value(expensive_line_length_df, "ball_line", "unknown line")

    most_scored_shot = safe_first_value(shots_conceded_df, "shot_played", "unknown shot")
    wicket_shot = safe_first_value(wicket_shots_df, "shot_played", "unknown shot")
    best_phase = safe_first_value(phase_df, "phase", "unknown phase")

    paragraph = (
        f"{bowler_name}'s bowling strategy profile suggests that the most effective line-and-length pattern is "
        f"{best_length} on {best_line}, based on wickets, economy rate, and balls per wicket. The most expensive "
        f"pattern appears to be {worst_length} on {worst_line}. Batters score most often through the {most_scored_shot} "
        f"against this bowler, while wickets are most often linked with batters playing the {wicket_shot}. Phase-wise, "
        f"the strongest wicket-taking phase appears to be the {best_phase}. This should be treated as a data-based "
        f"tactical suggestion rather than a guaranteed bowling plan."
    )

    summary_rows = [
        {
            "analysis_area": "Overall bowling strategy",
            "insight": paragraph,
        },
        {
            "analysis_area": "Best line and length",
            "insight": f"The most effective pattern is {best_length} on {best_line}.",
        },
        {
            "analysis_area": "Pattern to avoid",
            "insight": f"The most expensive pattern is {worst_length} on {worst_line}.",
        },
        {
            "analysis_area": "Shot conceded most",
            "insight": f"Batters score most often through the {most_scored_shot}.",
        },
        {
            "analysis_area": "Wicket shot pattern",
            "insight": f"Wickets are most often linked with batters playing the {wicket_shot}.",
        },
        {
            "analysis_area": "Best phase",
            "insight": f"The strongest wicket-taking phase appears to be the {best_phase}.",
        },
    ]

    summary_df = pd.DataFrame(summary_rows)

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "effective_line_length": effective_line_length_df,
        "expensive_line_length": expensive_line_length_df,
        "shots_conceded": shots_conceded_df,
        "wicket_shots": wicket_shots_df,
        "handedness": handedness_df,
        "phases": phase_df,
        "sql_queries": {
            "effective_line_length": effective_line_length_sql,
            "expensive_line_length": expensive_line_length_sql,
            "shots_conceded": shots_conceded_sql,
            "wicket_shots": wicket_shots_sql,
            "handedness": handedness_sql,
            "phases": phase_sql,
        },
    }

def analyze_batter_bowling_plan(player_condition, phase_condition=None, phase_label="all overs", forced_mode=None):
    """
    Builds a bowling plan against a batter using shot_events.

    player_condition should use se.striker, for example:
    se.striker = 'N Pooran'

    forced_mode can be:
    - None
    - "spin"
    - "pace"
    """

    condition_se = player_condition
    condition_se = condition_se.replace("d.striker", "se.striker")
    condition_se = condition_se.replace("pd.batter", "se.striker")

    where_clauses = [condition_se]

    if phase_condition is not None:
        phase_condition = phase_condition.replace("d.ball", "se.ball")
        where_clauses.append(phase_condition)

    if forced_mode == "spin":
        where_clauses.append(f"{bowling_category_sql('se.bowling_style_bowler')} LIKE '%spin%'")

    if forced_mode == "pace":
        where_clauses.append(f"{bowling_category_sql('se.bowling_style_bowler')} = 'Pace'")

    where_sql = " AND ".join(where_clauses)

    bowling_arm_expr = bowling_arm_sql("se.bowling_style_bowler")
    bowling_category_expr = bowling_category_sql("se.bowling_style_bowler")
    active_condition = active_recent_bowler_condition_sql("se.bowler")

    length_sql = f"""
SELECT
    COALESCE(se.ball_length, 'Unknown') AS ball_length,
    COUNT(*) AS balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(SUM(se.runs_off_bat) * 100.0 / NULLIF(COUNT(*), 0), 2) AS strike_rate
FROM dbo.shot_events se
WHERE {where_sql}
  AND se.ball_length IS NOT NULL
GROUP BY COALESCE(se.ball_length, 'Unknown')
HAVING COUNT(*) >= 5
ORDER BY strike_rate ASC, dismissals DESC, balls DESC;
""".strip()

    line_sql = f"""
SELECT
    COALESCE(se.ball_line, 'Unknown') AS ball_line,
    COUNT(*) AS balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(SUM(se.runs_off_bat) * 100.0 / NULLIF(COUNT(*), 0), 2) AS strike_rate
FROM dbo.shot_events se
WHERE {where_sql}
  AND se.ball_line IS NOT NULL
GROUP BY COALESCE(se.ball_line, 'Unknown')
HAVING COUNT(*) >= 5
ORDER BY strike_rate ASC, dismissals DESC, balls DESC;
""".strip()

    bowling_type_sql_query = f"""
SELECT
    {bowling_category_expr} AS bowling_type,
    {bowling_arm_expr} AS bowling_arm,
    COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
    COUNT(*) AS balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(SUM(se.runs_off_bat) * 100.0 / NULLIF(COUNT(*), 0), 2) AS strike_rate
FROM dbo.shot_events se
WHERE {where_sql}
  AND se.bowling_style_bowler IS NOT NULL
GROUP BY
    {bowling_category_expr},
    {bowling_arm_expr},
    COALESCE(se.bowling_style_bowler, 'Unknown')
HAVING COUNT(*) >= 8
ORDER BY strike_rate ASC, dismissals DESC, balls DESC;
""".strip()

    pace_sql = f"""
SELECT
    {bowling_arm_expr} AS bowling_arm,
    COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
    COALESCE(se.ball_length, 'Unknown') AS ball_length,
    COALESCE(se.ball_line, 'Unknown') AS ball_line,
    COUNT(*) AS balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(SUM(se.runs_off_bat) * 100.0 / NULLIF(COUNT(*), 0), 2) AS strike_rate
FROM dbo.shot_events se
WHERE {where_sql}
  AND {bowling_category_expr} = 'Pace'
GROUP BY
    {bowling_arm_expr},
    COALESCE(se.bowling_style_bowler, 'Unknown'),
    COALESCE(se.ball_length, 'Unknown'),
    COALESCE(se.ball_line, 'Unknown')
HAVING COUNT(*) >= 5
ORDER BY strike_rate ASC, dismissals DESC, balls DESC;
""".strip()

    spin_sql = f"""
SELECT
    {bowling_arm_expr} AS bowling_arm,
    {bowling_category_expr} AS spin_type,
    COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
    COALESCE(se.ball_length, 'Unknown') AS ball_length,
    COALESCE(se.ball_line, 'Unknown') AS ball_line,
    COUNT(*) AS balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(SUM(se.runs_off_bat) * 100.0 / NULLIF(COUNT(*), 0), 2) AS strike_rate
FROM dbo.shot_events se
WHERE {where_sql}
  AND {bowling_category_expr} LIKE '%spin%'
GROUP BY
    {bowling_arm_expr},
    {bowling_category_expr},
    COALESCE(se.bowling_style_bowler, 'Unknown'),
    COALESCE(se.ball_length, 'Unknown'),
    COALESCE(se.ball_line, 'Unknown')
HAVING COUNT(*) >= 5
ORDER BY strike_rate ASC, dismissals DESC, balls DESC;
""".strip()

    active_bowlers_sql = f"""
SELECT TOP 10
    se.bowler,
    {bowling_arm_expr} AS bowling_arm,
    {bowling_category_expr} AS bowling_type,
    COALESCE(se.bowling_style_bowler, 'Unknown') AS bowling_style,
    COUNT(*) AS balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(SUM(se.runs_off_bat) * 100.0 / NULLIF(COUNT(*), 0), 2) AS strike_rate
FROM dbo.shot_events se
WHERE {where_sql}
  AND {active_condition}
GROUP BY
    se.bowler,
    {bowling_arm_expr},
    {bowling_category_expr},
    COALESCE(se.bowling_style_bowler, 'Unknown')
HAVING COUNT(*) >= 5
ORDER BY strike_rate ASC, dismissals DESC, balls DESC;
""".strip()

    length_df = run_query(length_sql)
    line_df = run_query(line_sql)
    bowling_type_df = run_query(bowling_type_sql_query)
    pace_df = run_query(pace_sql)
    spin_df = run_query(spin_sql)
    active_bowlers_df = run_query(active_bowlers_sql)

    best_length = safe_first_value(length_df, "ball_length", "unknown length")
    best_line = safe_first_value(line_df, "ball_line", "unknown line")
    best_type = safe_first_value(bowling_type_df, "bowling_style", "unknown bowling style")
    best_pace_arm = safe_first_value(pace_df, "bowling_arm", "unknown arm")
    best_pace_length = safe_first_value(pace_df, "ball_length", "unknown length")
    best_spin_type = safe_first_value(spin_df, "spin_type", "unknown spin type")
    best_spin_arm = safe_first_value(spin_df, "bowling_arm", "unknown arm")
    best_spin_length = safe_first_value(spin_df, "ball_length", "unknown length")
    best_active_bowler = safe_first_value(active_bowlers_df, "bowler", "unknown active/recent bowler")

    if forced_mode == "spin":
        paragraph = (
            f"If spin has to be bowled to this batter in {phase_label}, the data suggests using "
            f"{best_spin_arm} {best_spin_type}, ideally around a {best_spin_length} length. "
            f"Historically, the most restrictive overall length is {best_length}, and the most restrictive line is {best_line}. "
            f"Among bowlers active in the latest database seasons, {best_active_bowler} has the best record by this filter."
        )
    elif forced_mode == "pace":
        paragraph = (
            f"If pace has to be bowled to this batter in {phase_label}, the data suggests using "
            f"{best_pace_arm} pace, ideally around a {best_pace_length} length. "
            f"Historically, the most restrictive overall length is {best_length}, and the most restrictive line is {best_line}. "
            f"Among bowlers active in the latest database seasons, {best_active_bowler} has the best record by this filter."
        )
    else:
        paragraph = (
            f"For this batter in {phase_label}, the data suggests bowling a {best_length} length and {best_line} line. "
            f"The most restrictive bowling style historically is {best_type}. "
            f"If choosing pace, the best option appears to be {best_pace_arm} pace on a {best_pace_length} length. "
            f"If forced to bowl spin, the best option appears to be {best_spin_arm} {best_spin_type} on a {best_spin_length} length. "
            f"Among bowlers active in the latest database seasons, {best_active_bowler} has the best record by this filter."
        )

    summary_df = run_query(f"""
SELECT
    'Recommended length' AS analysis_area,
    '{best_length}' AS insight
UNION ALL
SELECT
    'Recommended line',
    '{best_line}'
UNION ALL
SELECT
    'Best historical bowling style',
    '{best_type}'
UNION ALL
SELECT
    'Best pace option',
    '{best_pace_arm} pace, {best_pace_length} length'
UNION ALL
SELECT
    'Best spin option',
    '{best_spin_arm} {best_spin_type}, {best_spin_length} length'
UNION ALL
SELECT
    'Best active/recent bowler',
    '{best_active_bowler}'
""")

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "best_lengths": length_df,
        "best_lines": line_df,
        "bowling_types": bowling_type_df,
        "pace_options": pace_df,
        "spin_options": spin_df,
        "active_bowler_options": active_bowlers_df,
        "sql_queries": {
            "best_lengths": length_sql,
            "best_lines": line_sql,
            "bowling_types": bowling_type_sql_query,
            "pace_options": pace_sql,
            "spin_options": spin_sql,
            "active_bowler_options": active_bowlers_sql,
        },
    }

def analyze_match_summaries(match_filter_sql, context_label, limit=5):
    """
    Return match summaries with result, scoreline, top scorer, and top wicket-taker.

    match_filter_sql should use aliases:
    - m for matches
    - ms for match_stages
    """

    limit = int(max(1, min(limit, 20)))

    summary_sql = f"""
WITH selected_matches AS (
    SELECT TOP {limit}
        m.match_id,
        COALESCE(ms.season_year, YEAR(CAST(m.start_date AS date))) AS season_year,
        m.season,
        m.start_date,
        m.venue,
        m.city,
        m.winner,
        m.winner_runs,
        m.winner_wickets,
        ms.match_stage,
        ms.is_final,
        CASE
            WHEN m.winner_runs IS NOT NULL THEN CONCAT('won by ', CAST(CAST(m.winner_runs AS INT) AS VARCHAR(20)), ' runs')
            WHEN m.winner_wickets IS NOT NULL THEN CONCAT('won by ', CAST(CAST(m.winner_wickets AS INT) AS VARCHAR(20)), ' wickets')
            ELSE 'result recorded'
        END AS margin
    FROM matches m
    LEFT JOIN match_stages ms
        ON m.match_id = ms.match_id
    WHERE {match_filter_sql}
    ORDER BY m.start_date DESC, m.match_id DESC
),
match_teams AS (
    SELECT
        d.match_id,
        MIN(d.batting_team) AS team_1,
        MAX(d.batting_team) AS team_2
    FROM (
        SELECT DISTINCT
            match_id,
            batting_team
        FROM deliveries
    ) d
    JOIN selected_matches sm
        ON d.match_id = sm.match_id
    GROUP BY d.match_id
),
innings_scores AS (
    SELECT
        d.match_id,
        d.innings,
        d.batting_team,
        SUM(d.runs_off_bat + d.extras) AS team_score,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('retired hurt', 'retired out')
            THEN 1
        END) AS wickets_lost
    FROM deliveries d
    JOIN selected_matches sm
        ON d.match_id = sm.match_id
    WHERE d.innings IN (1, 2)
    GROUP BY d.match_id, d.innings, d.batting_team
),
scoreline AS (
    SELECT
        match_id,
        MAX(CASE WHEN innings = 1 THEN batting_team END) AS innings_1_team,
        MAX(CASE WHEN innings = 1 THEN team_score END) AS innings_1_score,
        MAX(CASE WHEN innings = 1 THEN wickets_lost END) AS innings_1_wickets,
        MAX(CASE WHEN innings = 2 THEN batting_team END) AS innings_2_team,
        MAX(CASE WHEN innings = 2 THEN team_score END) AS innings_2_score,
        MAX(CASE WHEN innings = 2 THEN wickets_lost END) AS innings_2_wickets
    FROM innings_scores
    GROUP BY match_id
),
batter_innings AS (
    SELECT
        d.match_id,
        d.innings,
        d.striker AS batter,
        d.batting_team,
        SUM(d.runs_off_bat) AS runs,
        SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls
    FROM deliveries d
    JOIN selected_matches sm
        ON d.match_id = sm.match_id
    GROUP BY d.match_id, d.innings, d.striker, d.batting_team
),
ranked_batters AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY match_id
            ORDER BY runs DESC, balls ASC
        ) AS batter_rank
    FROM batter_innings
),
bowler_figures AS (
    SELECT
        d.match_id,
        d.innings,
        d.bowler,
        d.bowling_team,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
        SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls
    FROM deliveries d
    JOIN selected_matches sm
        ON d.match_id = sm.match_id
    GROUP BY d.match_id, d.innings, d.bowler, d.bowling_team
),
ranked_bowlers AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY match_id
            ORDER BY wickets DESC, runs_conceded ASC, legal_balls DESC
        ) AS bowler_rank
    FROM bowler_figures
    WHERE wickets > 0
)
SELECT
    sm.match_id,
    sm.season_year,
    sm.start_date,
    COALESCE(sm.match_stage, 'League Match') AS match_stage,
    mt.team_1,
    mt.team_2,
    sm.winner,
    sm.margin,
    sm.venue,
    sc.innings_1_team,
    sc.innings_1_score,
    sc.innings_1_wickets,
    sc.innings_2_team,
    sc.innings_2_score,
    sc.innings_2_wickets,
    rb.batter AS top_scorer,
    rb.batting_team AS top_scorer_team,
    rb.runs AS top_scorer_runs,
    rb.balls AS top_scorer_balls,
    rbo.bowler AS top_wicket_taker,
    rbo.bowling_team AS top_wicket_taker_team,
    rbo.wickets AS top_wicket_taker_wickets,
    rbo.runs_conceded AS top_wicket_taker_runs_conceded,
    CONCAT(
        sm.winner,
        ' ',
        sm.margin,
        '. Top scorer: ',
        COALESCE(rb.batter, 'N/A'),
        ' with ',
        COALESCE(CAST(rb.runs AS VARCHAR(20)), '0'),
        ' runs. Top wicket-taker: ',
        COALESCE(rbo.bowler, 'N/A'),
        ' with ',
        COALESCE(CAST(rbo.wickets AS VARCHAR(20)), '0'),
        ' wickets.'
    ) AS game_summary
FROM selected_matches sm
LEFT JOIN match_teams mt
    ON sm.match_id = mt.match_id
LEFT JOIN scoreline sc
    ON sm.match_id = sc.match_id
LEFT JOIN ranked_batters rb
    ON sm.match_id = rb.match_id
    AND rb.batter_rank = 1
LEFT JOIN ranked_bowlers rbo
    ON sm.match_id = rbo.match_id
    AND rbo.bowler_rank = 1
ORDER BY sm.start_date DESC, sm.match_id DESC;
""".strip()

    result = run_query(summary_sql)

    if result is None or result.empty:
        paragraph = f"No matches found for {context_label}."
    elif limit == 1:
        paragraph = str(result.iloc[0]["game_summary"])
    else:
        paragraph = f"Found {len(result)} matches for {context_label}. The latest match summary is: {result.iloc[0]['game_summary']}"

    return {
        "paragraph": paragraph,
        "summary": result,
        "match_summaries": result,
        "sql_query": summary_sql,
    }