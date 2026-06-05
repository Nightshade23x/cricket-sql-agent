from app.llm_agent import answer_question_with_fallback

def main():
    questions=[
        "Who are the top 10 run scorers?",
        "WHo are the top 10 wicket takers?",
        "Who scored the most runs in death overs?",
        "Who has taken the most wickets in the powerplay",
        "Which teams have the most wins while chasing",
        "Which venues have the highest average first innings score?",
        "Which batters have the best strike rate with at least 300 balls faced?",
        "Which bowlers have the best economy rate with at least 300 legal balls bowled?",
    ]
    for question in questions:
        print("User question:")
        print(question)
        response=answer_question_with_fallback(question)
        print("\nmethod used:")
        print(response["method"])
        if response["matched_question"] is not None:
            print("\nmatched fallback question")
            print(response["matched_question"])
        if response["error"] is not None:
            print("\noriginal llm error")
            print(response["error"])
        print("\nsql used")
        print(response["sql_query"])
        print("\nresult")
        print(response["result"])

if __name__=="__main__":
    main()