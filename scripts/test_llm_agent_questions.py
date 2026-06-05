from app.llm_agent import answer_question_with_llm

def main():
    questions=[
        "Who are the top 10 run scorers?",
        "Who are the top 10 wicket takers?",
        "Who scored the most runs in the death overs?",
        "Who has taken the most wickets in the powerplay",
        "Which teams have the most wins while chasing?",
        "Which venues have the highest average first innings score?",
        "Which batters have the best strike rate with at least 300 balls faced?",
        "Which bowlers have the best economy rate with at least 300 legal balls bowled?",
    ]
    for question in questions:
        print("User question:")
        print(question)
        try:
            sql_query,result=answer_question_with_llm(question)
            print("\ngenerated sql")
            print(sql_query)
            print("\nresult")
            print(result)
        except Exception as error:
            print("\nerror")
            print(error)

if __name__=="__main__":
    main()