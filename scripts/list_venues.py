from app.db import run_query  # Imports our database query function


def main():  # Main function where the script starts
    query = """
    SELECT DISTINCT venue
    FROM matches
    ORDER BY venue;
    """  # SQL query to get all unique venue names
    venues = run_query(query)  # Runs the query and stores the result
    print(venues)  
    venues.to_csv("reports/venues.csv", index=False)  # Saves the venue list to a CSV file

if __name__ == "__main__":  
    main() 