import re

import pandas as pd
import streamlit as st

from app.llm_agent import answer_question_with_fallback


st.set_page_config(
    page_title="Cricket SQL Agent",
    layout="wide",
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

SKIP_EXTRA_TABLES = {
    "team_report_squad_summary",
}


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


def split_into_sentences(text):
    text = str(text).strip()

    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def render_answer_paragraph(paragraph):
    st.subheader("Answer")

    sentences = split_into_sentences(paragraph)

    if not sentences:
        st.write(paragraph)
        return

    for sentence in sentences:
        st.markdown(f"- {sentence}")


def render_action_plan(df):
    clean_df = clean_dataframe_for_display(df)

    for _, row in clean_df.iterrows():
        phase = row.get("phase", "Action")
        plan = row.get("plan", "")
        why = row.get("why", "")
        key_players = row.get("key_players", "")

        with st.container(border=True):
            st.markdown(f"**{phase}**")

            if pd.notna(plan) and str(plan).strip():
                st.write(str(plan))

            if pd.notna(why) and str(why).strip():
                st.caption(f"Why: {why}")

            if pd.notna(key_players) and str(key_players).strip():
                st.caption(f"Key players: {key_players}")


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
                    label_parts.append(str(value))

        label = " - ".join(label_parts)

        if not label:
            label = f"Row {row_index + 1}"

        with st.container(border=True):
            st.markdown(f"**{label}**")

            for text_col in long_text_columns:
                text_value = row.get(text_col, "")

                if pd.notna(text_value) and str(text_value).strip():
                    st.write(str(text_value))


def display_result(title, value):
    if value is None:
        return

    if isinstance(value, pd.DataFrame):
        if value.empty:
            st.info(f"No rows returned for {title}.")
            return

        clean_value = clean_dataframe_for_display(value)

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

        if not table_value.empty and len(table_value.columns) > 0:
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
            "tell me about this venue",
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
            if st.button(suggestion, key=f"suggestion_{index}_{suggestion}"):
                st.session_state.pending_question = suggestion
                st.rerun()


def run_question(question):
    question = str(question).strip()

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
    if should_show_table(result):
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

if "pending_question" in st.session_state:
    st.session_state.question_input = st.session_state.pop("pending_question")

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
                if st.button(example, key=f"example_{group_name}_{index}"):
                    st.session_state.pending_question = example
                    st.rerun()

st.markdown("### Ask your question")

question = st.text_input(
    "Question",
    key="question_input",
    placeholder="Example: how can MI beat KKR at Eden Gardens",
)

if st.button("Give answer", type="primary"):
    run_question(st.session_state.question_input)
