import streamlit as st
import html
from app.llm_agent import answer_question_with_fallback


st.set_page_config(
    page_title="Cricket SQL Agent",
    page_icon="🏏",
    layout="wide",
)


def prettify_name(name):
    return str(name).replace("_", " ").title()


def is_empty_table(dataframe):
    if dataframe is None:
        return True

    if hasattr(dataframe, "empty") and dataframe.empty:
        return True

    return False


def show_dataframe(title, dataframe):
    if is_empty_table(dataframe):
        return

    st.markdown(f"#### {title}")
    st.dataframe(dataframe, use_container_width=True)


def show_summary(result):
    if is_empty_table(result):
        return

    if "analysis_area" in result.columns and "insight" in result.columns:
        st.markdown("#### Summary")

        for _, row in result.iterrows():
            area = html.escape(str(row["analysis_area"]))
            insight = html.escape(str(row["insight"]))

            st.markdown(
                f"""
<div style="
    border: 1px solid rgba(250, 250, 250, 0.15);
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
    background-color: rgba(255, 255, 255, 0.03);
    white-space: normal;
    overflow-wrap: break-word;
    line-height: 1.5;
">
    <div style="font-weight: 700; margin-bottom: 6px;">{area}</div>
    <div>{insight}</div>
</div>
""",
                unsafe_allow_html=True,
            )

        return

    show_dataframe("Summary", result)


def show_answer(answer):
    method = answer.get("method")
    matched_question = answer.get("matched_question")
    error = answer.get("error")
    result = answer.get("result")
    sql_query = answer.get("sql_query")
    analysis_paragraph = answer.get("analysis_paragraph")
    extra_tables = answer.get("extra_tables")

    if error is not None and method != "fallback_question_bank":
        st.error(error)
        return

    if matched_question:
        st.caption(f"Matched mode: {matched_question}")
    elif method:
        st.caption(f"Method: {method}")

    if error is not None and method == "fallback_question_bank":
        st.warning("The LLM query failed, so the app used the closest fallback question from the question bank.")

    if analysis_paragraph:
        st.markdown("### Insight")
        st.info(analysis_paragraph)

    show_summary(result)

    if extra_tables:
        st.markdown("### Detailed Analysis")

        for table_name, table_data in extra_tables.items():
            if is_empty_table(table_data):
                continue

            with st.expander(prettify_name(table_name), expanded=False):
                st.dataframe(table_data, use_container_width=True)

    if sql_query:
        with st.expander("SQL used", expanded=False):
            st.code(sql_query, language="sql")


def set_example_question(question):
    st.session_state["question_input"] = question


if "question_input" not in st.session_state:
    st.session_state["question_input"] = ""


with st.sidebar:
    st.title("Demo Questions")

    st.markdown("### Basic SQL")
    basic_questions = [
        "Who has the most runs in IPL?",
        "Who has the most wickets in IPL?",
        "What is the highest individual score?",
        "Who has the fastest fifty?",
        "Who has the best bowling figures?",
    ]

    for question in basic_questions:
        st.button(
            question,
            key=f"basic_{question}",
            on_click=set_example_question,
            args=(question,),
            use_container_width=True,
        )

    st.markdown("### Player Intelligence")
    player_questions = [
        "Analyse Virat Kohli",
        "Analyse Kohli dismissals",
        "Analyse Virat Kohli shots",
        "What shot should Kohli avoid playing?",
        "Which shot gets Kohli out the most?",
    ]

    for question in player_questions:
        st.button(
            question,
            key=f"player_{question}",
            on_click=set_example_question,
            args=(question,),
            use_container_width=True,
        )

    st.markdown("### Bowler Intelligence")
    bowler_questions = [
        "Analyse Bumrah bowling matchups",
        "Analyse Bumrah bowling strategy",
        "What line and length works best for Chahal?",
        "What should Bumrah avoid bowling?",
        "Which batsman has Bumrah dismissed the most?",
    ]

    for question in bowler_questions:
        st.button(
            question,
            key=f"bowler_{question}",
            on_click=set_example_question,
            args=(question,),
            use_container_width=True,
        )

    st.markdown("### Team Intelligence")
    team_questions = [
        "Analyse CSK",
        "Team report for RCB",
        "Analyse Mumbai Indians as a team",
        "Which team has won the most titles?",
        "Who won the 2016 final?",
    ]

    for question in team_questions:
        st.button(
            question,
            key=f"team_{question}",
            on_click=set_example_question,
            args=(question,),
            use_container_width=True,
        )

    st.markdown("### Prediction")
    prediction_questions = [
        "Who will win next season based on data?",
        "Which team has the best title chances?",
    ]

    for question in prediction_questions:
        st.button(
            question,
            key=f"prediction_{question}",
            on_click=set_example_question,
            args=(question,),
            use_container_width=True,
        )


st.title("Cricket SQL Agent")
st.caption(
    "Ask IPL analytics questions using SQL, curated logic, and deeper cricket intelligence layers."
)

st.markdown(
    """
This app can answer direct cricket database questions and also perform deeper analysis such as player profiles,
dismissal patterns, shot selection, bowler matchups, team reports, bowling strategy, playoff analysis, and title-chance prediction.
"""
)

with st.form("question_form"):
    user_question = st.text_area(
        "Ask a cricket analytics question",
        key="question_input",
        height=100,
        placeholder="Example: Analyse Virat Kohli shots",
    )

    submitted = st.form_submit_button("Ask")

if submitted:
    if user_question.strip() == "":
        st.warning("Please enter a question.")
    else:
        with st.spinner("Analysing..."):
            answer = answer_question_with_fallback(user_question.strip())

        st.markdown("---")
        show_answer(answer)