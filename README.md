# IPL SQL Agent

A local cricket analytics assistant that answers Indian Premier League (IPL) questions by generating and running SQL queries over a local SQL Server database.

The project uses processed Cricsheet IPL data, SQL Server, a local Ollama model, and a Streamlit frontend. It is designed to answer cricket questions through structured SQL instead of relying on internet search.

**Author:** Samar Mahajan

---

## Project Overview

The IPL SQL Agent allows users to ask natural-language IPL analytics questions such as:

- Who are the top 10 run scorers in 2026?
- Who are the top 10 wicket takers for CSK in 2026?
- Who has the fastest 50 in IPL history?
- Analyse Bumrah.
- How many fifties does Kohli have against CSK?
- Who has taken the most wickets against CSK?
- How can GT beat RR at Narendra Modi Stadium?
- Best bowlers against Kohli for Delhi Capitals.

The assistant converts these questions into safe SQL queries, executes them on a local database, and displays the result in a Streamlit app.

---

## Key Features

### Player Analytics

- Batting profiles
- Bowling profiles
- Batting and bowling season trends
- Fifties and hundreds
- Venue-specific player records
- Team-specific player records
- Player-vs-team milestone queries

### Leaderboards

- Top run scorers by season
- Top wicket takers by season
- Team-wise run scorers
- Team-wise wicket takers
- Venue-wise batting and bowling leaderboards
- Fastest 50s and fastest 100s using a cached milestone table

### Team Analytics

- Most trophies
- Trophy years
- Best win percentage
- Team run scorers by season
- Team wicket takers by season

### Tactical Analysis

- Match plans
- Venue profiles
- Squad analysis
- Tactical matchups
- Current squad based bowling recommendations

### Query Robustness

The agent supports multiple phrasings for the same question. For example:

- `top 10 run scorers at Wankhede`
- `top 10 run scorers in Wankhede`
- `who has the most runs at Wankhede`
- `Wankhede top 10 run scorers`

These are routed to the same venue leaderboard logic.

---

## Tech Stack

| Component | Tool |
|---|---|
| Language | Python |
| Database | SQL Server |
| SQL access | SQLAlchemy, pyodbc |
| Data processing | pandas |
| Frontend | Streamlit |
| Local LLM | Ollama |
| Data source | Cricsheet IPL data |

---

## Project Structure

```text
cricket-sql-agent/
│
├── app/
│   ├── main.py              # Streamlit frontend
│   ├── llm.py               # Ollama/local LLM connection
│   ├── llm_agent.py         # Routing, SQL generation, fallback logic
│   ├── analysis.py          # Analysis helpers
│   └── db.py                # Database query connection helper
│
├── data/
│   └── processed/           # Processed IPL CSV files
│
├── docs/
│   ├── architecture.md
│   ├── setup_guide.md
│   ├── example_questions.md
│   ├── testing_checklist.md
│   └── limitations_future_work.md
│
├── scripts/
│   ├── test_core_questions.py
│   └── other setup/test scripts
│
├── requirements.txt
└── README.md
```

---

## Database Tables

The main database is called:

```text
CricketAnalytics
```

Main tables used by the project:

| Table | Purpose |
|---|---|
| `deliveries` | Ball-by-ball IPL data |
| `matches` | Match-level IPL data |
| `current_squads` | Current squad/player metadata |
| `batter_innings_milestones` | Cached fastest 50/100 calculations |
| `shot_events` | Shot-level event table, where available |

---

## How to Run

Open two PowerShell windows.

### 1. Start Ollama

```powershell
$env:OLLAMA_MODELS = "G:\Ollama\models"
& "G:\MovedFromC\AppDataLocalPrograms\Ollama\ollama.exe" serve
```

### 2. Start the Streamlit App

```powershell
cd C:\Users\Samar\Desktop\cricket-sql-agent
.\.venv\Scripts\activate

python -m streamlit cache clear
python -m streamlit run app\main.py --server.port 8503 --server.address 127.0.0.1 --server.headless true
```

Then open:

```text
http://127.0.0.1:8503
```

---

## Testing

Run:

```powershell
cd C:\Users\Samar\Desktop\cricket-sql-agent
.\.venv\Scripts\activate

python -m py_compile app\analysis.py app\llm_agent.py app\main.py scripts\test_core_questions.py
python scripts\test_core_questions.py
```

Expected result:

```text
ALL TESTS PASSED
```

At the latest stable point, the project regression suite had **42 passing questions**.

---

## Example Questions

See [`docs/example_questions.md`](docs/example_questions.md) for a full list of tested example prompts.

---

## Limitations

- The model is local and depends on the available Ollama model.
- The database only knows the data that has been loaded locally.
- Current squad analysis depends on the accuracy of the `current_squads` table.
- Some new players may have limited historical ball-by-ball data.
- Tactical recommendations are analytical suggestions, not guaranteed predictions.

See [`docs/limitations_future_work.md`](docs/limitations_future_work.md) for more detail.

---

## Future Improvements

- Add more current-squad metadata.
- Add more robust name alias handling.
- Add charts for player season trends.
- Add automated database setup scripts.
- Add support for more competitions beyond IPL.
- Consolidate route logic into cleaner modules.

---

## Status

The core agent is working and tested. The next stage is documentation, cleanup, and final presentation/report preparation.
