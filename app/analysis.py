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
def empty_dataframe():
    return pd.DataFrame()

def analyze_bowler_length_plan_against_batter(
    bowler_condition,
    batter_condition,
    phase_condition=None,
    phase_label=None,
    venue_condition=None,
):
    """
    Bowler-specific length/line plan against a batter.

    Uses actual shot_events columns:
    - ball_length
    - ball_line
    - shot_played
    - shot_direction

    Fallback logic:
    1. Direct bowler vs batter.
    2. Bowler vs same batting style as batter.
    3. Batter vs same bowling style as bowler.
    """

    def sql_literal(value):
        if value is None:
            return "NULL"
        return "'" + str(value).replace("'", "''") + "'"

    def build_length_line_sql(where_clause, min_balls=3):
        return f"""
WITH length_line_base AS (
    SELECT
        se.ball_length,
        se.ball_line,
        COUNT(*) AS balls,
        SUM(se.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS dismissals,
        SUM(CASE
            WHEN se.wides IS NULL THEN 1
            ELSE 0
        END) AS balls_faced,
        SUM(CASE
            WHEN se.wides IS NULL AND se.noballs IS NULL THEN 1
            ELSE 0
        END) AS legal_balls,
        SUM(se.runs_off_bat + COALESCE(se.wides, 0) + COALESCE(se.noballs, 0)) AS total_runs_conceded
    FROM shot_events se
    JOIN matches m
        ON se.match_id = m.match_id
    WHERE {where_clause}
      AND se.ball_length IS NOT NULL
      AND se.ball_line IS NOT NULL
    GROUP BY
        se.ball_length,
        se.ball_line
),
scored AS (
    SELECT
        ball_length,
        ball_line,
        balls,
        runs,
        dismissals,
        ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
        ROUND(total_runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy,
        ROUND(
            dismissals * 25.0
            +
            CASE
                WHEN balls >= 18 THEN 8
                WHEN balls >= 12 THEN 5
                WHEN balls >= 6 THEN 2
                ELSE 0
            END
            +
            CASE
                WHEN runs * 100.0 / NULLIF(balls_faced, 0) <= 100 THEN 8
                WHEN runs * 100.0 / NULLIF(balls_faced, 0) <= 125 THEN 5
                WHEN runs * 100.0 / NULLIF(balls_faced, 0) <= 150 THEN 2
                ELSE 0
            END
            -
            CASE
                WHEN dismissals = 0
                     AND runs * 100.0 / NULLIF(balls_faced, 0) >= 170
                THEN 8
                ELSE 0
            END,
            2
        ) AS plan_score,
        CASE
            WHEN dismissals >= 2 THEN 'Strong wicket-taking length/line'
            WHEN dismissals = 1 AND runs * 100.0 / NULLIF(balls_faced, 0) <= 130 THEN 'Useful wicket and control option'
            WHEN dismissals = 0 AND runs * 100.0 / NULLIF(balls_faced, 0) <= 110 THEN 'Control option, but no dismissal evidence'
            WHEN balls < 6 THEN 'Very small sample'
            ELSE 'Limited advantage'
        END AS plan_reason
    FROM length_line_base
    WHERE balls >= {min_balls}
)
SELECT TOP 10
    ball_length,
    ball_line,
    balls,
    runs,
    dismissals,
    strike_rate,
    economy,
    plan_score,
    plan_reason
FROM scored
ORDER BY
    plan_score DESC,
    dismissals DESC,
    strike_rate ASC,
    balls DESC;
""".strip()

    def build_shots_sql(where_clause):
        return f"""
WITH shot_base AS (
    SELECT
        se.shot_played,
        COUNT(*) AS balls,
        SUM(se.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS dismissals,
        SUM(CASE
            WHEN se.wides IS NULL THEN 1
            ELSE 0
        END) AS balls_faced
    FROM shot_events se
    JOIN matches m
        ON se.match_id = m.match_id
    WHERE {where_clause}
      AND se.shot_played IS NOT NULL
    GROUP BY se.shot_played
)
SELECT TOP 10
    shot_played,
    balls,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
    CASE
        WHEN dismissals >= 1 THEN 'Dismissal risk shot'
        WHEN runs * 100.0 / NULLIF(balls_faced, 0) <= 100 THEN 'Controlled shot option'
        ELSE 'Scoring shot'
    END AS shot_reason
FROM shot_base
WHERE balls >= 2
ORDER BY
    dismissals DESC,
    strike_rate ASC,
    balls DESC;
""".strip()

    def build_direction_sql(where_clause):
        return f"""
WITH direction_base AS (
    SELECT
        se.shot_direction,
        COUNT(*) AS balls,
        SUM(se.runs_off_bat) AS runs,
        COUNT(CASE
            WHEN se.player_dismissed = se.striker
                 AND se.wicket_type IS NOT NULL
                 AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS dismissals,
        SUM(CASE
            WHEN se.wides IS NULL THEN 1
            ELSE 0
        END) AS balls_faced
    FROM shot_events se
    JOIN matches m
        ON se.match_id = m.match_id
    WHERE {where_clause}
      AND se.shot_direction IS NOT NULL
    GROUP BY se.shot_direction
)
SELECT TOP 10
    shot_direction,
    balls,
    runs,
    dismissals,
    ROUND(runs * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate
FROM direction_base
WHERE balls >= 2
ORDER BY
    dismissals DESC,
    strike_rate ASC,
    balls DESC;
""".strip()

    direct_filters = [
        bowler_condition,
        batter_condition,
    ]

    if phase_condition is not None:
        direct_filters.append(phase_condition)

    if venue_condition is not None:
        direct_filters.append(venue_condition)

    direct_where_clause = " AND ".join(direct_filters)

    direct_summary_sql = f"""
SELECT
    COUNT(*) AS direct_balls,
    SUM(se.runs_off_bat) AS direct_runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS direct_dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS direct_strike_rate
FROM shot_events se
JOIN matches m
    ON se.match_id = m.match_id
WHERE {direct_where_clause};
""".strip()

    batter_profile_sql = f"""
SELECT TOP 1
    se.batting_style_striker
FROM shot_events se
WHERE {batter_condition}
  AND se.batting_style_striker IS NOT NULL
GROUP BY se.batting_style_striker
ORDER BY COUNT(*) DESC;
""".strip()

    bowler_profile_sql = f"""
SELECT TOP 1
    se.bowling_style_bowler
FROM shot_events se
WHERE {bowler_condition}
  AND se.bowling_style_bowler IS NOT NULL
GROUP BY se.bowling_style_bowler
ORDER BY COUNT(*) DESC;
""".strip()

    direct_length_line_sql = build_length_line_sql(direct_where_clause, min_balls=3)
    direct_shots_sql = build_shots_sql(direct_where_clause)
    direct_direction_sql = build_direction_sql(direct_where_clause)

    direct_length_line_df = run_query(direct_length_line_sql)
    direct_shots_df = run_query(direct_shots_sql)
    direct_direction_df = run_query(direct_direction_sql)
    direct_summary_df = run_query(direct_summary_sql)

    batter_profile_df = run_query(batter_profile_sql)
    bowler_profile_df = run_query(bowler_profile_sql)

    direct_balls = safe_first_value(direct_summary_df, "direct_balls", 0)
    batter_style = safe_first_value(batter_profile_df, "batting_style_striker", None)
    bowler_style = safe_first_value(bowler_profile_df, "bowling_style_bowler", None)

    proxy_bowler_style_df = pd.DataFrame()
    proxy_batter_style_df = pd.DataFrame()
    proxy_bowler_style_sql = ""
    proxy_batter_style_sql = ""

    proxy_shots_df = pd.DataFrame()
    proxy_direction_df = pd.DataFrame()
    proxy_shots_sql = ""
    proxy_direction_sql = ""

    proxy_balls = 0
    used_proxy = False
    recommendation_source = "direct matchup"

    direct_has_plan = direct_length_line_df is not None and not direct_length_line_df.empty
    direct_sample_ok = direct_balls is not None and float(direct_balls) >= 12

    if batter_style is not None:
        proxy_filters = [
            bowler_condition,
            f"se.batting_style_striker = {sql_literal(batter_style)}",
        ]

        if phase_condition is not None:
            proxy_filters.append(phase_condition)

        if venue_condition is not None:
            proxy_filters.append(venue_condition)

        proxy_bowler_style_where = " AND ".join(proxy_filters)
        proxy_bowler_style_sql = build_length_line_sql(proxy_bowler_style_where, min_balls=8)
        proxy_bowler_style_df = run_query(proxy_bowler_style_sql)

    if bowler_style is not None:
        proxy_filters = [
            batter_condition,
            f"se.bowling_style_bowler = {sql_literal(bowler_style)}",
        ]

        if phase_condition is not None:
            proxy_filters.append(phase_condition)

        if venue_condition is not None:
            proxy_filters.append(venue_condition)

        proxy_batter_style_where = " AND ".join(proxy_filters)
        proxy_batter_style_sql = build_length_line_sql(proxy_batter_style_where, min_balls=8)
        proxy_batter_style_df = run_query(proxy_batter_style_sql)

    final_plan_df = direct_length_line_df

    if direct_has_plan and direct_sample_ok:
        final_plan_df = direct_length_line_df
        recommendation_source = "direct matchup"
        proxy_balls = 0
        used_proxy = False
        proxy_shots_df = direct_shots_df
        proxy_direction_df = direct_direction_df

    elif proxy_bowler_style_df is not None and not proxy_bowler_style_df.empty:
        final_plan_df = proxy_bowler_style_df
        recommendation_source = f"proxy: bowler vs {batter_style} batters"
        proxy_balls = safe_first_value(proxy_bowler_style_df, "balls", 0)
        used_proxy = True

        proxy_filters = [
            bowler_condition,
            f"se.batting_style_striker = {sql_literal(batter_style)}",
        ]

        if phase_condition is not None:
            proxy_filters.append(phase_condition)

        if venue_condition is not None:
            proxy_filters.append(venue_condition)

        proxy_where = " AND ".join(proxy_filters)
        proxy_shots_sql = build_shots_sql(proxy_where)
        proxy_direction_sql = build_direction_sql(proxy_where)
        proxy_shots_df = run_query(proxy_shots_sql)
        proxy_direction_df = run_query(proxy_direction_sql)

    elif proxy_batter_style_df is not None and not proxy_batter_style_df.empty:
        final_plan_df = proxy_batter_style_df
        recommendation_source = f"proxy: batter vs {bowler_style} bowling"
        proxy_balls = safe_first_value(proxy_batter_style_df, "balls", 0)
        used_proxy = True

        proxy_filters = [
            batter_condition,
            f"se.bowling_style_bowler = {sql_literal(bowler_style)}",
        ]

        if phase_condition is not None:
            proxy_filters.append(phase_condition)

        if venue_condition is not None:
            proxy_filters.append(venue_condition)

        proxy_where = " AND ".join(proxy_filters)
        proxy_shots_sql = build_shots_sql(proxy_where)
        proxy_direction_sql = build_direction_sql(proxy_where)
        proxy_shots_df = run_query(proxy_shots_sql)
        proxy_direction_df = run_query(proxy_direction_sql)

    else:
        final_plan_df = direct_length_line_df
        recommendation_source = "direct matchup only, but sample is too small"
        proxy_balls = 0
        used_proxy = False
        proxy_shots_df = direct_shots_df
        proxy_direction_df = direct_direction_df

    bowler_name = extract_player_name_from_condition(bowler_condition)
    batter_name = extract_player_name_from_condition(batter_condition)

    best_length = safe_first_value(final_plan_df, "ball_length", "unknown length")
    best_line = safe_first_value(final_plan_df, "ball_line", "unknown line")
    best_reason = safe_first_value(final_plan_df, "plan_reason", "limited evidence")
    risky_shot = safe_first_value(proxy_shots_df, "shot_played", safe_first_value(direct_shots_df, "shot_played", "unknown shot"))
    risky_direction = safe_first_value(proxy_direction_df, "shot_direction", safe_first_value(direct_direction_df, "shot_direction", "unknown direction"))

    confidence, confidence_reason = get_tactical_confidence(
        direct_balls=direct_balls,
        proxy_balls=proxy_balls,
        used_proxy=used_proxy,
        venue_condition=venue_condition,
    )

    phase_text = f" in the {phase_label}" if phase_label else ""

    if final_plan_df is None or final_plan_df.empty:
        paragraph = (
            f"I could not find enough direct or proxy length/line data for {bowler_name} bowling to {batter_name}{phase_text}. "
            f"The direct sample has {direct_balls} balls."
        )
    else:
        paragraph = (
            f"For {bowler_name} against {batter_name}{phase_text}, the recommended plan is to bowl a "
            f"{best_length} length around the {best_line} line. Source used: {recommendation_source}. "
            f"Reason: {best_reason}. The shot to watch is {risky_shot}, usually toward {risky_direction}. "
            f"The direct sample is {direct_balls} balls, so proxy evidence is used when the direct matchup is too small. "
            f"Confidence: {confidence} — {confidence_reason}"
        )

    summary_df = pd.DataFrame(
        [
            {
                "analysis_area": "Recommended length",
                "insight": best_length,
            },
            {
                "analysis_area": "Recommended line",
                "insight": best_line,
            },
            {
                "analysis_area": "Recommendation source",
                "insight": recommendation_source,
            },
            {
                "analysis_area": "Reason",
                "insight": best_reason,
            },
            {
                "analysis_area": "Shot to watch",
                "insight": risky_shot,
            },
            {
                "analysis_area": "Direction to watch",
                "insight": risky_direction,
            },
            {
                "analysis_area": "Direct balls",
                "insight": direct_balls,
            },
            {
                "analysis_area": "Proxy balls",
                "insight": proxy_balls,
            },
            {
                "analysis_area": "Confidence",
                "insight": confidence,
            },
        ]
    )

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "length_line_plan": final_plan_df,
        "direct_length_line_plan": direct_length_line_df,
        "proxy_bowler_style_plan": proxy_bowler_style_df,
        "proxy_batter_style_plan": proxy_batter_style_df,
        "shot_response": proxy_shots_df,
        "shot_direction": proxy_direction_df,
        "direct_summary": direct_summary_df,
        "batter_profile": batter_profile_df,
        "bowler_profile": bowler_profile_df,
        "sql_queries": {
            "length_line_plan": direct_length_line_sql,
            "direct_summary": direct_summary_sql,
            "batter_profile": batter_profile_sql,
            "bowler_profile": bowler_profile_sql,
            "proxy_bowler_style_plan": proxy_bowler_style_sql,
            "proxy_batter_style_plan": proxy_batter_style_sql,
            "shot_response": proxy_shots_sql,
            "shot_direction": proxy_direction_sql,
        },
    }
def analyze_team_report_squad_extras(team_condition, team_label="selected team"):
    """
    Extra squad-aware context for normal team reports.

    Adds:
    - 3 historical legends with reasons
    - 3 current players to watch with reasons
    - current squad role snapshot
    """

    squad_condition = convert_condition_column(team_condition, "cs.team_name")
    batting_team_condition = convert_condition_column(team_condition, "d.batting_team")
    bowling_team_condition = convert_condition_column(team_condition, "d.bowling_team")

    if squad_condition is None:
        squad_condition = "1 = 1"

    if batting_team_condition is None:
        batting_team_condition = "1 = 1"

    if bowling_team_condition is None:
        bowling_team_condition = "1 = 1"

    historical_legends_sql = f"""
WITH batting_legacy AS (
    SELECT
        d.striker AS player,
        COUNT(DISTINCT d.match_id) AS batting_matches,
        SUM(d.runs_off_bat) AS runs,
        SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END) AS balls_faced,
        ROUND(
            SUM(d.runs_off_bat) * 100.0 /
            NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
            2
        ) AS strike_rate
    FROM deliveries d
    WHERE {batting_team_condition}
    GROUP BY d.striker
),
bowling_legacy AS (
    SELECT
        d.bowler AS player,
        COUNT(DISTINCT d.match_id) AS bowling_matches,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS wickets,
        SUM(CASE
            WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1
            ELSE 0
        END) AS legal_balls,
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
        ROUND(
            SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) * 6.0 /
            NULLIF(SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END), 0),
            2
        ) AS economy
    FROM deliveries d
    WHERE {bowling_team_condition}
    GROUP BY d.bowler
),
combined AS (
    SELECT
        COALESCE(b.player, bo.player) AS player,
        COALESCE(b.batting_matches, 0) AS batting_matches,
        COALESCE(b.runs, 0) AS runs,
        COALESCE(b.balls_faced, 0) AS balls_faced,
        b.strike_rate,
        COALESCE(bo.bowling_matches, 0) AS bowling_matches,
        COALESCE(bo.wickets, 0) AS wickets,
        bo.economy
    FROM batting_legacy b
    FULL OUTER JOIN bowling_legacy bo
        ON b.player = bo.player
),
scored AS (
    SELECT
        player,
        batting_matches,
        runs,
        balls_faced,
        strike_rate,
        bowling_matches,
        wickets,
        economy,
        ROUND(
            runs / 45.0
            + wickets * 8.0
            + (batting_matches + bowling_matches) * 0.35
            + CASE
                WHEN player IN ('MS Dhoni', 'SK Raina', 'V Kohli', 'RG Sharma', 'AB de Villiers',
                                'KA Pollard', 'SP Narine', 'AD Russell', 'DJ Bravo',
                                'Rashid Khan', 'DA Warner', 'CH Gayle', 'JJ Bumrah',
                                'SL Malinga', 'RA Jadeja')
                THEN 35
                ELSE 0
              END,
            2
        ) AS legend_score,
        CASE
            WHEN player = 'MS Dhoni'
                THEN 'Franchise icon: also called Thala by fans, central to CSK through captaincy, finishing, wicketkeeping and long-term identity.'
            WHEN player = 'SK Raina'
                THEN 'Franchise batting legend: one of the most consistent IPL run scorers and a major CSK playoff-era performer.'
            WHEN player = 'DJ Bravo'
                THEN 'Franchise bowling legend: death-over specialist and wicket-taking all-rounder.'
            WHEN player = 'V Kohli'
                THEN 'Franchise icon: long-term batting leader and the face of the team across IPL eras.'
            WHEN player = 'AB de Villiers'
                THEN 'Franchise batting legend: elite strike-rate impact and match-winning middle-order role.'
            WHEN player = 'RG Sharma'
                THEN 'Franchise icon: major batting figure and title-winning leadership impact.'
            WHEN player = 'JJ Bumrah'
                THEN 'Franchise bowling legend: elite wicket-taking and death-over control.'
            WHEN player = 'KA Pollard'
                THEN 'Franchise legend: power-hitting finisher and useful all-round impact.'
            WHEN player = 'SP Narine'
                THEN 'Franchise legend: mystery spin, economy control and all-round value.'
            WHEN player = 'AD Russell'
                THEN 'Franchise legend: explosive finishing and wicket-taking all-round impact.'
            WHEN player = 'Rashid Khan'
                THEN 'Franchise-defining spinner: wicket threat, economy control and strong middle-over value.'
            WHEN player = 'DA Warner'
                THEN 'Franchise batting legend: high-volume run scorer and title-era impact.'
            WHEN player = 'CH Gayle'
                THEN 'IPL batting legend: extreme powerplay and boundary-hitting impact.'
            WHEN player = 'RA Jadeja'
                THEN 'Franchise all-round legend: spin, fielding, finishing and long-term tactical value.'
            WHEN runs >= 3000 AND wickets >= 50
                THEN CONCAT('All-round franchise impact: ', runs, ' runs and ', wickets, ' wickets for the team.')
            WHEN runs >= 2500
                THEN CONCAT('Batting legend by output: ', runs, ' runs for the franchise at a strike rate of ', COALESCE(CAST(strike_rate AS varchar(20)), 'N/A'), '.')
            WHEN wickets >= 75
                THEN CONCAT('Bowling legend by output: ', wickets, ' wickets for the franchise with economy ', COALESCE(CAST(economy AS varchar(20)), 'N/A'), '.')
            ELSE 'High historical franchise impact based on combined runs, wickets and matches.'
        END AS legend_reason
    FROM combined
)
SELECT TOP 3
    player,
    batting_matches,
    runs,
    strike_rate,
    bowling_matches,
    wickets,
    economy,
    legend_score,
    legend_reason
FROM scored
ORDER BY legend_score DESC, runs DESC, wickets DESC;
""".strip()

    current_players_to_watch_sql = f"""
WITH latest AS (
    SELECT MAX(YEAR(CAST(start_date AS date))) AS latest_season
    FROM matches
),
batting AS (
    SELECT
        cs.team_code,
        cs.team_name,
        cs.display_name,
        cs.cricsheet_name,
        cs.role,
        SUM(d.runs_off_bat) AS career_runs,
        SUM(CASE
            WHEN YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
            THEN d.runs_off_bat
            ELSE 0
        END) AS recent_runs,
        SUM(CASE
            WHEN d.wides IS NULL THEN 1
            ELSE 0
        END) AS career_balls,
        SUM(CASE
            WHEN YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
                 AND d.wides IS NULL
            THEN 1
            ELSE 0
        END) AS recent_balls
    FROM dbo.current_squads cs
    LEFT JOIN deliveries d
        ON d.striker = cs.cricsheet_name
    LEFT JOIN matches m
        ON d.match_id = m.match_id
    CROSS JOIN latest l
    WHERE cs.is_active = 1
      AND {squad_condition}
    GROUP BY
        cs.team_code,
        cs.team_name,
        cs.display_name,
        cs.cricsheet_name,
        cs.role
),
bowling AS (
    SELECT
        cs.cricsheet_name,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS career_wickets,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
                 AND YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
            THEN 1
        END) AS recent_wickets,
        SUM(CASE
            WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1
            ELSE 0
        END) AS legal_balls,
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded
    FROM dbo.current_squads cs
    LEFT JOIN deliveries d
        ON d.bowler = cs.cricsheet_name
    LEFT JOIN matches m
        ON d.match_id = m.match_id
    CROSS JOIN latest l
    WHERE cs.is_active = 1
      AND {squad_condition}
    GROUP BY cs.cricsheet_name
),
combined AS (
    SELECT
        b.team_code,
        b.team_name,
        b.display_name,
        b.cricsheet_name,
        b.role,
        COALESCE(b.career_runs, 0) AS career_runs,
        COALESCE(b.recent_runs, 0) AS recent_runs,
        ROUND(
            COALESCE(b.career_runs, 0) * 100.0 /
            NULLIF(COALESCE(b.career_balls, 0), 0),
            2
        ) AS career_strike_rate,
        ROUND(
            COALESCE(b.recent_runs, 0) * 100.0 /
            NULLIF(COALESCE(b.recent_balls, 0), 0),
            2
        ) AS recent_strike_rate,
        COALESCE(bo.career_wickets, 0) AS career_wickets,
        COALESCE(bo.recent_wickets, 0) AS recent_wickets,
        ROUND(
            COALESCE(bo.runs_conceded, 0) * 6.0 /
            NULLIF(COALESCE(bo.legal_balls, 0), 0),
            2
        ) AS career_economy
    FROM batting b
    LEFT JOIN bowling bo
        ON b.cricsheet_name = bo.cricsheet_name
),
scored AS (
    SELECT
        *,
        ROUND(
            recent_runs * 0.25
            + recent_wickets * 15.0
            + career_runs * 0.015
            + career_wickets * 2.5
            + CASE
                WHEN recent_strike_rate >= 150 AND recent_runs >= 100 THEN 15
                WHEN recent_strike_rate >= 130 AND recent_runs >= 100 THEN 8
                ELSE 0
              END
            + CASE
                WHEN career_economy <= 7.5 AND career_wickets >= 20 THEN 12
                WHEN career_economy <= 8.5 AND career_wickets >= 20 THEN 6
                ELSE 0
              END,
            2
        ) AS watch_score,
        CASE
            WHEN recent_runs = 0 AND recent_wickets = 0 AND career_runs = 0 AND career_wickets = 0
                THEN 'Current squad player with limited or no IPL historical data in the local database.'
            WHEN recent_runs >= 250 AND recent_wickets >= 8
                THEN CONCAT('All-round current impact: ', recent_runs, ' recent runs and ', recent_wickets, ' recent wickets.')
            WHEN recent_runs >= 250
                THEN CONCAT('Current batting watch: ', recent_runs, ' recent runs at a recent strike rate of ', COALESCE(CAST(recent_strike_rate AS varchar(20)), 'N/A'), '.')
            WHEN recent_wickets >= 8
                THEN CONCAT('Current bowling watch: ', recent_wickets, ' recent wickets with career economy ', COALESCE(CAST(career_economy AS varchar(20)), 'N/A'), '.')
            WHEN career_runs >= 1000
                THEN CONCAT('Experienced current batter: ', career_runs, ' career IPL runs in the local dataset.')
            WHEN career_wickets >= 40
                THEN CONCAT('Experienced current bowler: ', career_wickets, ' career IPL wickets in the local dataset.')
            ELSE 'Current squad player with some tactical relevance, but limited recent sample.'
        END AS watch_reason
    FROM combined
)
SELECT TOP 3
    team_code,
    team_name,
    display_name,
    cricsheet_name,
    role,
    career_runs,
    recent_runs,
    career_strike_rate,
    recent_strike_rate,
    career_wickets,
    recent_wickets,
    career_economy,
    watch_score,
    watch_reason
FROM scored
ORDER BY watch_score DESC, recent_runs DESC, recent_wickets DESC;
""".strip()

    squad_snapshot_sql = f"""
SELECT
    cs.team_code,
    cs.team_name,
    cs.role,
    COUNT(*) AS players
FROM dbo.current_squads cs
WHERE cs.is_active = 1
  AND {squad_condition}
GROUP BY
    cs.team_code,
    cs.team_name,
    cs.role
ORDER BY
    cs.team_code,
    cs.role;
""".strip()

    historical_legends_df = run_query(historical_legends_sql)
    current_players_to_watch_df = run_query(current_players_to_watch_sql)
    squad_snapshot_df = run_query(squad_snapshot_sql)

    legend_1 = safe_first_value(historical_legends_df, "player", "unknown legend")
    legend_reason_1 = safe_first_value(historical_legends_df, "legend_reason", "No reason available.")

    watch_1 = safe_first_value(current_players_to_watch_df, "display_name", "unknown current player")
    watch_reason_1 = safe_first_value(current_players_to_watch_df, "watch_reason", "No reason available.")

    paragraph = (
        f"For {team_label}, the historical legend list is led by {legend_1}. Reason: {legend_reason_1} "
        f"The current players-to-watch list is led by {watch_1}. Reason: {watch_reason_1}"
    )

    summary_df = pd.DataFrame(
        [
            {
                "analysis_area": "Top historical legend",
                "insight": legend_1,
            },
            {
                "analysis_area": "Legend reason",
                "insight": legend_reason_1,
            },
            {
                "analysis_area": "Top current player to watch",
                "insight": watch_1,
            },
            {
                "analysis_area": "Watch reason",
                "insight": watch_reason_1,
            },
        ]
    )

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "historical_legends": historical_legends_df,
        "current_players_to_watch": current_players_to_watch_df,
        "squad_snapshot": squad_snapshot_df,
        "sql_queries": {
            "historical_legends": historical_legends_sql,
            "current_players_to_watch": current_players_to_watch_sql,
            "squad_snapshot": squad_snapshot_sql,
        },
    }
def analyze_enhanced_team_profile(team_condition, team_label="selected team"):
    """
    Normal team profile + squad-aware extra context.
    Keeps the old team report safe, but adds:
    - 3 legends with reasons
    - 3 current players to watch with reasons
    - current squad snapshot
    """

    base_result = analyze_team_profile(
        team_condition=team_condition,
        team_label=team_label,
    )

    squad_context = analyze_team_report_squad_extras(
        team_condition=team_condition,
        team_label=team_label,
    )

    base_summary = base_result.get("summary")
    squad_summary = squad_context.get("summary")

    if base_summary is not None and squad_summary is not None:
        combined_summary = pd.concat(
            [base_summary, squad_summary],
            ignore_index=True,
        )
    elif base_summary is not None:
        combined_summary = base_summary
    else:
        combined_summary = squad_summary

    base_paragraph = base_result.get("paragraph", "")
    squad_paragraph = squad_context.get("paragraph", "")

    paragraph = f"{base_paragraph} {squad_paragraph}".strip()

    sql_queries = {}

    if isinstance(base_result.get("sql_queries"), dict):
        sql_queries.update(base_result["sql_queries"])
    elif base_result.get("sql_query") is not None:
        sql_queries["base_team_profile"] = base_result["sql_query"]

    sql_queries.update(squad_context["sql_queries"])

    return {
        "paragraph": paragraph,
        "summary": combined_summary,
        "base_team_profile": base_result,
        "team_report_squad_summary": squad_context["summary"],
        "historical_legends": squad_context["historical_legends"],
        "current_players_to_watch": squad_context["current_players_to_watch"],
        "squad_snapshot": squad_context["squad_snapshot"],
        "sql_queries": sql_queries,
    }
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

    Ranking logic:
    1. Dismissals matter most.
    2. Lower strike rate matters second.
    3. Larger sample size improves confidence.
    """

    best_matchups_sql = f"""
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
),
scored AS (
    SELECT
        batter,
        runs_scored,
        balls_faced,
        dismissals,
        ROUND(runs_scored * 100.0 / NULLIF(balls_faced, 0), 2) AS strike_rate,
        ROUND(runs_scored * 1.0 / NULLIF(dismissals, 0), 2) AS batting_average,
        ROUND(
            dismissals * 25.0
            +
            CASE
                WHEN balls_faced >= 36 THEN 10
                WHEN balls_faced >= 24 THEN 7
                WHEN balls_faced >= 12 THEN 4
                ELSE 0
            END
            +
            CASE
                WHEN ROUND(runs_scored * 100.0 / NULLIF(balls_faced, 0), 2) <= 90 THEN 10
                WHEN ROUND(runs_scored * 100.0 / NULLIF(balls_faced, 0), 2) <= 110 THEN 7
                WHEN ROUND(runs_scored * 100.0 / NULLIF(balls_faced, 0), 2) <= 130 THEN 4
                WHEN ROUND(runs_scored * 100.0 / NULLIF(balls_faced, 0), 2) <= 150 THEN 2
                ELSE 0
            END
            -
            CASE
                WHEN dismissals = 0
                     AND ROUND(runs_scored * 100.0 / NULLIF(balls_faced, 0), 2) >= 160
                THEN 10
                ELSE 0
            END,
            2
        ) AS matchup_score,
        CASE
            WHEN dismissals >= 3 THEN 'Strong wicket matchup'
            WHEN dismissals >= 2 THEN 'Good wicket matchup'
            WHEN dismissals = 1 AND ROUND(runs_scored * 100.0 / NULLIF(balls_faced, 0), 2) <= 120 THEN 'Useful control matchup'
            WHEN dismissals = 0 AND ROUND(runs_scored * 100.0 / NULLIF(balls_faced, 0), 2) <= 110 THEN 'Control matchup but no dismissal evidence'
            ELSE 'Limited matchup advantage'
        END AS matchup_reason
    FROM batter_vs_bowler
    WHERE balls_faced >= 10
)
SELECT TOP 10
    batter,
    runs_scored,
    balls_faced,
    dismissals,
    batting_average,
    strike_rate,
    matchup_score,
    matchup_reason
FROM scored
ORDER BY
    matchup_score DESC,
    dismissals DESC,
    strike_rate ASC,
    balls_faced DESC;
""".strip()

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

    best_matchups_df = run_query(best_matchups_sql)
    most_dismissed_df = run_query(most_dismissed_sql)
    most_runs_df = run_query(most_runs_sql)
    highest_average_df = run_query(highest_average_sql)
    highest_strike_rate_df = run_query(highest_strike_rate_sql)
    phase_df = run_query(phase_sql)

    best_matchup_batter = safe_first_value(best_matchups_df, "batter", "unknown")
    best_matchup_reason = safe_first_value(best_matchups_df, "matchup_reason", "unknown")
    top_success_batter = safe_first_value(most_dismissed_df, "batter", "unknown")
    top_runs_batter = safe_first_value(most_runs_df, "batter", "unknown")
    top_average_batter = safe_first_value(highest_average_df, "batter", "unknown")
    top_strike_rate_batter = safe_first_value(highest_strike_rate_df, "batter", "unknown")
    best_phase = safe_first_value(phase_df, "phase", "unknown")
    bowler_name = extract_player_name_from_condition(bowler_condition)

    paragraph = (
        f"{bowler_name}'s best matchup by the new weighting is {best_matchup_batter}, mainly because of: "
        f"{best_matchup_reason}. This model gives the most importance to dismissals, then uses strike rate and "
        f"sample size as supporting evidence. Historically, {top_success_batter} is the batter he has dismissed most "
        f"often. {top_runs_batter} has scored the most runs against him, while {top_average_batter} has the highest "
        f"average and {top_strike_rate_batter} has scored fastest among filtered batters. Phase-wise, his strongest "
        f"wicket-taking phase appears to be the {best_phase}."
    )

    summary_rows = [
        {
            "analysis_area": "Overall insight",
            "insight": paragraph,
        },
        {
            "analysis_area": "Best weighted matchup",
            "insight": f"{best_matchup_batter} is the best matchup after prioritising dismissals over strike rate.",
        },
        {
            "analysis_area": "Most dismissed batter",
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
        "best_matchups": best_matchups_df,
        "most_dismissed": most_dismissed_df,
        "most_runs": most_runs_df,
        "highest_average": highest_average_df,
        "highest_strike_rate": highest_strike_rate_df,
        "phases": phase_df,
        "sql_queries": {
            "best_matchups": best_matchups_sql,
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
    Current-squad definition of active:
    bowlers currently listed in dbo.current_squads.

    This is better than using latest two IPL seasons because squads are now loaded.
    """
    return f"""
{bowler_column} IN (
    SELECT DISTINCT cs.cricsheet_name
    FROM dbo.current_squads cs
    WHERE cs.is_active = 1
      AND (
          LOWER(cs.role) LIKE '%bowler%'
          OR LOWER(cs.role) LIKE '%all%'
          OR NULLIF(LTRIM(RTRIM(cs.bowling_style)), '') IS NOT NULL
      )
)
""".strip()
def analyze_team_title_chances():
    """
    Squad-aware IPL title prediction model.

    Uses:
    - current_squads table for current team strength
    - historical IPL data of current squad players
    - recent franchise form
    - batting strength
    - bowling strength
    - death-over strength
    - playoff/final experience
    - squad depth

    This is still an explainable model, not a guaranteed prediction.
    """

    current_team_key = canonical_team_sql("cs.team_name")
    batting_team_key = canonical_team_sql("d.batting_team")
    winner_team_key = canonical_team_sql("m.winner")
    match_team_key = canonical_team_sql("mt.team_name")
    playoff_team_key = canonical_team_sql("team")
    playoff_winner_key = canonical_team_sql("winner")

    title_sql = f"""
WITH latest AS (
    SELECT
        MAX(YEAR(CAST(start_date AS date))) AS latest_season
    FROM matches
),
current_teams AS (
    SELECT DISTINCT
        cs.team_code,
        cs.team_name,
        {current_team_key} AS team_key
    FROM current_squads cs
    WHERE cs.is_active = 1
),
match_teams AS (
    SELECT DISTINCT
        d.match_id,
        {batting_team_key} AS team_key,
        d.batting_team AS team_name
    FROM deliveries d
),
recent_form AS (
    SELECT
        ct.team_code,
        ct.team_name,
        ct.team_key,
        COUNT(DISTINCT CASE
            WHEN YEAR(CAST(m.start_date AS date)) >= l.latest_season - 1
            THEN m.match_id
        END) AS recent_matches,
        COUNT(DISTINCT CASE
            WHEN YEAR(CAST(m.start_date AS date)) >= l.latest_season - 1
                 AND {winner_team_key} = ct.team_key
            THEN m.match_id
        END) AS recent_wins
    FROM current_teams ct
    CROSS JOIN latest l
    LEFT JOIN match_teams mt
        ON mt.team_key = ct.team_key
    LEFT JOIN matches m
        ON mt.match_id = m.match_id
    GROUP BY
        ct.team_code,
        ct.team_name,
        ct.team_key
),
squad_batting AS (
    SELECT
        ct.team_code,
        ct.team_name,
        ct.team_key,
        COUNT(DISTINCT cs.cricsheet_name) AS squad_players,
        COUNT(DISTINCT CASE
            WHEN d.match_id IS NOT NULL THEN cs.cricsheet_name
        END) AS batting_players_with_history,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
            THEN d.runs_off_bat
            ELSE 0
        END) AS squad_career_runs,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
                 AND YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
            THEN d.runs_off_bat
            ELSE 0
        END) AS squad_recent_runs,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
                 AND d.wides IS NULL
            THEN 1
            ELSE 0
        END) AS squad_balls_faced,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
                 AND FLOOR(d.ball) BETWEEN 0 AND 5
            THEN d.runs_off_bat
            ELSE 0
        END) AS powerplay_runs,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
                 AND FLOOR(d.ball) BETWEEN 0 AND 5
                 AND d.wides IS NULL
            THEN 1
            ELSE 0
        END) AS powerplay_balls,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
                 AND FLOOR(d.ball) BETWEEN 15 AND 19
            THEN d.runs_off_bat
            ELSE 0
        END) AS death_runs,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
                 AND FLOOR(d.ball) BETWEEN 15 AND 19
                 AND d.wides IS NULL
            THEN 1
            ELSE 0
        END) AS death_balls
    FROM current_teams ct
    CROSS JOIN latest l
    JOIN current_squads cs
        ON cs.team_code = ct.team_code
        AND cs.is_active = 1
    LEFT JOIN deliveries d
        ON d.striker = cs.cricsheet_name
    LEFT JOIN matches m
        ON d.match_id = m.match_id
    GROUP BY
        ct.team_code,
        ct.team_name,
        ct.team_key
),
squad_bowling AS (
    SELECT
        ct.team_code,
        ct.team_name,
        ct.team_key,
        COUNT(DISTINCT CASE
            WHEN d.match_id IS NOT NULL THEN cs.cricsheet_name
        END) AS bowling_players_with_history,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
            THEN 1
        END) AS squad_career_wickets,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
                 AND YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
            THEN 1
        END) AS squad_recent_wickets,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
            THEN d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)
            ELSE 0
        END) AS squad_runs_conceded,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
                 AND d.wides IS NULL
                 AND d.noballs IS NULL
            THEN 1
            ELSE 0
        END) AS squad_legal_balls,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
                 AND FLOOR(d.ball) BETWEEN 15 AND 19
            THEN d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)
            ELSE 0
        END) AS death_runs_conceded,
        SUM(CASE
            WHEN d.match_id IS NOT NULL
                 AND FLOOR(d.ball) BETWEEN 15 AND 19
                 AND d.wides IS NULL
                 AND d.noballs IS NULL
            THEN 1
            ELSE 0
        END) AS death_legal_balls
    FROM current_teams ct
    CROSS JOIN latest l
    JOIN current_squads cs
        ON cs.team_code = ct.team_code
        AND cs.is_active = 1
        AND (
            LOWER(cs.role) LIKE '%bowler%'
            OR LOWER(cs.role) LIKE '%all%'
            OR NULLIF(LTRIM(RTRIM(cs.bowling_style)), '') IS NOT NULL
        )
    LEFT JOIN deliveries d
        ON d.bowler = cs.cricsheet_name
    LEFT JOIN matches m
        ON d.match_id = m.match_id
    GROUP BY
        ct.team_code,
        ct.team_name,
        ct.team_key
),
playoff_raw AS (
    SELECT
        match_id,
        season_year,
        team_1 AS team,
        winner,
        is_playoff,
        is_final
    FROM match_stages
    WHERE is_playoff = 1

    UNION ALL

    SELECT
        match_id,
        season_year,
        team_2 AS team,
        winner,
        is_playoff,
        is_final
    FROM match_stages
    WHERE is_playoff = 1
),
playoff_history AS (
    SELECT
        {playoff_team_key} AS team_key,
        COUNT(DISTINCT CASE
            WHEN is_playoff = 1 THEN season_year
        END) AS playoff_seasons,
        COUNT(CASE
            WHEN is_playoff = 1
                 AND {playoff_winner_key} = {playoff_team_key}
            THEN 1
        END) AS playoff_wins,
        COUNT(DISTINCT CASE
            WHEN is_final = 1 THEN season_year
        END) AS final_appearances,
        COUNT(CASE
            WHEN is_final = 1
                 AND {playoff_winner_key} = {playoff_team_key}
            THEN 1
        END) AS titles
    FROM playoff_raw
    GROUP BY {playoff_team_key}
),
base_metrics AS (
    SELECT
        ct.team_code,
        ct.team_name,
        ct.team_key,

        COALESCE(rf.recent_matches, 0) AS recent_matches,
        COALESCE(rf.recent_wins, 0) AS recent_wins,
        COALESCE(rf.recent_wins * 100.0 / NULLIF(rf.recent_matches, 0), 0) AS recent_win_pct,

        COALESCE(sb.squad_players, 0) AS squad_players,
        COALESCE(sb.batting_players_with_history, 0) AS batting_players_with_history,
        COALESCE(sb.squad_career_runs, 0) AS squad_career_runs,
        COALESCE(sb.squad_recent_runs, 0) AS squad_recent_runs,
        COALESCE(sb.squad_career_runs * 100.0 / NULLIF(sb.squad_balls_faced, 0), 0) AS squad_batting_sr,
        COALESCE(sb.powerplay_runs * 100.0 / NULLIF(sb.powerplay_balls, 0), 0) AS squad_powerplay_sr,
        COALESCE(sb.death_runs * 100.0 / NULLIF(sb.death_balls, 0), 0) AS squad_death_sr,

        COALESCE(sw.bowling_players_with_history, 0) AS bowling_players_with_history,
        COALESCE(sw.squad_career_wickets, 0) AS squad_career_wickets,
        COALESCE(sw.squad_recent_wickets, 0) AS squad_recent_wickets,
        COALESCE(sw.squad_runs_conceded * 6.0 / NULLIF(sw.squad_legal_balls, 0), 99.0) AS squad_economy,
        COALESCE(sw.death_runs_conceded * 6.0 / NULLIF(sw.death_legal_balls, 0), 99.0) AS squad_death_economy,

        COALESCE(ph.playoff_seasons, 0) AS playoff_seasons,
        COALESCE(ph.playoff_wins, 0) AS playoff_wins,
        COALESCE(ph.final_appearances, 0) AS final_appearances,
        COALESCE(ph.titles, 0) AS titles
    FROM current_teams ct
    LEFT JOIN recent_form rf
        ON ct.team_key = rf.team_key
    LEFT JOIN squad_batting sb
        ON ct.team_key = sb.team_key
    LEFT JOIN squad_bowling sw
        ON ct.team_key = sw.team_key
    LEFT JOIN playoff_history ph
        ON ct.team_key = ph.team_key
),
normalized AS (
    SELECT
        *,
        CASE
            WHEN MAX(recent_win_pct) OVER () = MIN(recent_win_pct) OVER () THEN 0.5
            ELSE (recent_win_pct - MIN(recent_win_pct) OVER ()) /
                 NULLIF(MAX(recent_win_pct) OVER () - MIN(recent_win_pct) OVER (), 0)
        END AS norm_recent_form,

        CASE
            WHEN MAX(squad_recent_runs) OVER () = MIN(squad_recent_runs) OVER () THEN 0.5
            ELSE (squad_recent_runs - MIN(squad_recent_runs) OVER ()) /
                 NULLIF(MAX(squad_recent_runs) OVER () - MIN(squad_recent_runs) OVER (), 0)
        END AS norm_recent_runs,

        CASE
            WHEN MAX(squad_batting_sr) OVER () = MIN(squad_batting_sr) OVER () THEN 0.5
            ELSE (squad_batting_sr - MIN(squad_batting_sr) OVER ()) /
                 NULLIF(MAX(squad_batting_sr) OVER () - MIN(squad_batting_sr) OVER (), 0)
        END AS norm_batting_sr,

        CASE
            WHEN MAX(squad_death_sr) OVER () = MIN(squad_death_sr) OVER () THEN 0.5
            ELSE (squad_death_sr - MIN(squad_death_sr) OVER ()) /
                 NULLIF(MAX(squad_death_sr) OVER () - MIN(squad_death_sr) OVER (), 0)
        END AS norm_death_batting,

        CASE
            WHEN MAX(squad_recent_wickets) OVER () = MIN(squad_recent_wickets) OVER () THEN 0.5
            ELSE (squad_recent_wickets - MIN(squad_recent_wickets) OVER ()) /
                 NULLIF(MAX(squad_recent_wickets) OVER () - MIN(squad_recent_wickets) OVER (), 0)
        END AS norm_recent_wickets,

        CASE
            WHEN MAX(squad_economy) OVER () = MIN(squad_economy) OVER () THEN 0.5
            ELSE (MAX(squad_economy) OVER () - squad_economy) /
                 NULLIF(MAX(squad_economy) OVER () - MIN(squad_economy) OVER (), 0)
        END AS norm_economy,

        CASE
            WHEN MAX(squad_death_economy) OVER () = MIN(squad_death_economy) OVER () THEN 0.5
            ELSE (MAX(squad_death_economy) OVER () - squad_death_economy) /
                 NULLIF(MAX(squad_death_economy) OVER () - MIN(squad_death_economy) OVER (), 0)
        END AS norm_death_bowling,

        CASE
            WHEN MAX(playoff_wins + titles * 2 + final_appearances) OVER () =
                 MIN(playoff_wins + titles * 2 + final_appearances) OVER () THEN 0.5
            ELSE ((playoff_wins + titles * 2 + final_appearances) -
                  MIN(playoff_wins + titles * 2 + final_appearances) OVER ()) /
                 NULLIF(
                    MAX(playoff_wins + titles * 2 + final_appearances) OVER () -
                    MIN(playoff_wins + titles * 2 + final_appearances) OVER (),
                    0
                 )
        END AS norm_playoff_experience,

        CASE
            WHEN MAX(batting_players_with_history + bowling_players_with_history) OVER () =
                 MIN(batting_players_with_history + bowling_players_with_history) OVER () THEN 0.5
            ELSE ((batting_players_with_history + bowling_players_with_history) -
                  MIN(batting_players_with_history + bowling_players_with_history) OVER ()) /
                 NULLIF(
                    MAX(batting_players_with_history + bowling_players_with_history) OVER () -
                    MIN(batting_players_with_history + bowling_players_with_history) OVER (),
                    0
                 )
        END AS norm_squad_depth
    FROM base_metrics
),
component_scores AS (
    SELECT
        *,
        (
            0.50 * norm_recent_runs +
            0.30 * norm_batting_sr +
            0.20 * norm_death_batting
        ) AS squad_batting_score,

        (
            0.45 * norm_recent_wickets +
            0.35 * norm_economy +
            0.20 * norm_death_bowling
        ) AS squad_bowling_score,

        (
            0.50 * norm_death_batting +
            0.50 * norm_death_bowling
        ) AS death_overs_score
    FROM normalized
),
final_scores AS (
    SELECT
        *,
        ROUND(
            100.0 * (
                0.25 * norm_recent_form +
                0.22 * squad_batting_score +
                0.22 * squad_bowling_score +
                0.12 * death_overs_score +
                0.11 * norm_playoff_experience +
                0.08 * norm_squad_depth
            ),
            2
        ) AS title_chance_score
    FROM component_scores
)
SELECT
    ROW_NUMBER() OVER (ORDER BY title_chance_score DESC) AS predicted_rank,
    team_code,
    team_name,
    title_chance_score,

    ROUND(norm_recent_form * 100, 2) AS recent_form_score,
    ROUND(squad_batting_score * 100, 2) AS squad_batting_score,
    ROUND(squad_bowling_score * 100, 2) AS squad_bowling_score,
    ROUND(death_overs_score * 100, 2) AS death_overs_score,
    ROUND(norm_playoff_experience * 100, 2) AS playoff_experience_score,
    ROUND(norm_squad_depth * 100, 2) AS squad_depth_score,

    recent_matches,
    recent_wins,
    ROUND(recent_win_pct, 2) AS recent_win_pct,

    squad_players,
    batting_players_with_history,
    bowling_players_with_history,

    squad_recent_runs,
    ROUND(squad_batting_sr, 2) AS squad_batting_sr,
    ROUND(squad_death_sr, 2) AS squad_death_sr,

    squad_recent_wickets,
    ROUND(squad_economy, 2) AS squad_economy,
    ROUND(squad_death_economy, 2) AS squad_death_economy,

    playoff_seasons,
    playoff_wins,
    final_appearances,
    titles
FROM final_scores
ORDER BY title_chance_score DESC;
""".strip()

    batting_leaders_sql = """
SELECT TOP 30
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role,
    SUM(d.runs_off_bat) AS career_runs,
    SUM(CASE
        WHEN d.wides IS NULL THEN 1 ELSE 0
    END) AS balls_faced,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate,
    SUM(CASE
        WHEN FLOOR(d.ball) BETWEEN 15 AND 19 THEN d.runs_off_bat
        ELSE 0
    END) AS death_runs
FROM current_squads cs
JOIN deliveries d
    ON d.striker = cs.cricsheet_name
WHERE cs.is_active = 1
GROUP BY
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role
ORDER BY career_runs DESC;
""".strip()

    bowling_leaders_sql = """
SELECT TOP 30
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role,
    cs.bowling_style,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS career_wickets,
    SUM(CASE
        WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1
        ELSE 0
    END) AS legal_balls,
    SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
    ROUND(
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) * 6.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy
FROM current_squads cs
JOIN deliveries d
    ON d.bowler = cs.cricsheet_name
WHERE cs.is_active = 1
GROUP BY
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role,
    cs.bowling_style
ORDER BY career_wickets DESC;
""".strip()

    scores_df = run_query(title_sql)
    batting_leaders_df = run_query(batting_leaders_sql)
    bowling_leaders_df = run_query(bowling_leaders_sql)

    if scores_df is None or scores_df.empty:
        paragraph = "I could not calculate squad-aware title chances because the required squad or match data was missing."
    else:
        top_team = scores_df.iloc[0]["team_name"]
        top_score = scores_df.iloc[0]["title_chance_score"]
        top_recent_form = scores_df.iloc[0]["recent_form_score"]
        top_batting = scores_df.iloc[0]["squad_batting_score"]
        top_bowling = scores_df.iloc[0]["squad_bowling_score"]
        top_death = scores_df.iloc[0]["death_overs_score"]

        paragraph = (
            f"The squad-aware model currently predicts {top_team} as the strongest title candidate "
            f"with a score of {format_metric(top_score)}. This combines recent franchise form, "
            f"current squad batting strength, current squad bowling strength, death-over strength, "
            f"playoff experience and squad depth. {top_team}'s component scores are: recent form "
            f"{format_metric(top_recent_form)}, squad batting {format_metric(top_batting)}, "
            f"squad bowling {format_metric(top_bowling)}, and death overs {format_metric(top_death)}. "
            f"This is an explainable statistical prediction, not a guarantee, because injuries, auction changes, "
            f"team combinations and match conditions can still change the outcome."
        )

    return {
        "paragraph": paragraph,
        "summary": scores_df,
        "team_scores": scores_df,
        "current_squad_batting_leaders": batting_leaders_df,
        "current_squad_bowling_leaders": bowling_leaders_df,
        "sql_query": title_sql,
        "sql_queries": {
            "team_scores": title_sql,
            "current_squad_batting_leaders": batting_leaders_sql,
            "current_squad_bowling_leaders": bowling_leaders_sql,
        },
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

def get_tactical_confidence(direct_balls, proxy_balls=0, used_proxy=False, venue_condition=None):
    """
    Simple confidence label for tactical recommendations.
    Uses sample size and whether the answer is direct or proxy-based.
    """

    direct_balls = 0 if direct_balls is None else direct_balls
    proxy_balls = 0 if proxy_balls is None else proxy_balls

    if not used_proxy:
        if direct_balls >= 24:
            confidence = "High"
            reason = "Strong direct matchup sample."
        elif direct_balls >= 12:
            confidence = "Medium"
            reason = "Usable direct matchup sample."
        elif direct_balls >= 8:
            confidence = "Low-Medium"
            reason = "Small direct sample, but still usable."
        else:
            confidence = "Low"
            reason = "Direct sample is too small."
    else:
        if proxy_balls >= 40:
            confidence = "Medium"
            reason = "Direct sample is small, but proxy sample is strong."
        elif proxy_balls >= 20:
            confidence = "Low-Medium"
            reason = "Direct sample is small, but proxy sample is usable."
        else:
            confidence = "Low"
            reason = "Both direct and proxy samples are small."

    if venue_condition is not None and confidence == "High":
        confidence = "Medium"
        reason += " Venue filter makes the sample more specific."

    return confidence, reason

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

def analyze_bowler_vs_batter_decision(
    batter_condition,
    bowler_condition,
    phase_condition=None,
    phase_label="all overs",
    venue_condition=None,
):
    """
    Tactical decision engine:
    - Should bowler X bowl to batter Y?
    - Should batter Y face bowler X?

    Uses direct matchup first.
    If direct matchup in the requested phase/venue is too small,
    it falls back to proxy evidence using similar batting style.
    Example: Rashid vs Pooran in PP -> Rashid vs left-hand batters in PP.
    """

    batter_condition = batter_condition.replace("d.striker", "se.striker")
    batter_condition = batter_condition.replace("pd.batter", "se.striker")

    bowler_condition = bowler_condition.replace("d.bowler", "se.bowler")
    bowler_condition = bowler_condition.replace("pd.bowler", "se.bowler")

    if phase_condition is not None:
        phase_condition = phase_condition.replace("d.ball", "se.ball")

    direct_clauses = [batter_condition, bowler_condition]

    if phase_condition is not None:
        direct_clauses.append(phase_condition)

    if venue_condition is not None:
        direct_clauses.append(venue_condition)

    direct_where_sql = " AND ".join(direct_clauses)

    phase_clauses = [batter_condition, bowler_condition]

    if venue_condition is not None:
        phase_clauses.append(venue_condition)

    phase_where_sql = " AND ".join(phase_clauses)

    benchmark_clauses = [batter_condition]

    if phase_condition is not None:
        benchmark_clauses.append(phase_condition)

    if venue_condition is not None:
        benchmark_clauses.append(venue_condition)

    benchmark_where_sql = " AND ".join(benchmark_clauses)

    direct_sql = f"""
SELECT
    se.striker AS batter,
    se.bowler,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {direct_where_sql}
GROUP BY se.striker, se.bowler;
""".strip()

    benchmark_sql = f"""
SELECT
    se.striker AS batter,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS batter_context_strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {benchmark_where_sql}
GROUP BY se.striker;
""".strip()

    phase_breakdown_sql = f"""
SELECT
    CASE
        WHEN FLOOR(se.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(se.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(se.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END AS phase,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {phase_where_sql}
GROUP BY
    CASE
        WHEN FLOOR(se.ball) BETWEEN 0 AND 5 THEN 'Powerplay'
        WHEN FLOOR(se.ball) BETWEEN 6 AND 14 THEN 'Middle overs'
        WHEN FLOOR(se.ball) BETWEEN 15 AND 19 THEN 'Death overs'
        ELSE 'Other'
    END
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 3
ORDER BY strike_rate ASC, dismissals DESC, legal_balls DESC;
""".strip()

    length_line_sql = f"""
SELECT
    COALESCE(se.ball_length, 'Unknown') AS ball_length,
    COALESCE(se.ball_line, 'Unknown') AS ball_line,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {direct_where_sql}
  AND se.ball_length IS NOT NULL
  AND se.ball_line IS NOT NULL
GROUP BY COALESCE(se.ball_length, 'Unknown'), COALESCE(se.ball_line, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 2
ORDER BY strike_rate ASC, dismissals DESC, legal_balls DESC;
""".strip()

    shot_direction_sql = f"""
SELECT
    COALESCE(se.shot_direction, 'Unknown') AS shot_direction,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {direct_where_sql}
  AND se.shot_direction IS NOT NULL
GROUP BY COALESCE(se.shot_direction, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 2
ORDER BY strike_rate DESC, dismissals ASC, legal_balls DESC;
""".strip()

    shot_type_sql = f"""
SELECT
    COALESCE(se.shot_played, 'Unknown') AS shot_played,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {direct_where_sql}
  AND se.shot_played IS NOT NULL
GROUP BY COALESCE(se.shot_played, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 2
ORDER BY strike_rate DESC, dismissals ASC, legal_balls DESC;
""".strip()

    direct_df = run_query(direct_sql)
    benchmark_df = run_query(benchmark_sql)
    phase_df = run_query(phase_breakdown_sql)
    length_line_df = run_query(length_line_sql)
    shot_direction_df = run_query(shot_direction_sql)
    shot_type_df = run_query(shot_type_sql)

    similar_batter_matchup_df = pd.DataFrame()
    similar_batter_benchmark_df = pd.DataFrame()
    similar_batter_lengths_lines_df = pd.DataFrame()
    similar_batter_shot_directions_df = pd.DataFrame()

    similar_batter_matchup_sql = ""
    similar_batter_benchmark_sql = ""
    similar_batter_lengths_lines_sql = ""
    similar_batter_shot_directions_sql = ""

    similar_batter_style = "similar-style"

    style_check_df = run_query("""
SELECT
    CASE
        WHEN COL_LENGTH('dbo.shot_events', 'batting_style_striker') IS NULL THEN 0
        ELSE 1
    END AS has_batting_style;
""".strip())

    has_batting_style = False

    if style_check_df is not None and not style_check_df.empty:
        has_batting_style = int(style_check_df.iloc[0]["has_batting_style"]) == 1

    if has_batting_style:
        batter_style_sql = f"""
SELECT TOP 1
    se.batting_style_striker,
    COUNT(*) AS balls
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {batter_condition}
  AND se.batting_style_striker IS NOT NULL
GROUP BY se.batting_style_striker
ORDER BY balls DESC;
""".strip()

        batter_style_df = run_query(batter_style_sql)

        if batter_style_df is not None and not batter_style_df.empty:
            similar_batter_style = str(batter_style_df.iloc[0]["batting_style_striker"])
            similar_batter_style_safe = similar_batter_style.replace("'", "''")

            proxy_clauses = [
                bowler_condition,
                f"se.batting_style_striker = '{similar_batter_style_safe}'",
            ]

            proxy_benchmark_clauses = [
                f"se.batting_style_striker = '{similar_batter_style_safe}'",
            ]

            if phase_condition is not None:
                proxy_clauses.append(phase_condition)
                proxy_benchmark_clauses.append(phase_condition)

            if venue_condition is not None:
                proxy_clauses.append(venue_condition)
                proxy_benchmark_clauses.append(venue_condition)

            proxy_where_sql = " AND ".join(proxy_clauses)
            proxy_benchmark_where_sql = " AND ".join(proxy_benchmark_clauses)

            similar_batter_matchup_sql = f"""
SELECT
    '{similar_batter_style_safe}' AS proxy_batter_type,
    se.bowler,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {proxy_where_sql}
GROUP BY se.bowler
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 10
ORDER BY strike_rate ASC, dismissals DESC, legal_balls DESC;
""".strip()

            similar_batter_benchmark_sql = f"""
SELECT
    '{similar_batter_style_safe}' AS proxy_batter_type,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS proxy_group_strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {proxy_benchmark_where_sql};
""".strip()

            similar_batter_lengths_lines_sql = f"""
SELECT
    COALESCE(se.ball_length, 'Unknown') AS ball_length,
    COALESCE(se.ball_line, 'Unknown') AS ball_line,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {proxy_where_sql}
  AND se.ball_length IS NOT NULL
  AND se.ball_line IS NOT NULL
GROUP BY COALESCE(se.ball_length, 'Unknown'), COALESCE(se.ball_line, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 3
ORDER BY strike_rate ASC, dismissals DESC, legal_balls DESC;
""".strip()

            similar_batter_shot_directions_sql = f"""
SELECT
    COALESCE(se.shot_direction, 'Unknown') AS shot_direction,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {proxy_where_sql}
  AND se.shot_direction IS NOT NULL
GROUP BY COALESCE(se.shot_direction, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 3
ORDER BY strike_rate DESC, dismissals ASC, legal_balls DESC;
""".strip()

            similar_batter_matchup_df = run_query(similar_batter_matchup_sql)
            similar_batter_benchmark_df = run_query(similar_batter_benchmark_sql)
            similar_batter_lengths_lines_df = run_query(similar_batter_lengths_lines_sql)
            similar_batter_shot_directions_df = run_query(similar_batter_shot_directions_sql)

    batter_name = extract_player_name_from_condition(batter_condition) or safe_first_value(
        direct_df,
        "batter",
        "the batter",
    )

    bowler_name = extract_player_name_from_condition(bowler_condition) or safe_first_value(
        direct_df,
        "bowler",
        "the bowler",
    )

    direct_balls = safe_first_value(direct_df, "legal_balls", 0)
    direct_runs = safe_first_value(direct_df, "runs", 0)
    direct_dismissals = safe_first_value(direct_df, "dismissals", 0)
    direct_sr = safe_first_value(direct_df, "strike_rate", None)
    benchmark_sr = safe_first_value(benchmark_df, "batter_context_strike_rate", None)

    proxy_balls = safe_first_value(similar_batter_matchup_df, "legal_balls", 0)
    proxy_runs = safe_first_value(similar_batter_matchup_df, "runs", 0)
    proxy_dismissals = safe_first_value(similar_batter_matchup_df, "dismissals", 0)
    proxy_sr = safe_first_value(similar_batter_matchup_df, "strike_rate", None)
    proxy_benchmark_sr = safe_first_value(
        similar_batter_benchmark_df,
        "proxy_group_strike_rate",
        None,
    )

    best_phase = safe_first_value(phase_df, "phase", "unknown phase")

    if length_line_df is not None and not length_line_df.empty:
        best_length = safe_first_value(length_line_df, "ball_length", "unknown length")
        best_line = safe_first_value(length_line_df, "ball_line", "unknown line")
        bowling_plan_source = "direct matchup data"
    elif similar_batter_lengths_lines_df is not None and not similar_batter_lengths_lines_df.empty:
        best_length = safe_first_value(similar_batter_lengths_lines_df, "ball_length", "unknown length")
        best_line = safe_first_value(similar_batter_lengths_lines_df, "ball_line", "unknown line")
        bowling_plan_source = f"proxy data against {similar_batter_style} batters"
    else:
        best_length = "unknown length"
        best_line = "unknown line"
        bowling_plan_source = "insufficient length/line data"

    if shot_direction_df is not None and not shot_direction_df.empty:
        best_direction = safe_first_value(shot_direction_df, "shot_direction", "unknown area")
        scoring_area_source = "direct matchup data"
    elif similar_batter_shot_directions_df is not None and not similar_batter_shot_directions_df.empty:
        best_direction = safe_first_value(similar_batter_shot_directions_df, "shot_direction", "unknown area")
        scoring_area_source = f"proxy data against {similar_batter_style} batters"
    else:
        best_direction = "unknown area"
        scoring_area_source = "insufficient shot-direction data"

    best_shot = safe_first_value(shot_type_df, "shot_played", "unknown shot")

    used_proxy = False

    if direct_sr is None or direct_balls < 8:
        if proxy_sr is not None and proxy_balls >= 10:
            used_proxy = True

            if proxy_benchmark_sr is not None and proxy_sr <= proxy_benchmark_sr * 0.90:
                decision = "Yes, but proxy-based"
                decision_reason = (
                    f"There is not enough direct {bowler_name} vs {batter_name} data in this context, "
                    f"so the model uses {bowler_name} vs {similar_batter_style} batters as a proxy. "
                    f"That proxy record is restrictive compared with the normal scoring rate of that batter type."
                )
            elif proxy_benchmark_sr is not None and proxy_sr >= proxy_benchmark_sr * 1.10:
                decision = "Avoid if possible"
                decision_reason = (
                    f"There is not enough direct {bowler_name} vs {batter_name} data in this context. "
                    f"Using {similar_batter_style} batters as a proxy, this matchup looks risky."
                )
            else:
                decision = "Use with caution"
                decision_reason = (
                    f"There is not enough direct {bowler_name} vs {batter_name} data in this context. "
                    f"The proxy sample against {similar_batter_style} batters is usable, but not decisive."
                )
        else:
            decision = "Insufficient data"
            decision_reason = (
                "There is not enough direct matchup data, and the proxy sample is also too small "
                "for a confident recommendation."
            )

    elif benchmark_sr is not None and direct_sr <= benchmark_sr * 0.85:
        decision = "Yes"
        decision_reason = (
            f"{bowler_name} has restricted {batter_name} well compared with the batter's usual scoring rate "
            "in this context."
        )

    elif benchmark_sr is not None and direct_sr >= benchmark_sr * 1.15:
        decision = "Avoid if possible"
        decision_reason = (
            f"{batter_name} scores faster than usual against {bowler_name} in this context."
        )

    elif direct_dismissals >= 1 and direct_sr < 140:
        decision = "Yes"
        decision_reason = (
            "The strike rate is controlled and the bowler has taken the batter's wicket before."
        )

    else:
        decision = "Neutral / situational"
        decision_reason = (
            "The matchup is not clearly one-sided, so phase, venue, and match situation should decide."
        )
    confidence, confidence_reason = get_tactical_confidence(
        direct_balls=direct_balls,
        proxy_balls=proxy_balls,
        used_proxy=used_proxy,
        venue_condition=venue_condition,
    )
    phase_note = ""

    if phase_label != "all overs" and best_phase != "unknown phase":
        clean_requested_phase = phase_label.replace("_", " ").lower()

        if clean_requested_phase not in best_phase.lower():
            phase_note = (
                f" Historically, {best_phase} looks like the better phase for this matchup. "
                f"If using the bowler in {phase_label}, use the recommended length/line rather than treating it as the ideal phase."
            )
        else:
            phase_note = " The requested phase also looks suitable historically for this matchup."

    if used_proxy:
        evidence_sentence = (
            f"Direct record in the requested context is too small: {bowler_name} to {batter_name} is "
            f"{direct_runs} runs from {direct_balls} legal balls. "
            f"As a proxy, {bowler_name} vs {similar_batter_style} batters in this context is "
            f"{proxy_runs} runs from {proxy_balls} legal balls, {proxy_dismissals} dismissals, "
            f"strike rate {format_metric(proxy_sr)}."
        )
    else:
        evidence_sentence = (
            f"Direct record: {bowler_name} to {batter_name} is {direct_runs} runs from {direct_balls} legal balls, "
            f"{direct_dismissals} dismissals, strike rate {format_metric(direct_sr)}."
        )

    paragraph = (
        f"Decision: {decision}. Confidence: {confidence}. {decision_reason} "
        f"{evidence_sentence} "
        f"The best historical phase for this direct matchup is {best_phase}. "
        f"If this bowler is used here, the data suggests bowling {best_length} length and {best_line} line "
        f"based on {bowling_plan_source}. "
        f"From the batter's point of view, the best scoring area is {best_direction} "
        f"based on {scoring_area_source}, especially using {best_shot}."
        f"{phase_note}"
    )

    summary_df = pd.DataFrame(
    [
        {
            "analysis_area": "Decision",
            "insight": decision,
        },
        {
            "analysis_area": "Confidence",
            "insight": f"{confidence}: {confidence_reason}",
        },
        {
            "analysis_area": "Reason",
            "insight": decision_reason,
        },
        {
            "analysis_area": "Evidence type",
            "insight": "Proxy-based" if used_proxy else "Direct matchup",
        },
        {
            "analysis_area": "Direct matchup",
            "insight": (
                f"{direct_runs} runs from {direct_balls} legal balls, "
                f"{direct_dismissals} dismissals, SR {format_metric(direct_sr)}."
            ),
        },
        {
            "analysis_area": "Proxy sample",
            "insight": (
                f"{bowler_name} vs {similar_batter_style} batters: "
                f"{proxy_runs} runs from {proxy_balls} legal balls, "
                f"{proxy_dismissals} dismissals, SR {format_metric(proxy_sr)}."
                if used_proxy
                else "Not needed."
            ),
        },
        {
            "analysis_area": "Best phase",
            "insight": best_phase,
        },
        {
            "analysis_area": "Bowling plan",
            "insight": f"Bowl {best_length} length and {best_line} line.",
        },
        {
            "analysis_area": "Batter scoring area",
            "insight": f"Aim for {best_direction}, especially with {best_shot}.",
        },
    ]
)

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "direct_matchup": direct_df,
        "batter_benchmark": benchmark_df,
        "phase_breakdown": phase_df,
        "recommended_lengths_lines": length_line_df,
        "shot_directions": shot_direction_df,
        "shot_types": shot_type_df,
        "similar_batter_matchup": similar_batter_matchup_df,
        "similar_batter_benchmark": similar_batter_benchmark_df,
        "similar_batter_lengths_lines": similar_batter_lengths_lines_df,
        "similar_batter_shot_directions": similar_batter_shot_directions_df,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "sql_queries": {
            "direct_matchup": direct_sql,
            "batter_benchmark": benchmark_sql,
            "phase_breakdown": phase_breakdown_sql,
            "recommended_lengths_lines": length_line_sql,
            "shot_directions": shot_direction_sql,
            "shot_types": shot_type_sql,
            "similar_batter_matchup": similar_batter_matchup_sql,
            "similar_batter_benchmark": similar_batter_benchmark_sql,
            "similar_batter_lengths_lines": similar_batter_lengths_lines_sql,
            "similar_batter_shot_directions": similar_batter_shot_directions_sql,
        },
    }

def analyze_team_bowler_recommendation(
    batter_condition,
    team_condition,
    phase_condition=None,
    phase_label="all overs",
    venue_condition=None,
):
    """
    Squad-aware team bowler recommendation.

    Example:
    Which GT bowler should bowl to Pooran?

    Uses current_squads table to get CURRENT squad bowlers,
    then uses their historical IPL data from shot_events.
    This prevents outdated answers like Noor Ahmad for GT if Noor is now in CSK.
    """

    batter_condition = batter_condition.replace("d.striker", "se.striker")
    batter_condition = batter_condition.replace("pd.batter", "se.striker")

    squad_team_condition = team_condition
    squad_team_condition = squad_team_condition.replace("se.bowling_team", "cs.team_name")
    squad_team_condition = squad_team_condition.replace("d.bowling_team", "cs.team_name")
    squad_team_condition = squad_team_condition.replace("d.batting_team", "cs.team_name")

    if phase_condition is not None:
        phase_condition = phase_condition.replace("d.ball", "se.ball")

    squad_bowler_filter = """
cs.is_active = 1
AND (
    LOWER(cs.role) LIKE '%bowler%'
    OR LOWER(cs.role) LIKE '%all%'
    OR NULLIF(LTRIM(RTRIM(cs.bowling_style)), '') IS NOT NULL
)
""".strip()

    direct_clauses = [
        batter_condition,
        squad_team_condition,
        squad_bowler_filter,
    ]

    if phase_condition is not None:
        direct_clauses.append(phase_condition)

    if venue_condition is not None:
        direct_clauses.append(venue_condition)

    direct_where_sql = " AND ".join(direct_clauses)

    direct_options_sql = f"""
SELECT
    cs.team_code,
    cs.team_name AS current_team,
    cs.display_name,
    cs.cricsheet_name AS bowler,
    cs.role,
    COALESCE(cs.bowling_style, se.bowling_style_bowler, 'Unknown') AS bowling_style,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.current_squads cs
JOIN dbo.shot_events se
    ON se.bowler = cs.cricsheet_name
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {direct_where_sql}
GROUP BY
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role,
    COALESCE(cs.bowling_style, se.bowling_style_bowler, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 3
ORDER BY strike_rate ASC, dismissals DESC, legal_balls DESC;
""".strip()

    direct_options_df = run_query(direct_options_sql)

    style_check_df = run_query("""
SELECT
    CASE
        WHEN COL_LENGTH('dbo.shot_events', 'batting_style_striker') IS NULL THEN 0
        ELSE 1
    END AS has_batting_style;
""".strip())

    has_batting_style = False

    if style_check_df is not None and not style_check_df.empty:
        has_batting_style = int(style_check_df.iloc[0]["has_batting_style"]) == 1

    proxy_options_df = pd.DataFrame()
    proxy_options_sql = ""
    similar_batter_style = "similar-style"

    if has_batting_style:
        batter_style_sql = f"""
SELECT TOP 1
    se.batting_style_striker,
    COUNT(*) AS balls
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {batter_condition}
  AND se.batting_style_striker IS NOT NULL
GROUP BY se.batting_style_striker
ORDER BY balls DESC;
""".strip()

        batter_style_df = run_query(batter_style_sql)

        if batter_style_df is not None and not batter_style_df.empty:
            similar_batter_style = str(batter_style_df.iloc[0]["batting_style_striker"])
            similar_batter_style_safe = similar_batter_style.replace("'", "''")

            proxy_clauses = [
                squad_team_condition,
                squad_bowler_filter,
                f"se.batting_style_striker = '{similar_batter_style_safe}'",
            ]

            if phase_condition is not None:
                proxy_clauses.append(phase_condition)

            if venue_condition is not None:
                proxy_clauses.append(venue_condition)

            proxy_where_sql = " AND ".join(proxy_clauses)

            proxy_options_sql = f"""
SELECT
    '{similar_batter_style_safe}' AS proxy_batter_type,
    cs.team_code,
    cs.team_name AS current_team,
    cs.display_name,
    cs.cricsheet_name AS bowler,
    cs.role,
    COALESCE(cs.bowling_style, se.bowling_style_bowler, 'Unknown') AS bowling_style,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.current_squads cs
JOIN dbo.shot_events se
    ON se.bowler = cs.cricsheet_name
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {proxy_where_sql}
GROUP BY
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role,
    COALESCE(cs.bowling_style, se.bowling_style_bowler, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 10
ORDER BY strike_rate ASC, dismissals DESC, legal_balls DESC;
""".strip()

            proxy_options_df = run_query(proxy_options_sql)

    used_proxy = False

    if direct_options_df is not None and not direct_options_df.empty:
        best_df = direct_options_df
        evidence_type = "Direct matchup using current squad"
    elif proxy_options_df is not None and not proxy_options_df.empty:
        best_df = proxy_options_df
        evidence_type = f"Proxy using current squad vs {similar_batter_style} batters"
        used_proxy = True
    else:
        best_df = pd.DataFrame()
        evidence_type = "Insufficient current-squad data"

    best_bowler = safe_first_value(best_df, "bowler", "unknown bowler")
    best_display_name = safe_first_value(best_df, "display_name", best_bowler)
    best_style = safe_first_value(best_df, "bowling_style", "unknown style")
    best_team = safe_first_value(best_df, "current_team", "unknown team")
    best_balls = safe_first_value(best_df, "legal_balls", 0)
    best_runs = safe_first_value(best_df, "runs", 0)
    best_dismissals = safe_first_value(best_df, "dismissals", 0)
    best_sr = safe_first_value(best_df, "strike_rate", None)

    confidence, confidence_reason = get_tactical_confidence(
        direct_balls=best_balls if not used_proxy else 0,
        proxy_balls=best_balls if used_proxy else 0,
        used_proxy=used_proxy,
        venue_condition=venue_condition,
    )

    length_line_df = pd.DataFrame()
    length_line_sql = ""

    if best_bowler != "unknown bowler":
        best_bowler_safe = str(best_bowler).replace("'", "''")

        plan_clauses = [
            f"se.bowler = '{best_bowler_safe}'",
        ]

        if used_proxy and similar_batter_style != "similar-style":
            similar_batter_style_safe = similar_batter_style.replace("'", "''")
            plan_clauses.append(f"se.batting_style_striker = '{similar_batter_style_safe}'")
        else:
            plan_clauses.append(batter_condition)

        if phase_condition is not None:
            plan_clauses.append(phase_condition)

        if venue_condition is not None:
            plan_clauses.append(venue_condition)

        plan_where_sql = " AND ".join(plan_clauses)

        length_line_sql = f"""
SELECT
    COALESCE(se.ball_length, 'Unknown') AS ball_length,
    COALESCE(se.ball_line, 'Unknown') AS ball_line,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {plan_where_sql}
  AND se.ball_length IS NOT NULL
  AND se.ball_line IS NOT NULL
GROUP BY COALESCE(se.ball_length, 'Unknown'), COALESCE(se.ball_line, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 3
ORDER BY strike_rate ASC, dismissals DESC, legal_balls DESC;
""".strip()

        length_line_df = run_query(length_line_sql)

    best_length = safe_first_value(length_line_df, "ball_length", "unknown length")
    best_line = safe_first_value(length_line_df, "ball_line", "unknown line")

    paragraph = (
        f"Recommendation: use {best_display_name} from the current {best_team} squad. "
        f"Confidence: {confidence}. Evidence type: {evidence_type}. "
        f"Record used: {best_runs} runs from {best_balls} legal balls, "
        f"{best_dismissals} dismissals, strike rate {format_metric(best_sr)}. "
        f"Bowling style: {best_style}. Suggested plan: bowl {best_length} length and {best_line} line."
    )

    summary_df = pd.DataFrame(
        [
            {
                "analysis_area": "Recommended bowler",
                "insight": best_display_name,
            },
            {
                "analysis_area": "Current team",
                "insight": best_team,
            },
            {
                "analysis_area": "Confidence",
                "insight": f"{confidence}: {confidence_reason}",
            },
            {
                "analysis_area": "Evidence type",
                "insight": evidence_type,
            },
            {
                "analysis_area": "Record used",
                "insight": f"{best_runs} runs from {best_balls} legal balls, {best_dismissals} dismissals, SR {format_metric(best_sr)}.",
            },
            {
                "analysis_area": "Bowling plan",
                "insight": f"Bowl {best_length} length and {best_line} line.",
            },
        ]
    )

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "direct_options": direct_options_df,
        "proxy_options": proxy_options_df,
        "recommended_lengths_lines": length_line_df,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "sql_queries": {
            "direct_options": direct_options_sql,
            "proxy_options": proxy_options_sql,
            "recommended_lengths_lines": length_line_sql,
        },
    }

def analyze_batter_plan_against_bowler(
    batter_condition,
    bowler_condition,
    phase_condition=None,
    phase_label="all overs",
    venue_condition=None,
):
    """
    Batting plan:
    How should a batter play a bowler?

    Returns scoring areas, useful shots, risky shots, and length/line advice.
    """

    batter_condition = batter_condition.replace("d.striker", "se.striker")
    batter_condition = batter_condition.replace("pd.batter", "se.striker")

    bowler_condition = bowler_condition.replace("d.bowler", "se.bowler")
    bowler_condition = bowler_condition.replace("pd.bowler", "se.bowler")

    if phase_condition is not None:
        phase_condition = phase_condition.replace("d.ball", "se.ball")

    where_clauses = [batter_condition, bowler_condition]

    if phase_condition is not None:
        where_clauses.append(phase_condition)

    if venue_condition is not None:
        where_clauses.append(venue_condition)

    where_sql = " AND ".join(where_clauses)

    direct_summary_sql = f"""
SELECT
    se.striker AS batter,
    se.bowler,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {where_sql}
GROUP BY se.striker, se.bowler;
""".strip()

    scoring_areas_sql = f"""
SELECT
    COALESCE(se.shot_direction, 'Unknown') AS shot_direction,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {where_sql}
  AND se.shot_direction IS NOT NULL
GROUP BY COALESCE(se.shot_direction, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 2
ORDER BY strike_rate DESC, runs DESC;
""".strip()

    scoring_shots_sql = f"""
SELECT
    COALESCE(se.shot_played, 'Unknown') AS shot_played,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {where_sql}
  AND se.shot_played IS NOT NULL
GROUP BY COALESCE(se.shot_played, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 2
ORDER BY strike_rate DESC, runs DESC;
""".strip()

    risky_shots_sql = f"""
SELECT
    COALESCE(se.shot_played, 'Unknown') AS shot_played,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {where_sql}
  AND se.shot_played IS NOT NULL
GROUP BY COALESCE(se.shot_played, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 2
ORDER BY dismissals DESC, strike_rate ASC;
""".strip()

    length_line_attack_sql = f"""
SELECT
    COALESCE(se.ball_length, 'Unknown') AS ball_length,
    COALESCE(se.ball_line, 'Unknown') AS ball_line,
    COUNT(*) AS total_balls,
    SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    SUM(se.runs_off_bat) AS runs,
    COUNT(CASE
        WHEN se.player_dismissed = se.striker
             AND se.wicket_type IS NOT NULL
             AND se.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS dismissals,
    ROUND(
        SUM(se.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM dbo.shot_events se
JOIN dbo.matches m
    ON se.match_id = m.match_id
WHERE {where_sql}
  AND se.ball_length IS NOT NULL
  AND se.ball_line IS NOT NULL
GROUP BY COALESCE(se.ball_length, 'Unknown'), COALESCE(se.ball_line, 'Unknown')
HAVING SUM(CASE WHEN se.wides IS NULL THEN 1 ELSE 0 END) >= 2
ORDER BY strike_rate DESC, runs DESC;
""".strip()

    direct_summary_df = run_query(direct_summary_sql)
    scoring_areas_df = run_query(scoring_areas_sql)
    scoring_shots_df = run_query(scoring_shots_sql)
    risky_shots_df = run_query(risky_shots_sql)
    length_line_attack_df = run_query(length_line_attack_sql)

    batter_name = extract_player_name_from_condition(batter_condition) or safe_first_value(
        direct_summary_df,
        "batter",
        "the batter",
    )

    bowler_name = extract_player_name_from_condition(bowler_condition) or safe_first_value(
        direct_summary_df,
        "bowler",
        "the bowler",
    )

    balls = safe_first_value(direct_summary_df, "legal_balls", 0)
    runs = safe_first_value(direct_summary_df, "runs", 0)
    dismissals = safe_first_value(direct_summary_df, "dismissals", 0)
    strike_rate = safe_first_value(direct_summary_df, "strike_rate", None)

    confidence, confidence_reason = get_tactical_confidence(
        direct_balls=balls,
        proxy_balls=0,
        used_proxy=False,
        venue_condition=venue_condition,
    )

    best_area = safe_first_value(scoring_areas_df, "shot_direction", "unknown area")
    best_shot = safe_first_value(scoring_shots_df, "shot_played", "unknown shot")
    risky_shot = safe_first_value(risky_shots_df, "shot_played", "unknown shot")
    attack_length = safe_first_value(length_line_attack_df, "ball_length", "unknown length")
    attack_line = safe_first_value(length_line_attack_df, "ball_line", "unknown line")

    paragraph = (
        f"Batting plan for {batter_name} against {bowler_name}: "
        f"Confidence: {confidence}. Direct record is {runs} runs from {balls} legal balls, "
        f"{dismissals} dismissals, strike rate {format_metric(strike_rate)}. "
        f"The best scoring area is {best_area}, and the most productive shot is {best_shot}. "
        f"The batter should be careful with {risky_shot}, which has carried the most risk in this matchup. "
        f"The best length/line to attack appears to be {attack_length} length and {attack_line} line."
    )

    summary_df = pd.DataFrame(
        [
            {
                "analysis_area": "Confidence",
                "insight": f"{confidence}: {confidence_reason}",
            },
            {
                "analysis_area": "Direct record",
                "insight": f"{runs} runs from {balls} legal balls, {dismissals} dismissals, SR {format_metric(strike_rate)}.",
            },
            {
                "analysis_area": "Best scoring area",
                "insight": best_area,
            },
            {
                "analysis_area": "Best shot",
                "insight": best_shot,
            },
            {
                "analysis_area": "Risky shot",
                "insight": risky_shot,
            },
            {
                "analysis_area": "Length/line to attack",
                "insight": f"{attack_length} length and {attack_line} line.",
            },
        ]
    )

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "direct_summary": direct_summary_df,
        "scoring_areas": scoring_areas_df,
        "scoring_shots": scoring_shots_df,
        "risky_shots": risky_shots_df,
        "length_line_attack": length_line_attack_df,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "sql_queries": {
            "direct_summary": direct_summary_sql,
            "scoring_areas": scoring_areas_sql,
            "scoring_shots": scoring_shots_sql,
            "risky_shots": risky_shots_sql,
            "length_line_attack": length_line_attack_sql,
        },
    }
def analyze_current_squad_report(team_condition, team_label="selected team"):
    """
    Current squad report for one IPL team.

    Shows:
    - full current squad
    - current squad batting leaders
    - current squad bowling leaders
    - players to watch from current squad
    - historical batting legends for the franchise
    - historical bowling legends for the franchise
    """

    squad_condition = convert_condition_column(team_condition, "cs.team_name")
    batting_team_condition = convert_condition_column(team_condition, "d.batting_team")
    bowling_team_condition = convert_condition_column(team_condition, "d.bowling_team")

    if squad_condition is None:
        squad_condition = "1 = 1"

    if batting_team_condition is None:
        batting_team_condition = "1 = 1"

    if bowling_team_condition is None:
        bowling_team_condition = "1 = 1"

    current_squad_sql = f"""
SELECT
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role,
    cs.batting_style,
    cs.bowling_style,
    cs.bowling_arm,
    cs.is_overseas,
    cs.is_active
FROM dbo.current_squads cs
WHERE cs.is_active = 1
  AND {squad_condition}
ORDER BY
    CASE
        WHEN LOWER(cs.role) LIKE '%batter%' THEN 1
        WHEN LOWER(cs.role) LIKE '%all%' THEN 2
        WHEN LOWER(cs.role) LIKE '%bowler%' THEN 3
        ELSE 4
    END,
    cs.display_name;
""".strip()

    squad_batting_sql = f"""
WITH latest AS (
    SELECT MAX(YEAR(CAST(start_date AS date))) AS latest_season
    FROM matches
)
SELECT TOP 15
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role,
    SUM(d.runs_off_bat) AS career_runs,
    SUM(CASE
        WHEN YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
        THEN d.runs_off_bat
        ELSE 0
    END) AS recent_runs,
    SUM(CASE
        WHEN d.wides IS NULL THEN 1
        ELSE 0
    END) AS balls_faced,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate,
    SUM(CASE
        WHEN FLOOR(d.ball) BETWEEN 15 AND 19
        THEN d.runs_off_bat
        ELSE 0
    END) AS death_runs
FROM dbo.current_squads cs
JOIN deliveries d
    ON d.striker = cs.cricsheet_name
JOIN matches m
    ON d.match_id = m.match_id
CROSS JOIN latest l
WHERE cs.is_active = 1
  AND {squad_condition}
GROUP BY
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role
ORDER BY recent_runs DESC, career_runs DESC;
""".strip()

    squad_bowling_sql = f"""
WITH latest AS (
    SELECT MAX(YEAR(CAST(start_date AS date))) AS latest_season
    FROM matches
)
SELECT TOP 15
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role,
    cs.bowling_style,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS career_wickets,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
             AND YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
        THEN 1
    END) AS recent_wickets,
    SUM(CASE
        WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1
        ELSE 0
    END) AS legal_balls,
    SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
    ROUND(
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) * 6.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy
FROM dbo.current_squads cs
JOIN deliveries d
    ON d.bowler = cs.cricsheet_name
JOIN matches m
    ON d.match_id = m.match_id
CROSS JOIN latest l
WHERE cs.is_active = 1
  AND {squad_condition}
  AND (
      LOWER(cs.role) LIKE '%bowler%'
      OR LOWER(cs.role) LIKE '%all%'
      OR NULLIF(LTRIM(RTRIM(cs.bowling_style)), '') IS NOT NULL
  )
GROUP BY
    cs.team_code,
    cs.team_name,
    cs.display_name,
    cs.cricsheet_name,
    cs.role,
    cs.bowling_style
ORDER BY recent_wickets DESC, career_wickets DESC, economy ASC;
""".strip()

    players_to_watch_sql = f"""
WITH latest AS (
    SELECT MAX(YEAR(CAST(start_date AS date))) AS latest_season
    FROM matches
),
batting AS (
    SELECT
        cs.team_code,
        cs.team_name,
        cs.display_name,
        cs.cricsheet_name,
        cs.role,
        SUM(CASE
            WHEN YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
            THEN d.runs_off_bat
            ELSE 0
        END) AS recent_runs,
        SUM(CASE
            WHEN YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
                 AND d.wides IS NULL
            THEN 1
            ELSE 0
        END) AS recent_balls
    FROM dbo.current_squads cs
    LEFT JOIN deliveries d
        ON d.striker = cs.cricsheet_name
    LEFT JOIN matches m
        ON d.match_id = m.match_id
    CROSS JOIN latest l
    WHERE cs.is_active = 1
      AND {squad_condition}
    GROUP BY
        cs.team_code,
        cs.team_name,
        cs.display_name,
        cs.cricsheet_name,
        cs.role
),
bowling AS (
    SELECT
        cs.cricsheet_name,
        COUNT(CASE
            WHEN d.wicket_type IS NOT NULL
                 AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
                 AND YEAR(CAST(m.start_date AS date)) >= l.latest_season - 2
            THEN 1
        END) AS recent_wickets
    FROM dbo.current_squads cs
    LEFT JOIN deliveries d
        ON d.bowler = cs.cricsheet_name
    LEFT JOIN matches m
        ON d.match_id = m.match_id
    CROSS JOIN latest l
    WHERE cs.is_active = 1
      AND {squad_condition}
    GROUP BY cs.cricsheet_name
),
combined AS (
    SELECT
        b.team_code,
        b.team_name,
        b.display_name,
        b.cricsheet_name,
        b.role,
        COALESCE(b.recent_runs, 0) AS recent_runs,
        COALESCE(b.recent_balls, 0) AS recent_balls,
        COALESCE(bo.recent_wickets, 0) AS recent_wickets,
        ROUND(
            COALESCE(b.recent_runs, 0) * 100.0 /
            NULLIF(COALESCE(b.recent_balls, 0), 0),
            2
        ) AS recent_strike_rate,
        (
            COALESCE(b.recent_runs, 0) * 0.20 +
            COALESCE(bo.recent_wickets, 0) * 12.0 +
            CASE
                WHEN COALESCE(b.recent_balls, 0) >= 50
                THEN COALESCE(b.recent_runs, 0) * 100.0 / NULLIF(COALESCE(b.recent_balls, 0), 0) * 0.10
                ELSE 0
            END
        ) AS watch_score
    FROM batting b
    LEFT JOIN bowling bo
        ON b.cricsheet_name = bo.cricsheet_name
)
SELECT TOP 10
    team_code,
    team_name,
    display_name,
    cricsheet_name,
    role,
    recent_runs,
    recent_strike_rate,
    recent_wickets,
    ROUND(watch_score, 2) AS watch_score,
    CASE
        WHEN recent_runs = 0 AND recent_wickets = 0 THEN 'Current squad player with limited/no IPL historical data'
        WHEN recent_runs >= recent_wickets * 20 THEN 'Batting form / scoring impact'
        WHEN recent_wickets > recent_runs / 20 THEN 'Bowling wicket impact'
        ELSE 'All-round impact'
    END AS watch_reason
FROM combined
ORDER BY watch_score DESC, display_name;
""".strip()

    historical_batting_legends_sql = f"""
SELECT TOP 10
    d.striker AS player,
    COUNT(DISTINCT d.match_id) AS matches,
    SUM(d.runs_off_bat) AS runs,
    SUM(CASE
        WHEN d.wides IS NULL THEN 1
        ELSE 0
    END) AS balls_faced,
    ROUND(
        SUM(d.runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries d
WHERE {batting_team_condition}
GROUP BY d.striker
ORDER BY runs DESC;
""".strip()

    historical_bowling_legends_sql = f"""
SELECT TOP 10
    d.bowler AS player,
    COUNT(DISTINCT d.match_id) AS matches,
    COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) AS wickets,
    SUM(CASE
        WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1
        ELSE 0
    END) AS legal_balls,
    SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) AS runs_conceded,
    ROUND(
        SUM(d.runs_off_bat + COALESCE(d.wides, 0) + COALESCE(d.noballs, 0)) * 6.0 /
        NULLIF(SUM(CASE WHEN d.wides IS NULL AND d.noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy
FROM deliveries d
WHERE {bowling_team_condition}
GROUP BY d.bowler
HAVING COUNT(CASE
        WHEN d.wicket_type IS NOT NULL
             AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
        THEN 1
    END) > 0
ORDER BY wickets DESC, economy ASC;
""".strip()

    current_squad_df = run_query(current_squad_sql)
    squad_batting_df = run_query(squad_batting_sql)
    squad_bowling_df = run_query(squad_bowling_sql)
    players_to_watch_df = run_query(players_to_watch_sql)
    historical_batting_legends_df = run_query(historical_batting_legends_sql)
    historical_bowling_legends_df = run_query(historical_bowling_legends_sql)

    top_batter = safe_first_value(squad_batting_df, "display_name", "unknown batter")
    top_bowler = safe_first_value(squad_bowling_df, "display_name", "unknown bowler")
    player_to_watch = safe_first_value(players_to_watch_df, "display_name", "unknown player")
    batting_legend = safe_first_value(historical_batting_legends_df, "player", "unknown batting legend")
    bowling_legend = safe_first_value(historical_bowling_legends_df, "player", "unknown bowling legend")

    paragraph = (
        f"{team_label}'s current squad report highlights {top_batter} as the leading current-squad batting profile "
        f"based on historical IPL output, while {top_bowler} leads the current-squad bowling profile. "
        f"The player to watch from the current squad is {player_to_watch}. Historically, the franchise batting legend "
        f"is {batting_legend}, while the bowling legend is {bowling_legend}. "
        f"Newer squad players may appear in the squad list even if they have limited or no historical IPL data yet."
    )

    summary_df = pd.DataFrame(
        [
            {
                "analysis_area": "Current batting leader",
                "insight": top_batter,
            },
            {
                "analysis_area": "Current bowling leader",
                "insight": top_bowler,
            },
            {
                "analysis_area": "Current player to watch",
                "insight": player_to_watch,
            },
            {
                "analysis_area": "Historical batting legend",
                "insight": batting_legend,
            },
            {
                "analysis_area": "Historical bowling legend",
                "insight": bowling_legend,
            },
        ]
    )

    return {
        "paragraph": paragraph,
        "summary": summary_df,
        "current_squad": current_squad_df,
        "current_squad_batting": squad_batting_df,
        "current_squad_bowling": squad_bowling_df,
        "players_to_watch": players_to_watch_df,
        "historical_batting_legends": historical_batting_legends_df,
        "historical_bowling_legends": historical_bowling_legends_df,
        "sql_queries": {
            "current_squad": current_squad_sql,
            "current_squad_batting": squad_batting_sql,
            "current_squad_bowling": squad_bowling_sql,
            "players_to_watch": players_to_watch_sql,
            "historical_batting_legends": historical_batting_legends_sql,
            "historical_bowling_legends": historical_bowling_legends_sql,
        },
    }

def convert_condition_column(condition, new_column_name):
    """
    Converts a SQL condition from one table alias/column to another.
    Useful when reusing team filters across current_squads, deliveries, etc.
    """

    if condition is None:
        return None

    replacements = [
        "cs.team_name",
        "d.batting_team",
        "d.bowling_team",
        "m.winner",
        "se.bowling_team",
        "se.batting_team",
    ]

    converted = condition

    for old_column in replacements:
        converted = converted.replace(old_column, new_column_name)

    return converted

def analyze_strongest_current_squads():
    """
    Ranks current IPL squads using the squad-related components from the title model.
    """

    title_result = analyze_team_title_chances()
    team_scores = title_result["team_scores"]

    if team_scores is None or team_scores.empty:
        return {
            "paragraph": "I could not calculate current squad strength because the squad score table was empty.",
            "summary": team_scores,
            "team_scores": team_scores,
            "sql_queries": title_result.get("sql_queries", {}),
        }

    squad_scores = team_scores.copy()

    squad_scores["current_squad_strength_score"] = (
        squad_scores["squad_batting_score"] * 0.35 +
        squad_scores["squad_bowling_score"] * 0.35 +
        squad_scores["death_overs_score"] * 0.15 +
        squad_scores["squad_depth_score"] * 0.15
    )

    squad_scores = squad_scores.sort_values(
        by="current_squad_strength_score",
        ascending=False,
    ).reset_index(drop=True)

    squad_scores.insert(0, "squad_rank", range(1, len(squad_scores) + 1))

    top_team = squad_scores.iloc[0]["team_name"]
    top_score = squad_scores.iloc[0]["current_squad_strength_score"]

    paragraph = (
        f"The strongest current squad by this model is {top_team}, with a squad strength score of "
        f"{format_metric(top_score)}. This ranking focuses on current squad batting strength, bowling strength, "
        f"death-over strength and squad depth. It does not include future injuries or tactical selection changes."
    )

    return {
        "paragraph": paragraph,
        "summary": squad_scores,
        "team_scores": squad_scores,
        "sql_queries": title_result.get("sql_queries", {}),
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