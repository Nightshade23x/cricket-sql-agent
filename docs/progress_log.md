Week 1

day 1

created project folder
created git repo
created venv environment
installed required python libs
created project folder structure
downloaded ipl cricsheet csv data
inspected raw delivery and match info files
prepared combined processed datasets into csvs called deliveries and matches
confirmed the dataset size
created sql server and connected it to vs code
ensured both the tables exist
tested the sql server using manual queries
all queries work perfectly

day 2
created a ques bank with natural lang cricket questions which map to sql queries
saved the question sql examples in a json file for future model training
created a python database connection file to connect the project to sql server
confirmed python can run sql queries and return results
created a basic question matching agent
tested the agent with cricket ques
confirmed the bagic agent can match a user ques to the closest saved sql example and return the correct sql result
installed and tested ollama locally
downloaded qwen2.5 model
connected python to local ollama model
tested sql generation from the local mode
cleaned the model output so generated sql can be used properly
fixed the ollama model storage path due to c drive being full
both main pipelines work separately...python to sql server, and python to ollama
combined the ollama local model pipeline with sql server database pipeline
created an llm based sql agent that takes a natural lang cricket ques and generates added safety checks to only allow select querie
tested the full flow from user question to generated sql to database result
confirmed the local model can generate sql and return ipl anayltic results from sql server
also tested a ques : who are the top 10 run scorers and received the correct ans.

day 3
restarted the ollama local server and confirmed the llm agent still works
created a multi questions test script to evaluate the llm agent across diff cricket analytics question types
tested the agent on batting,bowling,death overs,powerplay,chasing wins,venue analysis,strike rate,and economy rate questions
idenitifed issues where the local model generated incorrect sql logic for some cricket specific questions
fixed the prompt by adding better cricket defs and sql rules
added examples for chasing wins, venue average first innings score,strike rate etc
improved sql safety checks so safe subqueries are allowed while still blocking unsafe sql commands
updated the test script so one failed ques doesnt stop the script using try and except
confirmed the expected test questions generate correct sql and return results correctly
tested the llm based sql agent with multiple ques
checked the generated sql for wicket takers,death overs etc
added fallback logic incase the agent fails,if so then the agent can use the closest matching question from the bank
testing the reliable agent and confirmed both llm generation and fallback logic work correctly
confirmed the llm can answer custom ques beyon the fixed ques bank,as long as the ans can be calculated from the available database cols
first created a terminal based interactive chat then created streamlit for ui
tested and checked how it works

day 4(break after weekend)
created an evaluation dataset with 15 cricket ques across multiple categories such as batting,venue based etc
created an evaluation script to automatically test the reliable llm agent on the evaluation dataset
ran the evaluation script and all 15 test questions were successful
saved the results to a csv file
improved the streamlit web interface by adding automatic result charts for suitable questions
added chart generation for numeric result tables such as top run scorers
fixed the displayed result table index so it starts from 1 instead of 0
tested the streamlit app with questions and confirmed it works
tested more custom ques 
identified llm weaknesses in certain ques such as ducks,highest score etc
added curated templates for such ques
added team abbreviation handling such as csk,rcb etc and also added support for nicknames of venues such as chepauk
confirmed that the templates work in the streamlit app
