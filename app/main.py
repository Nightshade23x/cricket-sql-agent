import pandas as pd
import streamlit as st

from app.llm_agent import answer_question_with_fallback


st.set_page_config(
    page_title="Cricket SQL Agent",
    page_icon="??",
    layout="wide",
)


def should_show_table(value):
    if value is None:
        return False

    if isinstance(value, pd.DataFrame):
        return not value.empty

    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0

    return True


def display_result(title, value):
    if value is None:
        return

    if isinstance(value, pd.DataFrame):
        if value.empty:
            st.info(f"No rows returned for {title}.")
            return

        clean_value = value.copy()

        numeric_columns = clean_value.select_dtypes(include=["float", "float64"]).columns
        clean_value[numeric_columns] = clean_value[numeric_columns].round(2)

        st.dataframe(clean_value, use_container_width=True, hide_index=True)

        long_text_columns = [
            col for col in clean_value.columns
            if col.lower() in ["reason", "why", "insight", "summary", "trophy_summary", "result_summary"]
        ]

        if long_text_columns:
            st.markdown("#### Full text details")

            for row_index, row in clean_value.iterrows():
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
                ]:
                    if possible_label in clean_value.columns:
                        label_parts.append(str(row.get(possible_label, "")))

                label = " - ".join([part for part in label_parts if part and part != "nan"])

                if not label:
                    label = f"Row {row_index + 1}"

                for text_col in long_text_columns:
                    text_value = row.get(text_col, "")

                    if pd.notna(text_value) and str(text_value).strip():
                        st.markdown(f"**{label}**")
                        st.write(str(text_value))

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

    st.subheader("Answer")

    paragraph = response.get("analysis_paragraph")
    if paragraph:
        st.write(paragraph)
    else:
        display_result("Result", response.get("result"))

    result = response.get("result")
    if should_show_table(result):
        with st.expander("Main result table", expanded=False):
            display_result("Result", result)

    extra_tables = response.get("extra_tables", {})
    if extra_tables:
        st.subheader("Extra analysis tables")

        for table_name, table_value in extra_tables.items():
            if not should_show_table(table_value):
                continue

            pretty_name = table_name.replace("_", " ").title()

            with st.expander(pretty_name, expanded=False):
                display_result(pretty_name, table_value)

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
        "best bowlers against Kohli",
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
                    st.session_state.question_input = example
                    st.rerun()

st.markdown("### Ask your question")

question = st.text_input(
    "Question",
    key="question_input",
    placeholder="Example: how can MI beat KKR at Eden Gardens",
)

if st.button("Give answer", type="primary"):
    run_question(st.session_state.question_input)
