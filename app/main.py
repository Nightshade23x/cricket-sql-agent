import streamlit as st

from app.llm_agent import answer_question_with_fallback


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
            st.code(response["sql_query"], language="sql")

            st.subheader("Result")
            st.dataframe(response["result"], use_container_width=True)


main()