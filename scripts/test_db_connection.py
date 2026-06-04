from app.db import run_query  # Imports our function for running SQL queries


def main():
    count_query = """
    SELECT COUNT(*) AS total_matches
    FROM matches;
    """

    result = run_query(count_query)

    print("Match count result:")
    print(result)

    top_batters_query = """
    SELECT TOP 10
        striker AS batter,
        SUM(runs_off_bat) AS total_runs
    FROM deliveries
    GROUP BY striker
    ORDER BY total_runs DESC;
    """

    top_batters = run_query(top_batters_query)

    print("\nTop 10 run scorers:")
    print(top_batters)


if __name__ == "__main__":
    main()