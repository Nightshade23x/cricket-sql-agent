# Setup Guide

This guide explains how to run the IPL SQL Agent locally.

---

## Requirements

Install the following before running the project:

- Python 3.12
- SQL Server
- SQL Server Management Studio
- ODBC Driver 17 for SQL Server
- Ollama
- VS Code or another code editor

---

## Python Environment

From the project root:

```powershell
cd C:\Users\Samar\Desktop\cricket-sql-agent
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

If the virtual environment already exists, only activate it:

```powershell
cd C:\Users\Samar\Desktop\cricket-sql-agent
.\.venv\Scripts\activate
```

---

## Database

The SQL Server database used by the project is:

```text
CricketAnalytics
```

The main tables are:

- `deliveries`
- `matches`
- `current_squads`
- `batter_innings_milestones`
- `shot_events`

The `deliveries` table contains ball-by-ball IPL data.  
The `matches` table contains match-level information.  
The `current_squads` table is used for current-player tactical analysis.  
The `batter_innings_milestones` table speeds up fastest 50 and fastest 100 questions.

---

## Starting Ollama

Open a PowerShell window and run:

```powershell
$env:OLLAMA_MODELS = "G:\Ollama\models"
& "G:\MovedFromC\AppDataLocalPrograms\Ollama\ollama.exe" serve
```

Keep this window open while using the app.

---

## Starting Streamlit

Open a second PowerShell window and run:

```powershell
cd C:\Users\Samar\Desktop\cricket-sql-agent
.\.venv\Scripts\activate

python -m streamlit cache clear
python -m streamlit run app\main.py --server.port 8503 --server.address 127.0.0.1 --server.headless true
```

Open the app at:

```text
http://127.0.0.1:8503
```

---

## Running Tests

Run:

```powershell
python -m py_compile app\analysis.py app\llm_agent.py app\main.py scripts\test_core_questions.py
python scripts\test_core_questions.py
```

Expected result:

```text
ALL TESTS PASSED
```

---

## Common Issues

### Ollama is not responding

Make sure the Ollama server window is still open.

### Streamlit opens the wrong cached version

Clear Streamlit cache:

```powershell
python -m streamlit cache clear
```

Then restart the app.

### SQL query fails

Check that SQL Server is running and that the `CricketAnalytics` database exists.

### Fastest 50/100 is slow

Check that the `batter_innings_milestones` cache table exists.
