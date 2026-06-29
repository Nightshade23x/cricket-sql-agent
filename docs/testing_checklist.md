# Testing Checklist

Use this checklist before committing or presenting the project.

---

## 1. Compile Check

```powershell
python -m py_compile app\analysis.py app\llm_agent.py app\main.py scripts\test_core_questions.py
```

This checks for Python syntax errors.

---

## 2. Regression Tests

```powershell
python scripts\test_core_questions.py
```

Expected:

```text
ALL TESTS PASSED
```

Latest stable run:

```text
42 questions passed
```

---

## 3. Manual UI Smoke Test

Start Ollama and Streamlit, then test these questions in the browser.

### Basic Leaderboards

```text
top 10 run scorers in 2026
top 10 wicket takers in 2026
top 10 run scorers for CSK in 2026
top 10 wicket takers for CSK in 2026
```

### Venue Wording

```text
top 10 run scorers at Wankhede
top 10 run scorers in Wankhede
who has the most runs at Wankhede
who has the most runs in Wankhede
```

### Player Profiles

```text
analyse Bumrah
analyse Kohli
analyse Narine
```

Check that profile tabs include:

- Batting summary
- Bowling summary
- Batting Season Trend
- Bowling Season Trend

### Fifties and Hundreds

```text
how many fifties does Kohli have against CSK
how many hundreds does Kohli have against CSK
```

### Wickets Against Team

```text
who has taken the most wickets against CSK
```

### Tactical Questions

```text
how can GT beat RR at Narendra Modi Stadium
best bowlers against Kohli for Delhi Capitals
best bowlers against Kohli for dc
```

For `dc`, the agent should ask for clarification.

---

## 4. Performance Check

Fastest 50 and fastest 100 should be quick.

```powershell
Measure-Command { python -c "from app.llm_agent import answer_question_with_fallback; r=answer_question_with_fallback('who has the fastest 50 in IPL history'); print(r.get('analysis_paragraph'))" }

Measure-Command { python -c "from app.llm_agent import answer_question_with_fallback; r=answer_question_with_fallback('who has the fastest 100 in IPL history'); print(r.get('analysis_paragraph'))" }
```

---

## 5. Git Check

Before committing:

```powershell
git status
```

Do not commit:

```text
patch_*.py
backups/
scripts/*.sql
```

Commit only source and documentation files.
