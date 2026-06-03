import json  
from pathlib import Path  


def main():  
    output_folder = Path("data/training")  
    output_folder.mkdir(parents=True, exist_ok=True)  # Creates the folder if it does not already exist
    examples = [  # List of natural language question and SQL examples
        {
            "id": 1,
            "category": "basic_database_check",
            "question": "How many IPL matches are in the database?",
            "sql": """
SELECT COUNT(*) AS total_matches
FROM matches;
""".strip()
        },
        {
            "id": 2,
            "category": "basic_database_check",
            "question": "How many ball-by-ball deliveries are in the database?",
            "sql": """
SELECT COUNT(*) AS total_deliveries
FROM deliveries;
""".strip()
        },
        {
            "id": 3,
            "category": "season_analysis",
            "question": "How many matches were played in each IPL season?",
            "sql": """
SELECT
    season,
    COUNT(*) AS total_matches
FROM matches
GROUP BY season
ORDER BY season;
""".strip()
        },
        {
            "id": 4,
            "category": "batting",
            "question": "Who are the top 10 run scorers in the IPL dataset?",
            "sql": """
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS total_runs
FROM deliveries
GROUP BY striker
ORDER BY total_runs DESC;
""".strip()
        },
        {
            "id": 5,
            "category": "batting",
            "question": "Which batters have the best strike rate with at least 300 balls faced?",
            "sql": """
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
""".strip()
        },
        {
            "id": 6,
            "category": "bowling",
            "question": "Who are the top 10 wicket takers in the IPL dataset?",
            "sql": """
SELECT TOP 10
    bowler,
    COUNT(*) AS wickets
FROM deliveries
WHERE wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY bowler
ORDER BY wickets DESC;
""".strip()
        },
        {
            "id": 7,
            "category": "bowling",
            "question": "Which bowlers have the best economy rate with at least 300 legal balls bowled?",
            "sql": """
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
""".strip()
        },
        {
            "id": 8,
            "category": "death_overs",
            "question": "Who scored the most runs in death overs?",
            "sql": """
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS death_overs_runs
FROM deliveries
WHERE FLOOR(ball) BETWEEN 15 AND 19
GROUP BY striker
ORDER BY death_overs_runs DESC;
""".strip()
        },
        {
            "id": 9,
            "category": "death_overs",
            "question": "Which batters have the best death overs strike rate with at least 100 balls faced?",
            "sql": """
SELECT TOP 10
    striker AS batter,
    SUM(runs_off_bat) AS runs,
    SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) AS balls_faced,
    ROUND(
        SUM(runs_off_bat) * 100.0 /
        NULLIF(SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END), 0),
        2
    ) AS death_overs_strike_rate
FROM deliveries
WHERE FLOOR(ball) BETWEEN 15 AND 19
GROUP BY striker
HAVING SUM(CASE WHEN wides IS NULL AND noballs IS NULL THEN 1 ELSE 0 END) >= 100
ORDER BY death_overs_strike_rate DESC;
""".strip()
        },
        {
            "id": 10,
            "category": "powerplay",
            "question": "Who has taken the most wickets in the powerplay?",
            "sql": """
SELECT TOP 10
    bowler,
    COUNT(*) AS powerplay_wickets
FROM deliveries
WHERE FLOOR(ball) BETWEEN 0 AND 5
  AND wicket_type IS NOT NULL
  AND wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
GROUP BY bowler
ORDER BY powerplay_wickets DESC;
""".strip()
        },
        {
            "id": 11,
            "category": "team_analysis",
            "question": "Which teams have the most wins while chasing?",
            "sql": """
SELECT
    batting_team AS chasing_team,
    COUNT(DISTINCT d.match_id) AS chasing_wins
FROM deliveries d
JOIN matches m
    ON d.match_id = m.match_id
WHERE d.innings = 2
  AND d.batting_team = m.winner
GROUP BY batting_team
ORDER BY chasing_wins DESC;
""".strip()
        },
        {
            "id": 12,
            "category": "venue_analysis",
            "question": "Which venues have the highest average first innings score?",
            "sql": """
SELECT TOP 10
    venue,
    ROUND(AVG(total_score * 1.0), 2) AS average_first_innings_score,
    COUNT(*) AS innings_count
FROM (
    SELECT
        match_id,
        venue,
        SUM(runs_off_bat + extras) AS total_score
    FROM deliveries
    WHERE innings = 1
    GROUP BY match_id, venue
) AS first_innings_scores
GROUP BY venue
HAVING COUNT(*) >= 10
ORDER BY average_first_innings_score DESC;
""".strip()
        }
    ]

    output_file = output_folder / "question_sql_examples.json"  

    with open(output_file, "w", encoding="utf-8") as file:  # Opens the file for writing
        json.dump(examples, file, indent=4)  # Saves the examples in a readable JSON format

    print("Question bank created successfully.")  # Confirms the script worked
    print("Total examples:", len(examples))  # Prints how many examples were saved
    print("Saved to:", output_file)  # Prints where the file was saved


if __name__ == "__main__":  
    main()  