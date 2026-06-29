# Project Explanation: IPL SQL Agent

## 1. What I Built

I built a local IPL cricket analytics assistant that allows users to ask natural-language questions about Indian Premier League data and receive structured answers from a SQL Server database.

The system is called **IPL SQL Agent**. It combines:

- processed IPL ball-by-ball data,
- a local SQL Server database,
- a Python backend,
- a local Ollama language model,
- and a Streamlit frontend.

The goal was to create an assistant that can understand cricket analytics questions and answer them using SQL queries instead of internet search.

Example questions include:

```text
top 10 run scorers in 2026
top 10 wicket takers for CSK in 2026
analyse Bumrah
how many fifties does Kohli have against CSK
who has taken the most wickets against CSK
how can GT beat RR at Narendra Modi Stadium
best bowlers against Kohli for Delhi Capitals
```

---

## 2. Why I Built It

The project was built to explore how natural language can be used to interact with a structured sports database.

Instead of manually writing SQL every time, the user can ask cricket questions in normal language. The agent then identifies the type of question, builds or selects the correct SQL query, runs it locally, and shows the result in the app.

This is useful because cricket data is highly structured, but most users do not want to manually write SQL queries to analyse it.

---

## 3. Data Used

The project uses processed IPL data from Cricsheet.

The main tables are:

| Table | Purpose |
|---|---|
| `deliveries` | Ball-by-ball IPL data |
| `matches` | Match-level information |
| `current_squads` | Current squad and player role information |
| `batter_innings_milestones` | Cached fastest 50 and 100 data |
| `shot_events` | Shot/event-level data where available |

The most important table is `deliveries`, which contains ball-by-ball information such as batter, bowler, runs, extras, wickets, batting team, bowling team, innings, venue, and season.

---

## 4. How the System Works

The system follows this flow:

```text
User question
    ↓
Streamlit frontend
    ↓
Question router / SQL agent
    ↓
SQL Server database
    ↓
Result table and explanation
```

### Step 1: User asks a question

The user types a cricket question into the Streamlit app.

### Step 2: The agent understands the question type

The Python agent checks whether the question matches a known route, such as:

- player profile,
- top run scorers,
- top wicket takers,
- fastest 50 or 100,
- team trophies,
- venue leaderboards,
- tactical match plan,
- player-vs-team records.

### Step 3: SQL is generated or selected

For important question types, the system uses direct SQL routes. This makes the answers more reliable than depending only on a language model.

### Step 4: Query is run locally

The SQL query is executed on the local `CricketAnalytics` SQL Server database.

### Step 5: Results are displayed

The frontend displays:

- a short answer,
- a main result table,
- extra tabs for supporting analysis,
- the SQL query used,
- and similar suggested questions.

---

## 5. Main Features Implemented

### Batting Analytics

The agent can answer questions about:

- top run scorers,
- batting averages,
- strike rates,
- fifties,
- hundreds,
- player season trends,
- venue-wise batting records,
- team-wise batting records.

Example:

```text
top 10 run scorers in 2026
```

### Bowling Analytics

The agent can answer questions about:

- top wicket takers,
- economy rate,
- bowling strike rate,
- dot balls,
- wickets by season,
- venue-wise bowling records,
- team-wise bowling records.

Example:

```text
top 10 wicket takers for CSK in 2026
```

### Player Profiles

The agent can analyse a player and show both batting and bowling information.

For example:

```text
analyse Bumrah
```

This includes:

- batting summary,
- bowling summary,
- batting season trend,
- bowling season trend.

If the player is mainly a bowler, bowling information is shown first. If the player is mainly a batter, batting information is shown first.

### Milestone Queries

The agent can answer filtered milestone questions such as:

```text
how many fifties does Kohli have against CSK
how many hundreds does Kohli have at Wankhede
```

It can filter by:

- opposition team,
- venue,
- season.

### Team Analytics

The agent supports team-level questions such as:

```text
who has won the most trophies
which team has the best win percentage
```

It can also answer team-wise player leaderboards, such as:

```text
top 10 run scorers for CSK in 2026
top 10 wicket takers for CSK in 2026
```

### Venue Analytics

The agent supports venue-based questions such as:

```text
top 10 run scorers at Wankhede
top 10 run scorers in Wankhede
who has the most runs at Wankhede
```

The app supports different ways of asking the same question, so the user does not have to use one exact phrase.

### Tactical Analysis

The agent can generate tactical cricket analysis using current squads and historical data.

Examples:

```text
how can GT beat RR at Narendra Modi Stadium
best bowlers against Kohli for Delhi Capitals
```

For current-team tactical questions, the agent uses the `current_squads` table so that recommendations are based on current players.

---

## 6. Handling Ambiguity

Some cricket abbreviations are ambiguous. For example, `DC` can mean:

- Delhi Capitals,
- Deccan Chargers.

To avoid giving the wrong answer, the agent asks the user to clarify instead of guessing.

Example:

```text
best bowlers against Kohli for dc
```

The agent asks the user to use the full team name.

---

## 7. Testing Performed

A regression test file was created to check that important routes continue to work.

The main test command is:

```powershell
python scripts\test_core_questions.py
```

At the latest stable stage, **42 questions passed**.

The tests cover areas such as:

- batting leaderboards,
- bowling leaderboards,
- player profiles,
- fastest milestones,
- venue wording,
- fifties and hundreds,
- wickets against teams,
- tactical questions,
- team analytics.

Before documentation, the project also passed Python compilation checks:

```powershell
python -m py_compile app\analysis.py app\llm_agent.py app\main.py scripts\test_core_questions.py
```

---

## 8. Local Setup Requirement

This is a local application. The GitHub repository contains the source code, but the app cannot run fully from GitHub alone.

To run the project, a user needs:

- Python environment and dependencies,
- SQL Server,
- the `CricketAnalytics` database,
- the required IPL tables,
- Ollama installed,
- the local Ollama model downloaded,
- the Ollama server running,
- the Streamlit app running.

This design keeps the project local and avoids relying on internet APIs for answering questions.

---

## 9. Limitations

The project has some limitations:

1. The app only knows the data loaded into the local SQL Server database.
2. Current squad analysis depends on the accuracy of the `current_squads` table.
3. New players may have limited historical data.
4. Tactical suggestions are analytical recommendations, not guaranteed match predictions.
5. Some route logic could be reorganised into separate files for cleaner long-term maintenance.

---

## 10. Future Improvements

Possible future improvements include:

- adding charts for player season trends,
- improving player and team alias handling,
- adding automatic database setup scripts,
- adding more competitions beyond IPL,
- improving tactical matchup logic,
- adding more current squad metadata,
- splitting route logic into separate modules,
- adding a larger natural-language test suite.

---

## 11. Final Outcome

The project successfully demonstrates a local natural-language cricket analytics assistant.

It can answer a wide range of IPL questions using SQL, display structured results in a frontend, handle many common cricket phrasings, and provide useful player, team, venue, and tactical analysis.

The final version is stable enough for documentation, demonstration, and further polishing.
