from app.agent import answer_question

def main():
    questions=[
        "who are the top run scorers?",
        "who has taken the most wickets",
        "who scored the most runs in the death overs",
        "which teams win the most while chasing",
    
    ]
    for question in questions:
        print("\nUser question:")
        print(question)
        best_example,sql_query,result=answer_question(question)
        if result is None:
            print("No matching sql example found")
        else:
            print("\n matched example question")
            print(best_example["question"])

            print("\nsql used")
            print(sql_query)

            print("\n result")
            print(result)

if __name__=="__main__":
    main()