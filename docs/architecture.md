# Architecture

The IPL SQL Agent has five main layers:

```text
User question
    ↓
Streamlit frontend
    ↓
Question router / LLM agent
    ↓
SQL Server database
    ↓
Formatted answer and tables
```

---

## 1. Streamlit Frontend

File:

```text
app/main.py
```

The frontend accepts user questions, sends them to the agent, and displays:

- Answer paragraph
- Main result table
- Extra analysis tabs
- SQL query used
- Similar questions

The UI is intentionally simple so the focus remains on cricket analytics.

---

## 2. Local LLM Connection

File:

```text
app/llm.py
```

This file handles communication with the local Ollama model.

The project is designed to work locally, so it does not need internet access for answering questions after the data and model are installed.

---

## 3. Agent and Routing Logic

File:

```text
app/llm_agent.py
```

This is the core of the project.

It handles:

- Recognising question type
- Routing common cricket questions to reliable SQL
- Handling aliases and alternate phrasings
- Preventing unsafe SQL
- Falling back to the local LLM when needed
- Formatting outputs for the frontend

Many high-value questions use direct deterministic routes rather than relying only on the LLM. This makes the project more stable and accurate.

---

## 4. Database Layer

File:

```text
app/db.py
```

This layer connects Python to SQL Server and runs the SQL queries.

The database is local and uses the `CricketAnalytics` SQL Server database.

---

## 5. Data Tables

### deliveries

Ball-by-ball IPL table.

Important columns include:

- `match_id`
- `season`
- `venue`
- `innings`
- `ball`
- `batting_team`
- `bowling_team`
- `striker`
- `bowler`
- `runs_off_bat`
- `extras`
- `wicket_type`
- `player_dismissed`

### matches

Match-level table.

Important columns include:

- `match_id`
- `season`
- `start_date`
- `venue`
- `city`
- `winner`
- `toss_winner`
- `toss_decision`
- `player_of_match`

### current_squads

Current squad metadata.

Used for:

- Squad analysis
- Tactical matchups
- Current-player bowling recommendations

### batter_innings_milestones

Cached table for fast milestone queries.

Used for:

- Fastest 50
- Fastest 100

---

## Routing Strategy

The project uses a hybrid strategy:

### 1. Direct routes

Used for common questions where accuracy matters.

Examples:

- Top run scorers
- Top wicket takers
- Fastest 50
- Fastest 100
- Player profiles
- Team trophies
- Win percentage
- Fifties/hundreds against teams
- Wickets against teams

### 2. Local LLM fallback

Used when the question is not covered by a direct route.

### 3. Wording normalisation

Some questions are rewritten internally before routing.

Example:

```text
top 10 run scorers in Wankhede
```

is treated like:

```text
top 10 run scorers at Wankhede
```

This improves usability because users do not need to phrase questions exactly one way.

---

## Why SQL?

SQL is suitable for this project because cricket scorecard data is structured.

The benefits are:

- Transparent results
- Reproducible answers
- Easier debugging
- Fast aggregation
- Clear link between question and output

---

## Current Design Tradeoff

The project currently prioritises working routes and reliability. Some route logic is appended in `llm_agent.py`, so a future improvement would be to split routes into separate modules such as:

```text
app/routes/player_routes.py
app/routes/team_routes.py
app/routes/venue_routes.py
app/routes/tactical_routes.py
```
