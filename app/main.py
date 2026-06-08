import streamlit as st

from app.llm_agent import answer_question_with_fallback

def show_chart_if_possible(result):
    if result is None:
        return
    if result.empty:
        return
    if len(result) < 2:
        return
    numeric_columns=result.select_dtypes(include="number").columns.tolist()
    if len(numeric_columns)==0:
        return
    preferred_value_columns=[
        "total_runs",
        "wickets",
        "death_overs_runs",
        "powerplay_overs_runs",
        "chasing_wins",
        "average_first_innings_score",
        "strike_rate",
        "economy_rate",
        "match_count",
        "wins",
        "runs_in_innings",
        "total_runs_conceded",
        "runs_conceded",
    ]
    value_column=None
    for column in preferred_value_columns:
        if column in result.columns:
            value_column=column
            break
    if value_column is None:
        value_column=numeric_columns[-1]
    label_column=None
    for column in result.columns:
        if column!=value_column and column not in numeric_columns:
            label_column=column
            break
    if label_column is None:
        return
    chart_data=result[[label_column,value_column]].copy()
    chart_data=chart_data.set_index(label_column)
    st.subheader("chart")
    st.bar_chart(chart_data)

def main():
    st.set_page_config(page_title="Cricket SQL Agent", layout="wide")

    st.title("Local Cricket Analytics SQL Agent")

    st.write("Ask cricket analytics questions using the local IPL database.")

    st.write("This app runs locally using Ollama, Python, and SQL Server.")

    example_questions = [
        "Who are the top 10 run scorers?",
        "Who are the top 10 wicket takers?",
        "Who scored the most runs in death overs?",
        "Who has taken the most wickets in the powerplay?",
        "Which teams have the most wins while chasing?",
        "Which venues have the highest average first innings score?",
        "Which batters have the best strike rate with at least 300 balls faced?",
        "Which bowlers have the best economy rate with at least 300 legal balls bowled?",
    ]

    selected_example = st.selectbox(
        "Choose an example question:",
        example_questions
    )

    question = st.text_input(
        "Or type your own question:",
        value=selected_example
    )

    run_button = st.button("Ask Agent")

    if run_button:
        if question.strip() == "":
            st.warning("Please enter a question.")
        else:
            with st.spinner("Generating SQL and querying the database..."):
                response = answer_question_with_fallback(question)

            st.subheader("Method Used")
            st.write(response["method"])

            if response["matched_question"] is not None:
                st.subheader("Matched Fallback Question")
                st.write(response["matched_question"])

            if response["error"] is not None:
                st.subheader("Original LLM Error")
                st.write(response["error"])

            st.subheader("SQL Used")

            if response["sql_query"] is not None:
                st.code(response["sql_query"], language="sql")
            else:
                st.write("No SQL query was generated.")

            st.subheader("Result")

            if response["result"] is not None:
                result = response["result"].copy()

                result.index = result.index + 1

                st.dataframe(result, use_container_width=True)

                show_chart_if_possible(result)
            else:
                st.info("No result table to display.")


                                


main()