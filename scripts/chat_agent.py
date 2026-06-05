from app.llm_agent import answer_question_with_fallback

def main():
    print("type your ques below")
    print("type exit to stop\n")

    while True:
        question=input("Ask a question")
        if question.lower()=="exit":
            print("goodbye")
            break
    
            
        response=answer_question_with_fallback(question)
        print("method used")
        print(response["method"])
        if response["matched_question"] is not None:
            print("\n matched fallback ques")
            print(response["matched_question"])
        if response["error"] is not None:
            print("\noriginal llm error:")
            print(response["error"])
        print("\nsql used")
        print(response["sql_query"])
        print("\n result")
        print(response["result"])

if __name__=="__main__":
    main()