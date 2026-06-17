import pandas as pd
import streamlit as st

from app.llm_agent import answer_question_with_fallback


st.set_page_config(
    page_title="Cricket SQL Agent",
    page_icon="🏏",
    layout="wide",
)


EXAMPLE_QUESTION_GROUPS = {
    "Match plans": [
        "How can CSK beat GT?",
        "How can CSK beat GT at Chepauk?",
        "How can RCB beat MI at Chinnaswamy?",
        "How can MI beat KKR at Wankhede?",
    ],
    "Squad and prediction": [
        "Who will win next season?",
        "Which team has the strongest current squad?",
        "Analyse CSK squad",
        "Analyse RCB squad",
        "Analyse GT",
        "Analyse CSK",
    ],
    "Tactical matchups": [
        "Which GT bowler should bowl to Pooran?",
        "What length should Hazlewood bowl against Dhoni?",
        "What line should Rashid bowl to Maxwell?",
        "Best matchups for Bumrah",
    ],
    "Player analysis": [
        "Analyse Virat Kohli",
        "Analyse MS Dhoni",
        "How does Pooran get out?",
        "What shots does Maxwell play?",
    ],
    "Classic analytics": [
        "Top 10 run scorers",
        "Top 10 wicket takers",
        "Who has the most runs at Chepauk?",
        "Who has the most wickets at Wankhede?",
    ],
}


def set_example_question(question):
    st.session_state.question_input = question


def is_non_empty_dataframe(value):
    return isinstance(value, pd.DataFrame) and not value.empty


def display_result(title, value):
    if value is None:
        return

    if isinstance(value, pd.DataFrame):
        if value.empty:
            st.info(f"No rows returned for {title}.")
        else:
            clean_value = value.copy()

            numeric_columns = clean_value.select_dtypes(include=["float", "float64"]).columns
            clean_value[numeric_columns] = clean_value[numeric_columns].round(2)

            st.dataframe(clean_value, use_container_width=True, hide_index=True)
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


if "question_input" not in st.session_state:
    st.session_state.question_input = ""

if "last_response" not in st.session_state:
    st.session_state.last_response = None

if "last_question" not in st.session_state:
    st.session_state.last_question = ""


st.title("Cricket SQL Agent")
st.caption("Ask IPL analytics, squad, matchup, and tactical match-plan questions.")

with st.sidebar:
    st.header("Example questions")

    for group_name, questions in EXAMPLE_QUESTION_GROUPS.items():
        with st.expander(group_name, expanded=(group_name == "Match plans")):
            for question in questions:
                st.button(
                    question,
                    key=f"example_{group_name}_{question}",
                    on_click=set_example_question,
                    args=(question,),
                    use_container_width=True,
                )

    st.divider()

    if st.button("Clear question", use_container_width=True):
        st.session_state.question_input = ""
        st.session_state.last_response = None
        st.session_state.last_question = ""
        st.rerun()


left_col, right_col = st.columns([2, 1])

with left_col:
    user_question = st.text_area(
        "Ask a cricket question",
        key="question_input",
        height=100,
        placeholder="Example: How can CSK beat GT at Chepauk?",
    )

with right_col:
    st.markdown("### Current capabilities")
    st.markdown(
        """
        - Match plans  
        - Current squad reports  
        - Title prediction  
        - Bowler-vs-batter matchups  
        - Length and line plans  
        - Player profiles  
        - Classic SQL stats  
        """
    )


answer_clicked = st.button(
    "Give answer",
    type="primary",
    use_container_width=True,
)

if answer_clicked:
    clean_question = st.session_state.question_input.strip()

    if not clean_question:
        st.warning("Type a question or choose one of the examples.")
    else:
        with st.spinner("Thinking..."):
            response = answer_question_with_fallback(clean_question)

        st.session_state.last_response = response
        st.session_state.last_question = clean_question


response = st.session_state.last_response

if response is not None:
    st.divider()

    st.markdown("## Answer")
    st.caption(f"Question: {st.session_state.last_question}")

    error = response.get("error")

    if error:
        st.error(error)

    matched_question = response.get("matched_question")
    method = response.get("method")

    meta_cols = st.columns(2)

    with meta_cols[0]:
        if matched_question:
            st.info(f"Matched route: {matched_question}")

    with meta_cols[1]:
        if method:
            st.info(f"Method: {method}")

    analysis_paragraph = response.get("analysis_paragraph")

    if analysis_paragraph:
        st.markdown("### Summary")
        st.write(analysis_paragraph)

    result = response.get("result")

    if result is not None:
        st.markdown("### Main result")
        display_result("Main result", result)

    extra_tables = response.get("extra_tables", {})

    if extra_tables:
        st.markdown("### Extra analysis tables")

        for table_name, table_value in extra_tables.items():
            pretty_name = table_name.replace("_", " ").title()

            with st.expander(pretty_name, expanded=False):
                display_result(pretty_name, table_value)

    sql_query = response.get("sql_query")

    if sql_query:
        with st.expander("SQL used", expanded=False):
            st.code(sql_query, language="sql")