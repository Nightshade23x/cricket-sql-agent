from app.db import run_query
from app.llm import ask_ollama,clean_sql_response

def build_sql_prompt(user_question):#builds the full prompt that we send to the local model
    prompt=f"""
You are a cricket analytics sql agent
your job is to convert the user's cricket analytics question into sql server query

database schema:
table:matches
columns:
-match_id
-season
-start_date
-eveny
-venue
-city
-toss_winner
-toss_decision
-player_of_match
-winner
-winner_runs
-winner_wickets

Table:deliveries
columns:
-delivery_id
-match_id
-season
-start_date
-venue
-innings
-ball
-batting_team
-bowling_team
-striker
-non_striker
-bowler
-runs_off_bat
-extras
-wides
-noballs
-byes
-legbyes
-penalty
-wicket_type
-player_dismissed
-other_wicket_type
-other_player_dismissed

Important cricket definitions:
-total batter runs=SUM(runs_off_bat)
-total team runs=sum(runs_off_bat+extras)
-legal ball=wides IS NULL and noballs IS NULL
-batter strike rate= runs_off_bat*100/legal balls faced
-bowler economy rate= runs conceded * 6 / legal balls bowled
-powerplay overs= FLOOR(ball) BETWEEN 0 and 5
-death overs= FLOOR(ball) BETWEEN 15 and 19
-Bowling wickets should exlude run out,retired hurt,retired out,and obstructing the field
-batting_team and bowling_team are columns in the deliveries table, not in the matches table
-for chasing questions, use deliveries where innings=2 and join with matches using match_id
- for team chasing wins, compare d.batting_team with m.winner
- for average first innings score by venue, first calculate total score per match and venue where innings=1, then average those totals grouped by venue.
- the ball column stores over.ball values such as 0.1,5.3 and 19.6. it does not mean total balls faced or total balls bowled.
-never use ball>=300 to mean at least 300 balls faced or bowled
-balls faced should be calculated using legal deliveries: sum(case when wides IS NULL and noballs IS NULL then 1 else 0 END)
-strike rate= sum(runs_off_bat)*100.0/legal balls faced
-economy rate should include all deliveries bowled, not only wicket deliveries
-do not filter wicket_type when calculating economy rate
-economy rate= sum(runs_off_bat+extras)*6.0/legal balls bowled

sql rules:
-use sql server syntax only
-use select top 10 instead of limit
-only write select queries
-do not write insert,update,delete,drop,alter,create,truncate,exec or merge
-return only the sql query
-do not use markdown code fences
-do not explain anything

Examples:

Question: Who are the top 10 run scorers?
SQL:
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
GROUP BY striker
ORDER BY total_runs DESC;

Question: Who are the top 10 wicket takers?
SQL:
SELECT TOP 10
    bowler,
    COUNT(*) AS wickets
FROM deliveries
WHERE wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY bowler
ORDER BY wickets DESC;

Question: Who scored the most runs in death overs?
SQL:
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS death_overs_runs
FROM deliveries
WHERE FLOOR(ball) BETWEEN 15 AND 19
GROUP BY striker
ORDER BY death_overs_runs DESC;

Question: Which teams have the most wins while chasing?
SQL:
select top 10
    d.batting_team as chasing_team,
    count(distinct d.match_id) as chasing_wins
from deliveries d
join matches m
    on d.match_id=m.match_id
where d.innings=2
    and d.batting_team=m.winner
group by d.batting_team
order by chasing_wins desc;

Question: Which venues have the highest average first innings score?
SQL:
select top 10
    venue,
    round(avg(total_score*1.0),2) as average_first_innings_score,
    count(*) as innings_count
from(
    select
        match_id,
        venue,
        sum(runs_off_bat+extras) as total_score)
    from deliveries
    where innings=1
    group by match_id,venue
) as first_innings_scores
group by venue
having count(*)>=10
order by average_first_innings_score desc;

Question: Which batters have the best strike rate with at least 300 balls faced?
SQL:
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS runs,
    SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    ROUND(
        SUM(runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS strike_rate
FROM deliveries
GROUP BY striker
HAVING SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) >= 300
ORDER BY strike_rate DESC;

Question: Which bowlers have the best economy rate with at least 300 legal balls bowled?
SQL:
SELECT TOP 10
    bowler,
    SUM(runs_off_bat + extras) AS runs_conceded,
    SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) AS legal_balls,
    ROUND(
        SUM(runs_off_bat + extras) * 6.0 /
        NULLIF(SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS economy_rate
FROM deliveries
GROUP BY bowler
HAVING SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) >= 300
ORDER BY economy_rate ASC;

User question:
{user_question}
"""
    return prompt

def is_safe_select_query(sql_query):
    cleaned_query = sql_query.strip()
    cleaned_lower = cleaned_query.lower()
    # Allow normal SELECT queries and WITH CTE queries
    if not (cleaned_lower.startswith("select") or cleaned_lower.startswith("with")):
        return False
    # Remove one final semicolon if it exists
    query_without_trailing_semicolon = cleaned_lower.rstrip(";").strip()
    # Reject multiple SQL statements
    if ";" in query_without_trailing_semicolon:
        return False
    forbidden_words = [
        "insert ",
        "update ",
        "delete ",
        "drop ",
        "alter ",
        "create ",
        "truncate ",
        "exec ",
        "execute ",
        "merge "
    ]
    for word in forbidden_words:
        if word in cleaned_lower:
            return False
    return True

def answer_question_with_llm(user_question):#generates sql using ollama and runs it on sql server
    prompt=build_sql_prompt(user_question)#builds the model prompt
    raw_response=ask_ollama(prompt)#sends the prompt to the local ollama model
    sql_query=clean_sql_response(raw_response)#cleans code fences from the model response
    if not is_safe_select_query(sql_query):#checks that the generated sql is safe
        raise ValueError("Model generated an unsafe or invalid query")
    result=run_query(sql_query)
    return sql_query,result 
