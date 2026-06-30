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
added more templates for fastest 50 and fastest 100 ques
tested it against known records
found a bug so fixed that as no balls were being excluded from batting balls faced
corrected it and now results are accurate
continued testing custom cricket questions in the streamlit app
expanded evaluation to 32 questions
reran evaluation and imrpoved the agent based on incorrect sql logic

day 4
continued manual testing
focused on making the agent handle more specific and realistic user questions for specific players
added support for player specific ques such as how many fours has kohli hit etc
added support for team based records such as most fifties for a team
added support for orange cap and purple cap
added support for bowling records such as fifers
added support for match related records such as most sixes in a game
improved player name handling so agent can use player surnames rather than having to have each player surname manually added
added support for player nicknames such as thala or sky
added venue based ques combining with players such as how many sixes does rohit sharma have at wankhede
confirmed that the agent can now handle a broad set of questions

day 5
continued training
tested more advanced ques involving season milestones,venue milestones,team records etc
fixed order of functions as some broader templates were triggering before the more specific ones
added support for most hundreds and fifties by season
added support for most hundreds and fifties at specific venues
confirmed that training process is mostly been about asking new questions to the model and if it cannot ans,adding support for it
added support for season specific total,such as how many runs did dhoni score in 2015
added support for season specific boundary leaderboards
added support for player fifties in a specific season
added support for all time best performances in a season
added fastest 50/100 support for a team,against a team,at a venue or all cases combined
fixed rcb error as there was bengaluru and bangalore so joined them
added support for hattricks and extras
highest chases by teams,lowest defended scores by teams

day 6
added support for slowest fifties overall,per team,per venue
added support for playoffs
so made new table in ssms based on dates...also added labels
will continue testing playoffs tom

day 7
exteneded the agent beyond normal analysis
added matchups for both bowlers and batsman
added paragraphs that describe the analysis

day 8
added new datasource from kaggle which will help to support more advanced cricket analysis based on shot selection,line,lenght and batting bowling pattenrs
created new func to help with batter shot patterns
did the same for bowling
updated the routing in llm agent as well so shot selection ques route to the new player shot analysis func,same with the bowling func
improved venue and team normalisation...some teams and venues appeared under diff names so combined them
improved frontend,looks cleaner now...also fixed summary table as it kept cutting off
enhanced team profile analysis
improved title predictin model
added deper batter vs bowler intelligence...now gives better analysis
added curated support for season milestone questions
added match summary intelligence
added summaries for questions such as list last 5 encounters of mi vs csk
added fastest to 1000 runs etc,fastest to 50 wickets as well
added stats for most runs scored in pp,death overs etc

day 9
improved the agent by adding a new batter specific bowling plan layer. the agent can now ans questions like what should be bowled to pooran in the death overs
also added forced tactical scenarios...so for eg,if user asks what spin to ball to dube,the model can ans
so improved matchup analysis
updated full player profiles to show current players as well rather than only old ones
added current squads using scraping and scripts
updated team bowler recommendation to give current squad bowlers
updated analysis file also to take into accoutn recent players 
upgraded title prediction model
added current squad intelligence,so who has the stronfest squad
fixed bowler matchup ranking,more emphasis on dismissals
added enahnced team report
fixed kuldip yadav and kuldeep yadav mismatch

day10
completed standalone venue analysis
added venue intelligence to team vs team match plans
improved team reports
improved the ui
fixed bowling overs error

day 11
improved frontend
matchplan now shows cleaner ans
action plan cards are easier to read
added similar ques box and fixed a bug where it didnt work
improved tactical wording
bowling matchups are better now
fixed best bowlers against kohli ques,so kohli is treated as a batter not bowler
improved front end bugs
improved venue grouping

day 12
renamed title
improved frontend to become cleaner
changed layout
added new routes for highest score in losing cause,most runs in a single over etc
most fifties in playoffs
team lost percent at a venue
improved tactical matchups
improved player profiles

day 13
added stability tests
added support for dot balls
updated player profile tables
added comparion of teams such as trophies won
added best xi for teams
added what type of player to target per team via squad analysis
fixed action plan bug
fixed match plan bug where players such as sai and vaibhav arent showing

day 14
added cache tables to improve performance
added support for better matchups data

day 15
added season trend under player profiles
cleaned frontend by removing unneccesary text
resolved team names

day 16
added documentation
added support for strike rates and average
updated example questions
fixed some backend bugs

day 17
fixed example question bug
added support for new chandigarh
changed date format to dd-mm-yyyy
fixed season error of 2007/08 where it doesnt recognise 2008...also fixed other top run scorers bugs