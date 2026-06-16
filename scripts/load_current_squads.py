from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

import pandas as pd
from sqlalchemy import text

from app.db import get_engine


CSV_PATH = PROJECT_ROOT / "data" / "current_squads_2026.csv"
TABLE_NAME = "current_squads"


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Could not find {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)

    required_columns = [
        "season",
        "team_code",
        "team_name",
        "display_name",
        "cricsheet_name",
        "role",
        "batting_style",
        "bowling_style",
        "bowling_arm",
        "is_overseas",
        "is_active",
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]
    

    if missing_columns:
        raise ValueError(f"Missing columns in squad CSV: {missing_columns}")
    df = df[required_columns].copy()
    df["season"] = df["season"].astype(int)
    df["is_overseas"] = df["is_overseas"].fillna(0).astype(int)
    df["is_active"] = df["is_active"].fillna(1).astype(int)

    text_columns = [
        "team_code",
        "team_name",
        "display_name",
        "cricsheet_name",
        "role",
        "batting_style",
        "bowling_style",
        "bowling_arm",
    ]

    for col in text_columns:
        df[col] = df[col].fillna("").astype(str).str.strip()

    engine = get_engine()

    print(f"Loading {len(df)} squad rows into dbo.{TABLE_NAME}...")

    df.to_sql(
        TABLE_NAME,
        con=engine,
        schema="dbo",
        if_exists="replace",
        index=False,
        chunksize=1000,
    )

    with engine.begin() as conn:
        conn.execute(text("""
        ALTER TABLE dbo.current_squads
        ALTER COLUMN team_code NVARCHAR(20);
        """))

        conn.execute(text("""
        ALTER TABLE dbo.current_squads
        ALTER COLUMN team_name NVARCHAR(255);
        """))

        conn.execute(text("""
        ALTER TABLE dbo.current_squads
        ALTER COLUMN display_name NVARCHAR(255);
        """))

        conn.execute(text("""
        ALTER TABLE dbo.current_squads
        ALTER COLUMN cricsheet_name NVARCHAR(255);
        """))

        conn.execute(text("""
        ALTER TABLE dbo.current_squads
        ALTER COLUMN role NVARCHAR(100);
        """))

        conn.execute(text("""
        ALTER TABLE dbo.current_squads
        ALTER COLUMN batting_style NVARCHAR(100);
        """))

        conn.execute(text("""
        ALTER TABLE dbo.current_squads
        ALTER COLUMN bowling_style NVARCHAR(100);
        """))

        conn.execute(text("""
        ALTER TABLE dbo.current_squads
        ALTER COLUMN bowling_arm NVARCHAR(50);
        """))

        conn.execute(text("""
        CREATE INDEX idx_current_squads_team
        ON dbo.current_squads(team_code, team_name);
        """))

        conn.execute(text("""
        CREATE INDEX idx_current_squads_player
        ON dbo.current_squads(cricsheet_name);
        """))

        conn.execute(text("""
        CREATE INDEX idx_current_squads_active
        ON dbo.current_squads(is_active);
        """))

    print("Current squads table loaded successfully.")


if __name__ == "__main__":
    main()