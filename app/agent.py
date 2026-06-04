import json
import re
from pathlib import Path

from app.db import run_query

def load_examples():#load question sql examples
    examples_path=Path("data/training/question_sql_examples.json")
    with open(examples_path,"r",encoding="utf-8") as file:
        examples=json.load(file)
    return examples

def clean_text(text):#func cleans text for comparision
    text=text.lower()
    text=re.sub(r"[^a-z0-9\s]","",text)#remove punctuation and special characters
    words=text.split()
    common_words=["the","is","are","in","of","to","with","a","an","and"]# words that can be removed 
    useful_words=[]#empty list to storee the important words
    for word in words:
        if word not in common_words:
            useful_words.append(word)
    return useful_words

def find_best_example(user_question,examples):# finds the best matching example
    user_words=clean_text(user_question)
    best_example=None
    best_score=0
    for example in examples:
        example_words=clean_text(example["question"])
        score=0#starts score at 0
        for word in user_words:
            if word in example_words:
                score=score+1
        if score>best_score:
            best_score=score
            best_example=example#updates the best example
    return best_example,best_score

def answer_question(user_question):#answers a user's cricket analytics question
    examples=load_examples()
    best_example,score=find_best_example(user_question,examples)#finds the closest matching example
    if best_example is None or score==0:#checks if no useful match was found
        return None,None,None#returns nth useful
    sql_query=best_example["sql"]#gets the sql query from the matched example
    result=run_query(sql_query)#runs the sql query on sql server
    return best_example,sql_query,result