import re

import pandas as pd
import streamlit as st

from app.llm_agent import answer_question_with_fallback


st.set_page_config(
    page_title="Cricket SQL Agent",
    layout="wide",
)


st.markdown(
    '''
    <style>
    .small-note {
        color: #d7dae3;
        font-size: 0.95rem;
        line-height: 1.45;
        margin-top: 0.35rem;
    }
    .card-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 0.45rem;
    }
    .card-main {
        font-size: 1.02rem;
        line-height: 1.45;
        margin-bottom: 0.55rem;
    }
    </style>
    ''',
    unsafe_allow_html=True,
)


HIDDEN_COLUMNS = {
    "watch_score",
    "rank_score",
    "priority_score",
    "is_priority_player",
    "recent_weighted_score",
    "career_weighted_score",
    "score",
    "match_id",
    "sql_query",
    "team_name",
    "cricsheet_name",
    "full_name",
    "full_name_striker",
    "full_name_bowler",
    "first_innings_wickets",
    "second_innings_wickets",
    "matchup_score",
    "legal_balls",   
    "legal_balls",
    "analysis_area",
    "insight",
    }

LONG_TEXT_COLUMNS = {
    "reason",
    "why",
    "insight",
    "summary",
    "trophy_summary",
    "result_summary",
    "plan",
    "toss_plan",
    "reason",
    "Reason",
    "battle note",
    "battle_note",
}

LABEL_ONLY_COLUMNS = {
    "analysis_area",
    "section",
    "watch_type",
}

SKIP_EXTRA_TABLES = {
    "team_report_squad_summary",
}


TEAM_SHORT_NAMES = [
    ("royal challengers bangalore/bengaluru", "RCB"),
    ("royal challengers bengaluru", "RCB"),
    ("royal challengers bangalore", "RCB"),
    ("rcb", "RCB"),
    ("gujarat titans", "GT"),
    ("gt", "GT"),
    ("mumbai indians", "MI"),
    ("mi", "MI"),
    ("kolkata knight riders", "KKR"),
    ("kkr", "KKR"),
    ("chennai super kings", "CSK"),
    ("csk", "CSK"),
    ("sunrisers hyderabad", "SRH"),
    ("srh", "SRH"),
    ("rajasthan royals", "RR"),
    ("rr", "RR"),
    ("punjab kings", "PBKS"),
    ("pbks", "PBKS"),
    ("delhi capitals", "Delhi Capitals"),
    ("dc", "Delhi Capitals"),
    ("lucknow super giants", "LSG"),
    ("lsg", "LSG"),
]


def should_show_table(value):
    if value is None:
        return False

    if isinstance(value, pd.DataFrame):
        return not value.empty

    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0

    return True

def pretty_table_title(title):
    title_key = str(title).lower().strip()

    title_map = {
        "career": "Career summary",
        "season_trend": "Season-by-season trend",
        "phase_performance": "Phase performance",
        "opponent_performance": "Opponent record",
        "venue_performance": "Venue record",
        "playoff_performance": "Playoff record",
        "dismissal_types": "Dismissal types",
        "bowler_success": "Bowlers he scores well against",
        "bowler_dismissals": "Bowlers who dismiss him most",
        "quiet_bowlers": "Bowlers who keep him quiet",
        "preferred_bowler_types": "Preferred bowling types",
        "difficult_bowler_types": "Difficult bowling types",
        "active_quiet_bowlers": "Active/recent restrictive bowlers",
        "batter_matchups": "Best batter matchups",
        "bowler_matchups": "Bowler matchups",
    }

    return title_map.get(title_key, str(title).replace("_", " ").title())


def pretty_column_name(column_name):
    return str(column_name).replace("_", " ").title()


def clean_user_text(text):
    text = str(text)
    text = re.sub(r"(\d+\.\d)0{3,}", r"\1", text)
    text = re.sub(r"(\d+)\.0{3,}", r"\1", text)

    text = re.sub(r"(\d+)\.0\+", r"\1+", text)
    text = re.sub(r"(\d+)\.0 or below", r"\1 or below", text)
    text = text.replace("top-three band 120+", "top three score 120+")
    text = text.replace("top-order dependency check", "top-order pattern")
    text = text.replace("data-led tactical suggestions", "data-backed tactical suggestions")

    return text


def split_into_sentences(text):
    text = clean_user_text(text).strip()

    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def team_short_label(team_name):
    text = str(team_name).lower()

    for alias, short_name in TEAM_SHORT_NAMES:
        if alias in text:
            return short_name

    return str(team_name)


def extract_team_short_labels(question):
    question_lower = str(question).lower()
    found = []

    for alias, short_name in TEAM_SHORT_NAMES:
        pattern = r"\b" + re.escape(alias) + r"\b"

        if re.search(pattern, question_lower) and short_name not in found:
            found.append(short_name)

    if len(found) >= 2:
        return found[0], found[1]

    return "Team A", "Team B"


def rewrite_match_plan_sentence(sentence):
    sentence = clean_user_text(sentence)

    batting_match = re.match(
        r"If batting first, (.*?) should aim for around (\d+)\+ because (.*?)'s failure rate when chasing that threshold is ([\d.]+)%.",
        sentence,
    )
    if batting_match:
        team, target, opponent, pct = batting_match.groups()
        return f"Batting first: aim for {target}+ because {team_short_label(opponent)} have failed to chase that kind of target {pct}% of the time."

    bowling_match = re.match(
        r"If bowling first, (.*?) should try to restrict (.*?) to about (\d+) or below;.*loss rate.*is ([\d.]+)%.",
        sentence,
    )
    if bowling_match:
        team, opponent, score, pct = bowling_match.groups()
        return f"Bowling first: keep {team_short_label(opponent)} to {score} or below because they lose {pct}% of those games."

    top_order_match = re.match(
        r"The top-order pattern says that when (.*?)'s top three are in the 120\+ run band, their win rate is ([\d.]+)%, so early wickets against players like (.*?) are important.",
        sentence,
    )
    if top_order_match:
        opponent, pct, player = top_order_match.groups()
        return f"Early wickets: if {team_short_label(opponent)}'s top three score 120+, they win {pct}% of those games. Target {player} early."

    bowling_matchup = re.match(
        r"One potential bowling matchup is (.*?) vs (.*?) in the (.*?).",
        sentence,
    )
    if bowling_matchup:
        bowler, batter, phase = bowling_matchup.groups()
        return f"Bowling matchup: use {bowler} against {batter} in the {phase}."

    batting_matchup = re.match(
        r"One batting matchup to target is (.*?) vs (.*?) in the (.*?).",
        sentence,
    )
    if batting_matchup:
        batter, bowler, phase = batting_matchup.groups()
        return f"Batting matchup: {batter} can target {bowler} in the {phase}."

    return sentence


def render_answer_paragraph(paragraph):
    paragraph = clean_user_text(paragraph)

    match_title = re.match(r"Match plan for (.*?) to beat (.*?):", paragraph)

    if match_title:
        team_a, team_b = match_title.groups()
        st.subheader("Match plan")
        st.caption(f"{team_short_label(team_a)} vs {team_short_label(team_b)}")

        body = paragraph[match_title.end():].strip()
        sentences = split_into_sentences(body)

        for sentence in sentences:
            rewritten = rewrite_match_plan_sentence(sentence)

            if "not guarantees" in rewritten.lower():
                st.caption(rewritten)
            else:
                st.markdown(f"- {rewritten}")

        return

    st.subheader("Answer")

    sentences = split_into_sentences(paragraph)

    if not sentences:
        st.write(paragraph)
        return

    for sentence in sentences:
        st.markdown(f"- {sentence}")


def clean_dataframe_for_display(df):
    clean_df = df.copy()

    columns_to_drop = [
        col for col in clean_df.columns
        if str(col).lower() in HIDDEN_COLUMNS
    ]

    if columns_to_drop:
        clean_df = clean_df.drop(columns=columns_to_drop)

    numeric_columns = clean_df.select_dtypes(include=["float", "float64"]).columns
    clean_df[numeric_columns] = clean_df[numeric_columns].round(2)

    return clean_df


def rename_head_to_head_columns(df):
    question = st.session_state.get("current_question", "")
    team_a, team_b = extract_team_short_labels(question)

    rename_map = {
        "team_a_wins": f"{team_a} Wins",
        "team_b_wins": f"{team_b} Wins",
        "team_a_win_pct": f"{team_a} Win %",
        "team_b_win_pct": f"{team_b} Win %",
        "Team A Wins": f"{team_a} Wins",
        "Team B Wins": f"{team_b} Wins",
        "Team A Win Pct": f"{team_a} Win %",
        "Team B Win Pct": f"{team_b} Win %",
    }

    return df.rename(columns=rename_map)

def format_recent_h2h_table(df):
    clean_df = df.copy()

    for col in [
        "team_a",
        "team_b",
        "winner",
        "first_innings_team",
        "second_innings_team",
    ]:
        if col in clean_df.columns:
            clean_df[col] = clean_df[col].apply(team_short_label)

    preferred_order = [
        "start_date",
        "winner",
        "result",
        "venue",
        "team_a",
        "team_b",
        "first_innings_team",
        "first_innings_score",
        "second_innings_team",
        "second_innings_score",
    ]

    existing_order = [col for col in preferred_order if col in clean_df.columns]
    remaining_cols = [col for col in clean_df.columns if col not in existing_order]

    clean_df = clean_df[existing_order + remaining_cols]

    rename_map = {
        "start_date": "Date",
        "winner": "Winner",
        "result": "Result",
        "venue": "Venue",
        "team_a": "Team A",
        "team_b": "Team B",
        "first_innings_team": "1st Innings Team",
        "first_innings_score": "1st Innings Score",
        "second_innings_team": "2nd Innings Team",
        "second_innings_score": "2nd Innings Score",
    }

    return clean_df.rename(columns=rename_map)

def format_bowler_matchups_table(df):
    clean_df = df.copy()

    preferred_order = [
        "bowler",
        "batter",
        "verdict",
        "innings",
        "balls",
        "runs",
        "dismissals",
        "batter_sr",
        "battle_note",
    ]

    existing_order = [col for col in preferred_order if col in clean_df.columns]
    remaining_cols = [col for col in clean_df.columns if col not in existing_order]

    clean_df = clean_df[existing_order + remaining_cols]

    rename_map = {
        "bowler": "Bowler",
        "batter": "Batter",
        "verdict": "Verdict",
        "innings": "Innings",
        "balls": "Balls",
        "runs": "Runs",
        "dismissals": "Dismissals",
        "batter_sr": "Batter SR",
        "battle_note": "Battle Note",
    }

    return clean_df.rename(columns=rename_map)

def format_player_profile_table(df, title):
    clean_df = df.copy()
    title_key = str(title).lower().strip()

    preferred_orders = {
        "career": [
            "batter", "bowler", "matches", "innings", "total_runs", "highest_score",
            "balls_faced", "dismissals", "batting_average", "strike_rate",
            "fours", "sixes", "fifties", "hundreds", "overs", "runs_conceded",
            "wickets", "economy_rate", "bowling_average", "bowling_strike_rate",
            "dot_ball_pct",
        ],
        "season_trend": [
            "season_year", "matches", "innings", "runs", "highest_score",
            "balls_faced", "dismissals", "batting_average", "strike_rate",
            "overs", "runs_conceded", "wickets", "economy_rate",
        ],
        "phase_performance": [
            "phase", "runs", "balls_faced", "dismissals", "strike_rate",
            "overs", "runs_conceded", "wickets", "economy_rate",
        ],
        "opponent_performance": [
            "opponent", "runs", "balls_faced", "dismissals", "batting_average",
            "strike_rate", "overs", "runs_conceded", "wickets", "economy_rate",
        ],
        "venue_performance": [
            "venue", "runs", "balls_faced", "dismissals", "strike_rate",
            "overs", "runs_conceded", "wickets", "economy_rate",
        ],
        "batter_matchups": [
            "batter", "balls", "runs", "dismissals", "batter_strike_rate", "verdict",
        ],
    }

    if title_key in preferred_orders:
        order = [col for col in preferred_orders[title_key] if col in clean_df.columns]
        remaining = [col for col in clean_df.columns if col not in order]
        clean_df = clean_df[order + remaining]

    rename_map = {
        "batter": "Batter",
        "bowler": "Bowler",
        "matches": "Matches",
        "innings": "Innings",
        "total_runs": "Runs",
        "highest_score": "Highest Score",
        "balls_faced": "Balls",
        "dismissals": "Dismissals",
        "batting_average": "Average",
        "strike_rate": "Strike Rate",
        "fours": "4s",
        "sixes": "6s",
        "fifties": "50s",
        "hundreds": "100s",
        "season_year": "Season",
        "phase": "Phase",
        "opponent": "Opponent",
        "venue": "Venue",
        "overs": "Overs",
        "runs_conceded": "Runs Conceded",
        "wickets": "Wickets",
        "economy_rate": "Economy",
        "bowling_average": "Bowling Average",
        "bowling_strike_rate": "Bowling Strike Rate",
        "dot_ball_pct": "Dot Ball %",
        "batter_strike_rate": "Batter SR",
        "verdict": "Verdict",
        "wicket_type": "Dismissal Type",
        "bowling_style": "Bowling Style",
    }

    clean_df = clean_df.rename(columns={col: rename_map.get(col, col) for col in clean_df.columns})

    return clean_df

def render_action_plan(df):
    clean_df = clean_dataframe_for_display(df)

    for _, row in clean_df.iterrows():
        phase = clean_user_text(row.get("phase", "Action"))
        plan = clean_user_text(row.get("plan", ""))
        why = clean_user_text(row.get("why", ""))
        key_players = clean_user_text(row.get("key_players", ""))

        with st.container(border=True):
            st.markdown(f"<div class='card-title'>{phase}</div>", unsafe_allow_html=True)

            if pd.notna(plan) and str(plan).strip():
                st.markdown(f"<div class='card-main'>{plan}</div>", unsafe_allow_html=True)

            if pd.notna(why) and str(why).strip():
                st.markdown(f"<div class='small-note'><b>Why:</b> {why}</div>", unsafe_allow_html=True)

            if pd.notna(key_players) and str(key_players).strip():
                st.markdown(f"<div class='small-note'><b>Key players:</b> {key_players}</div>", unsafe_allow_html=True)


def render_long_text_details(original_df, long_text_columns):
    st.markdown("#### Details")

    for row_index, row in original_df.iterrows():
        label_parts = []

        for possible_label in [
            "display_name",
            "player",
            "Bowler",
            "Batter",
            "Verdict",
            "team_a_bowler",
            "team_a_batter",
            "phase",
            "section",
            "analysis_area",
            "team",
            "watch_type",
        ]:
            if possible_label in original_df.columns:
                value = row.get(possible_label, "")
                if pd.notna(value) and str(value).strip():
                    label_parts.append(clean_user_text(value))

        label = " - ".join(label_parts)

        if not label:
            label = f"Row {row_index + 1}"

        with st.container(border=True):
            st.markdown(f"<div class='card-title'>{label}</div>", unsafe_allow_html=True)

            for text_col in long_text_columns:
                text_value = row.get(text_col, "")

                if pd.notna(text_value) and str(text_value).strip():
                    st.markdown(
                        f"<div class='card-main'>{clean_user_text(text_value)}</div>",
                        unsafe_allow_html=True,
                    )


def display_result(response, table_value=None):
    def clean_text_safe(value):
        if value is None:
            return ""
        try:
            return clean_user_text(value)
        except Exception:
            return str(value)

    def is_dataframe(value):
        return hasattr(value, "copy") and hasattr(value, "columns")

    def is_empty(value):
        if value is None:
            return True
        if is_dataframe(value) and value.empty:
            return True
        return False

    def title_safe(title):
        try:
            return pretty_table_title(title)
        except Exception:
            return str(title).replace("_", " ").title()

    def drop_hidden_columns(df):
        clean_df = df.copy()

        hidden_columns = set(globals().get("HIDDEN_COLUMNS", set()))
        hidden_columns_lower = {str(col).lower() for col in hidden_columns}

        keep_cols = [
            col for col in clean_df.columns
            if str(col).lower() not in hidden_columns_lower
        ]

        if keep_cols:
            return clean_df[keep_cols]

        return clean_df

    def apply_formatters(df, title):
        clean_df = df.copy()
        title_key = str(title).lower().strip()

        if title_key == "recent head to head results":
            try:
                return format_recent_h2h_table(clean_df)
            except Exception:
                return clean_df

        if title_key == "bowler matchups":
            try:
                return format_bowler_matchups_table(clean_df)
            except Exception:
                return clean_df

        player_profile_tables = {
            "career",
            "season_trend",
            "phase_performance",
            "opponent_performance",
            "venue_performance",
            "playoff_performance",
            "dismissal_types",
            "bowler_success",
            "bowler_dismissals",
            "quiet_bowlers",
            "preferred_bowler_types",
            "difficult_bowler_types",
            "active_quiet_bowlers",
            "batter_matchups",
        }

        if title_key in player_profile_tables:
            try:
                return format_player_profile_table(clean_df, title)
            except Exception:
                return clean_df

        return clean_df

    def is_summary_table(df):
        if not is_dataframe(df):
            return False

        lower_cols = {str(col).lower() for col in df.columns}

        if lower_cols == {"analysis_area", "insight"}:
            return True

        if lower_cols == {"section", "summary"}:
            return True

        return False

    def get_long_text_columns(df):
        long_text_names = set(globals().get("LONG_TEXT_COLUMNS", set()))
        long_text_names = {str(col).lower() for col in long_text_names}

        long_cols = []

        for col in df.columns:
            col_key = str(col).lower()

            if col_key in long_text_names:
                long_cols.append(col)
                continue

            try:
                sample = df[col].dropna().astype(str).head(5)
                if not sample.empty and sample.map(len).mean() > 130:
                    long_cols.append(col)
            except Exception:
                pass

        return long_cols

    def detail_label(row, index):
        label_cols = [
            "Bowler",
            "Batter",
            "Verdict",
            "Player",
            "Team",
            "Opponent",
            "Venue",
            "Phase",
            "Season",
            "Context",
            "bowler",
            "batter",
            "verdict",
            "player",
            "team",
            "opponent",
            "venue",
            "phase",
        ]

        parts = []

        for col in label_cols:
            if col in row.index:
                value = row.get(col)
                if value is not None and str(value).strip() and str(value).lower() != "nan":
                    parts.append(str(value).strip())

        if parts:
            return " - ".join(parts[:3])

        return f"Row {index + 1}"

    def render_table(title, value, show_title=True, allow_summary=False):
        if is_empty(value):
            return

        if not is_dataframe(value):
            if show_title:
                st.markdown(f"### {title_safe(title)}")
            st.write(value)
            return

        df = value.copy()
        df = apply_formatters(df, title)
        df = drop_hidden_columns(df)

        if df.empty:
            return

        if is_summary_table(df) and not allow_summary:
            return

        if show_title:
            st.markdown(f"### {title_safe(title)}")

        long_cols = get_long_text_columns(df)
        compact_df = df.drop(columns=long_cols, errors="ignore")

        if compact_df.empty:
            compact_df = df.copy()

        # Use st.table for reliability. It avoids the blank dataframe rendering issue.
        st.table(compact_df)

        if long_cols:
            st.markdown("**Details**")

            for index, row in df.iterrows():
                with st.expander(detail_label(row, index)):
                    for col in long_cols:
                        value = row.get(col)

                        if value is None:
                            continue

                        value_text = str(value).strip()

                        if not value_text or value_text.lower() == "nan":
                            continue

                        st.markdown(f"**{str(col)}**")
                        st.write(clean_text_safe(value_text))

    # Old call style:
    # display_result(title, table_value)
    if table_value is not None:
        render_table(response, table_value, show_title=False, allow_summary=True)
        return

    # Full response style:
    # display_result(response)
    if response is None:
        st.warning("No result returned.")
        return

    if not isinstance(response, dict):
        st.write(response)
        return

    paragraph = (
        response.get("analysis_paragraph")
        or response.get("paragraph")
        or response.get("answer")
        or response.get("message")
    )

    if paragraph:
        st.markdown("### Answer")
        st.markdown(clean_text_safe(paragraph))

    main_result = response.get("result")

    if is_dataframe(main_result) and not main_result.empty:
        if not is_summary_table(main_result):
            st.markdown("### Result")
            render_table("result", main_result, show_title=False, allow_summary=False)
    elif main_result is not None and not is_dataframe(main_result):
        st.markdown("### Result")
        st.write(main_result)

    extra_tables = response.get("extra_tables") or {}

    for title, value in extra_tables.items():
        if is_empty(value):
            continue

        render_table(title, value, show_title=True, allow_summary=False)

    similar_questions = (
        response.get("similar_questions")
        or response.get("follow_up_questions")
        or response.get("suggested_questions")
        or []
    )

    if similar_questions:
        st.markdown("### Similar questions and deep dives")

        for question in similar_questions:
            if st.button(str(question), key=f"similar_{hash(str(question))}"):
                select_question(str(question))
                st.rerun()

    sql_text = (
        response.get("sql")
        or response.get("sql_query")
        or response.get("combined_sql")
    )

    if sql_text:
        with st.expander("SQL used"):
            st.code(str(sql_text), language="sql")

def select_question(question):
    st.session_state.question_input = question
    st.session_state.run_requested = True
    
def get_similar_questions(question, response):
    question_lower = str(question).lower()
    matched_question = str(response.get("matched_question", "")).lower()

    if "venue profile" in matched_question or "tell me about" in question_lower:
        return [
            "tell me about Chepauk",
            "tell me about Wankhede",
            "tell me about Chinnaswamy",
            "how can MI beat KKR at Eden Gardens",
        ]

    if "team-vs-team match plan" in matched_question or "beat" in question_lower:
        return [
            "how can CSK beat GT at Chepauk",
            "how can RCB beat GT",
            "tell me about Eden Gardens",
            "which players are key in this matchup",
        ]

    if "team profile" in matched_question or question_lower.startswith("analyse"):
        return [
            "which team has the strongest current squad",
            "who will win next season",
            "analyse GT",
            "analyse CSK",
        ]

    if "run scorers" in question_lower:
        return [
            "top 10 run scorers for CSK",
            "top 10 run scorers at Eden Gardens",
            "top 10 run scorers in death overs",
            "best strike rate with minimum 300 balls",
        ]

    if "wicket" in question_lower or "bowler" in question_lower:
        return [
            "top 10 wicket takers",
            "best bowlers at Chepauk",
            "how should Bumrah bowl to Kohli",
            "what length should Rashid bowl to Kohli",
        ]

    return [
        "analyse GT",
        "tell me about Eden Gardens",
        "how can MI beat KKR at Eden Gardens",
        "top 10 run scorers",
    ]



def show_similar_questions(question, response):
    suggestions = get_similar_questions(question, response)

    if not suggestions:
        return

    st.subheader("Similar questions and deep dives")

    cols = st.columns(2)

    for index, suggestion in enumerate(suggestions):
        with cols[index % 2]:
            st.button(
                suggestion,
                key=f"suggestion_{index}_{suggestion}",
                on_click=select_question,
                args=(suggestion,),
                use_container_width=True,
            )

def run_question(question):
    question = str(question).strip()
    st.session_state.current_question = question

    if not question:
        st.warning("Type a question first.")
        return

    with st.spinner("Analysing cricket data..."):
        response = answer_question_with_fallback(question)

    if response.get("error"):
        st.error(response["error"])
        return

    paragraph = response.get("analysis_paragraph")

    if paragraph:
        render_answer_paragraph(paragraph)
    else:
        st.subheader("Answer")
        display_result("Result", response.get("result"))

    result = response.get("result")
    matched_question = str(response.get("matched_question", "")).lower()

    show_main_result_table = (
        should_show_table(result)
        and not paragraph
        and "team-vs-team match plan" not in matched_question
        and "team profile" not in matched_question
        and "venue profile" not in matched_question
    )

    if show_main_result_table:
        with st.expander("Main result table", expanded=False):
            display_result("Result", result)

    extra_tables = response.get("extra_tables", {})

    visible_extra_tables = {
        table_name: table_value
        for table_name, table_value in extra_tables.items()
        if table_name not in SKIP_EXTRA_TABLES and should_show_table(table_value)
    }

    if visible_extra_tables:
        st.subheader("Extra analysis tables")

        for table_name, table_value in visible_extra_tables.items():
            pretty_name = table_name.replace("_", " ").title()

            with st.expander(pretty_name, expanded=False):
                display_result(pretty_name, table_value)

    show_similar_questions(question, response)

    with st.expander("SQL used", expanded=False):
        sql_query = response.get("sql_query", "")

        if sql_query:
            st.code(sql_query, language="sql")
        else:
            st.info("No SQL query available.")


st.title("Cricket SQL Agent")
st.caption("Ask IPL analytics questions using the local SQL Server database.")

if "question_input" not in st.session_state:
    st.session_state.question_input = ""



EXAMPLE_QUESTION_GROUPS = {
    "Classic analytics": [
        "who are the top 10 run scorers in IPL",
        "who are the top 10 wicket takers in IPL",
        "who has the fastest 50 in ipl history",
        "which team has the most trophies",
    ],
    "Player profiles": [
        "analyse Kohli",
        "analyse Bumrah",
        "analyse Dhoni",
        "analyse Rohit Sharma",
    ],
    "Match plans": [
        "how can MI beat RCB",
        "how can CSK beat GT at Chepauk",
        "how can RCB beat GT at Chinnaswamy",
        "how can GT beat RR at Narendra Modi Stadium",
    ],
    "Venue profiles": [
        "tell me about Eden Gardens",
        "tell me about Chepauk",
        "tell me about Wankhede",
        "tell me about Chinnaswamy",
    ],
    "Squad and prediction": [
        "which team has the strongest current squad",
        "analyse CSK squad",
        "analyse RCB squad",
        "who will win next season",
    ],
    "Tactical matchups": [
        "how should Bumrah bowl to Kohli",
        "what length should Rashid bowl to Suryavanshi",
        "best bowlers against Kohli for GT",
        "best bowlers against Dhoni at Chepauk",
    ],
}
st.markdown("## Example questions")

for section_name, questions in EXAMPLE_QUESTION_GROUPS.items():
    with st.expander(section_name, expanded=(section_name == "Classic analytics")):
        cols = st.columns(2)

        for index, question in enumerate(questions):
            with cols[index % 2]:
                if st.button(question, key=f"example_{section_name}_{index}"):
                    select_question(question)
                    st.rerun()

st.markdown("### Ask your question")

question = st.text_input(
    "Question",
    key="question_input",
    placeholder="Example: how can MI beat KKR at Eden Gardens",
)

manual_submit = st.button("Give answer", type="primary")

if manual_submit:
    st.session_state.run_requested = True

if st.session_state.get("run_requested", False):
    st.session_state.run_requested = False
    run_question(st.session_state.question_input)