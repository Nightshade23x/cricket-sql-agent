from urllib.parse import quote_plus  # Helps format the SQL Server connection string
import pandas as pd 
from sqlalchemy import create_engine, text  # Used to connect to SQL Server and run SQL


def main():
    # SQL Server connection settings
    server = r"localhost\SQLEXPRESS"
    database = "CricketAnalytics"

    # Connection string for Windows Authentication
    connection_string = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

    # Convert connection string into a format SQLAlchemy understands
    connection_url = quote_plus(connection_string)

    # Create database connection engine
    engine = create_engine(
        f"mssql+pyodbc:///?odbc_connect={connection_url}",
        fast_executemany=True
    )

    print("Reading processed CSV files...")

   
    matches = pd.read_csv("data/processed/matches.csv", low_memory=False)
    deliveries = pd.read_csv("data/processed/deliveries.csv", low_memory=False)
    # Make sure season is treated as text
    matches["season"] = matches["season"].astype(str)
    deliveries["season"] = deliveries["season"].astype(str)
    print("Matches shape:", matches.shape)
    print("Deliveries shape:", deliveries.shape)
    print("Clearing existing SQL tables...")

    # Clear old data before loading new data
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM deliveries;"))
        connection.execute(text("DELETE FROM matches;"))
        connection.execute(text("DBCC CHECKIDENT ('deliveries', RESEED, 0);"))
    print("Loading matches table...")

    # Load matches first because deliveries depends on matches
    matches.to_sql(
        "matches",
        con=engine,
        if_exists="append",
        index=False,
        chunksize=1000
    )
    print("Loading deliveries table...")

    # Load deliveries
    deliveries.to_sql(
        "deliveries",
        con=engine,
        if_exists="append",
        index=False,
        chunksize=5000
    )
    print("Data loaded successfully into SQL Server.")


if __name__ == "__main__":
    main()