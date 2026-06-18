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


def pretty_column_name(column_name):
    return str(column_name).replace("_", " ").title()


def clean_user_text(text):
    text = str(text)

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


def display_result(title, value):
    if value is None:
        return

    if isinstance(value, pd.DataFrame):
        if value.empty:
            st.info(f"No rows returned for {title}.")
            return

        clean_value = clean_dataframe_for_display(value)

        if str(title).lower() == "head to head":
            clean_value = rename_head_to_head_columns(clean_value)
        if str(title).lower() == "recent head to head results":
            clean_value = format_recent_h2h_table(clean_value)

        lower_columns = {str(col).lower() for col in clean_value.columns}

        if {"phase", "plan", "why"}.issubset(lower_columns):
            render_action_plan(clean_value)
            return

        long_text_columns = [
            col for col in clean_value.columns
            if str(col).lower() in LONG_TEXT_COLUMNS
        ]

        table_value = clean_value.copy()

        if long_text_columns:
            table_value = table_value.drop(columns=long_text_columns)

        remaining_columns = {str(col).lower() for col in table_value.columns}

        show_dataframe = (
            not table_value.empty
            and len(table_value.columns) > 0
            and not remaining_columns.issubset(LABEL_ONLY_COLUMNS)
        )

        if show_dataframe:
            display_table = table_value.rename(columns=pretty_column_name)
            st.dataframe(display_table, use_container_width=True, hide_index=True)

        if long_text_columns:
            render_long_text_details(clean_value, long_text_columns)

        return

    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            st.info(f"No rows returned for {title}.")
        else:
            st.write(value)
        return

    if isinstance(value, dict):
        if len(value) == 0:
            st.info(f"No data returned for {title}.")
        else:
            st.json(value)
        return

    st.write(value)

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



example_groups = {
    "Match plans": [
        "how can MI beat KKR at Eden Gardens",
        "how can CSK beat GT at Chepauk",
        "how can RCB beat GT",
    ],
    "Venue profiles": [
        "tell me about Eden Gardens",
        "tell me about Chepauk",
        "tell me about Wankhede",
    ],
    "Squad and prediction": [
        "analyse GT",
        "analyse CSK",
        "which team has the strongest current squad",
        "who will win next season",
    ],
    "Tactical matchups": [
        "how should Bumrah bowl to Narine",
        "what length should Rashid bowl to Kohli",
        "which bowlers should be used against Kohli as a batter",
    ],
    "Classic analytics": [
        "top 10 run scorers",
        "top 10 wicket takers",
        "venues with highest average first innings score",
    ],
}

st.markdown("### Example questions")

for group_name, examples in example_groups.items():
    with st.expander(group_name, expanded=False):
        cols = st.columns(2)

        for index, example in enumerate(examples):
            with cols[index % 2]:
                st.button(
                    example,
                    key=f"example_{group_name}_{index}",
                    on_click=select_question,
                    args=(example,),
                    use_container_width=True,
                )

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