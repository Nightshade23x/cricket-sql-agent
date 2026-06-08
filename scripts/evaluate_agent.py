import json
from pathlib import Path
import pandas as pd
from app.llm_agent import answer_question_with_fallback

def main():
    test_file=Path("data/evaluation/test_questions.json")
    output_file=Path("reports/evaluation_results.csv")
    output_file.parent.mkdir(parents=True,exist_ok=True)
    with open(test_file,"r",encoding="utf-8") as file:
        questions=json.load(file)
    results=[]
    for item in questions:
        question_id=item["id"]
        category=item["category"]
        question=item["question"]
        print("question id",question_id)
        print("category",category)
        print("question",question)

        try:
            response=answer_question_with_fallback(question)
            result_table=response["result"]
            row_count=len(result_table) if result_table is not None else 0
            success=result_table is not None and row_count>0
            sql_query=response["sql_query"]
            method=response["method"]
            error=response["error"]
            print("method",method)
            print("sucess",success)
            print("rows returned",row_count)
            print("sql used")
            print(sql_query)

        except Exception as exception:
            success=False
            row_count=0
            method="failed"
            sql_query=""
            error=str(exception)
            print("failed with error")
            print(error)
        results.append(
            {
                "id":question_id,
                "category":category,
                "question":question,
                "success":success,
                "method":method,
                "rows_returned":row_count,
                "sql_query":sql_query,
                "error":error
            }
        )
    results_df=pd.DataFrame(results)
    results_df.to_csv(output_file,index=False)
    total_questions=len(results_df)
    successful_questions=results_df["success"].sum()
    success_rate=successful_questions/total_questions*100
    print("evaluation complete")
    print("total ques",total_questions)
    print("sucessful questions",successful_questions)
    print("sucess rate",round(success_rate,2),"%")
    print("results saved to",output_file)

if __name__ == "__main__":
    main()