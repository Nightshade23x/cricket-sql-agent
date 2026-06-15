from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

import pandas as pd
from sqlalchemy import text

from app.db import get_engine

engine = get_engine()



SOURCE_FILE = Path(r"E:\Downloads 15 June 2026\ultimate ball by ball\ball_by_ball_data.csv")

TABLE_NAME = "shot_events"

USE_COLUMNS = [
    "match_id",
    "season",
    "start_date",
    "venue",
    "innings",
    "ball",
    "batting_team",
    "bowling_team",
    "striker",
    "non_striker",
    "bowler",
    "ball_length",
    "ball_line",
    "shot_played",
    "shot_direction",
    "runs_off_bat",
    "extras",
    "wides",
    "noballs",
    "wicket_type",
    "player_dismissed",
    "wicket",
    "gender",
    "event",
    "format",
    "type",
    "winner",
    "full name_striker",
    "country_striker",
    "batting style_striker",
    "playing role_striker",
    "full name_bowler",
    "country_bowler",
    "bowling style_bowler",
    "playing role_bowler",
]

RENAME_COLUMNS = {
    "full name_striker": "full_name_striker",
    "country_striker": "country_striker",
    "batting style_striker": "batting_style_striker",
    "playing role_striker": "playing_role_striker",
    "full name_bowler": "full_name_bowler",
    "country_bowler": "country_bowler",
    "bowling style_bowler": "bowling_style_bowler",
    "playing role_bowler": "playing_role_bowler",
}


def clean_chunk(chunk):
    chunk = chunk.rename(columns=RENAME_COLUMNS)

    # Keep IPL only
    chunk = chunk[
        chunk["event"].astype(str).str.lower().eq("indian premier league")
    ].copy()

    # Optional: keep men's IPL only
    if "gender" in chunk.columns:
        chunk = chunk[
            chunk["gender"].astype(str).str.lower().eq("male")
        ].copy()

    numeric_columns = [
        "match_id",
        "innings",
        "ball",
        "runs_off_bat",
        "extras",
        "wides",
        "noballs",
        "wicket",
    ]

    for column in numeric_columns:
        if column in chunk.columns:
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce")

    if "start_date" in chunk.columns:
        chunk["start_date"] = pd.to_datetime(chunk["start_date"], errors="coerce")

    return chunk


def main():
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"Could not find file: {SOURCE_FILE}")

    print(f"Loading from: {SOURCE_FILE}")
    print("This may take a few minutes because the source file is large.")

    total_inserted = 0
    first_write = True

    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME};"))

    chunk_reader = pd.read_csv(
        SOURCE_FILE,
        usecols=USE_COLUMNS,
        chunksize=100_000,
        low_memory=False,
    )

    for chunk_number, chunk in enumerate(chunk_reader, start=1):
        cleaned_chunk = clean_chunk(chunk)

        if cleaned_chunk.empty:
            print(f"Chunk {chunk_number}: no IPL rows")
            continue

        if_exists_mode = "replace" if first_write else "append"

        cleaned_chunk.to_sql(
            TABLE_NAME,
            con=engine,
            if_exists=if_exists_mode,
            index=False,
            chunksize=5_000,
        )

        first_write = False
        total_inserted += len(cleaned_chunk)

        print(
            f"Chunk {chunk_number}: inserted {len(cleaned_chunk)} rows "
            f"(total inserted: {total_inserted})"
        )

    if total_inserted == 0:
        print("No IPL rows were inserted. Check the event/type columns.")
        return

    print("Creating indexes...")

    with engine.begin() as connection:
        connection.execute(text(f"CREATE INDEX IX_{TABLE_NAME}_match ON {TABLE_NAME}(match_id);"))
        connection.execute(text(f"CREATE INDEX IX_{TABLE_NAME}_striker ON {TABLE_NAME}(striker);"))
        connection.execute(text(f"CREATE INDEX IX_{TABLE_NAME}_bowler ON {TABLE_NAME}(bowler);"))
        connection.execute(text(f"CREATE INDEX IX_{TABLE_NAME}_shot ON {TABLE_NAME}(shot_played);"))
        connection.execute(text(f"CREATE INDEX IX_{TABLE_NAME}_dismissed ON {TABLE_NAME}(player_dismissed);"))

    print("Done.")
    print(f"Total rows inserted into {TABLE_NAME}: {total_inserted}")


if __name__ == "__main__":
    main()