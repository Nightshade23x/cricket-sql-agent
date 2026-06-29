# Limitations and Future Work

## Limitations

### 1. Data is limited to local tables

The agent only knows the data that has been loaded into SQL Server. It does not automatically search the internet for new matches or updated squads.

### 2. Current squad accuracy depends on `current_squads`

Current-player analysis relies on the `current_squads` table. If a squad changes, the table must be updated.

### 3. Some new players have small samples

New players may not have enough ball-by-ball history. The app can still show them in current squad outputs, but direct matchup results may have limited data.

### 4. Tactical suggestions are analytical, not predictive

Match plans and bowling recommendations are based on historical data, current squads, and rule-based analysis. They should be treated as cricket analysis, not guaranteed outcomes.

### 5. Route logic can be modularised further

Many routes currently live in `app/llm_agent.py`. This is functional, but a cleaner future design would split routes into separate files.

---

## Future Work

### 1. Modular route system

Split `llm_agent.py` into separate modules:

```text
app/routes/player_routes.py
app/routes/team_routes.py
app/routes/venue_routes.py
app/routes/tactical_routes.py
app/routes/milestone_routes.py
```

### 2. Better alias resolver

Build a central player and team alias table to handle:

- Spelling variations
- Initials
- Full names
- Short names
- Retired players
- Current squad names

### 3. Charts in the frontend

Add visual charts for:

- Player season trends
- Strike rate by season
- Economy by season
- Venue scoring patterns
- Phase-wise batting/bowling performance

### 4. Automated database setup

Create scripts to:

- Create the database
- Create all tables
- Load processed CSV files
- Build indexes
- Build cache tables

### 5. More tactical depth

Improve tactical outputs with:

- Batter-vs-bowler matchup history
- Phase-specific bowling recommendations
- Venue-specific par scores
- Left/right-hand matchup logic
- Bowling type weaknesses

### 6. Support other competitions

Extend beyond IPL to:

- International T20s
- ODI cricket
- Test cricket
- Other franchise leagues

### 7. Better evaluation

Create a larger benchmark of natural-language questions and expected SQL outputs to measure routing quality over time.
