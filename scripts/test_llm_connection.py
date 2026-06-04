from app.llm import ask_ollama,clean_sql_response

def main():
    prompt="""
You are generating SQL server queries.
Rules are as follows:
-Use SQL server syntax only
-Use select top 10 instead of LIMIT
-Return only the SQL query
-Do not use markdown code fences
- Do not explain anything 
Task:
Write a SQL server query to select the top 10 batters by total runs from a table called deliveries with columns striker and runs_off_bat.
"""
    response=ask_ollama(prompt)#send prompt to ollama
    clean_sql=clean_sql_response(response)
    
    print(clean_sql)

if __name__=="__main__":
    main()

