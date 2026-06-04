from app.llm_agent import answer_question_with_llm


def main():
    user_question = "Who are the top 10 run scorers?"

    print("Starting LLM agent test...")

    print("Sending question to LLM agent:")
    print(user_question)

    sql_query, result = answer_question_with_llm(user_question)

    print("\nGenerated SQL:")
    print(sql_query)

    print("\nResult:")
    print(result)


if __name__ == "__main__":
    main()