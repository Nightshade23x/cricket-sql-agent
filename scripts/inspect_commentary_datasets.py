from pathlib import Path
import pandas as pd


ROOT_FOLDER = Path(r"E:\Downloads 15 June 2026")
OUTPUT_FILE = Path("data/commentary_dataset_inspection.txt")

KEYWORDS = [
    "comment",
    "shot",
    "batter",
    "batsman",
    "striker",
    "bowler",
    "wicket",
    "dismiss",
    "runs",
    "over",
    "ball",
    "innings",
    "match",
]


def file_size_mb(path):
    return round(path.stat().st_size / (1024 * 1024), 2)


def read_csv_sample(path):
    encodings = ["utf-8", "utf-8-sig", "latin1"]

    for encoding in encodings:
        try:
            return pd.read_csv(path, nrows=5, encoding=encoding)
        except Exception:
            continue

    return None


def read_excel_sample(path):
    try:
        return pd.read_excel(path, nrows=5)
    except Exception:
        return None


def read_json_sample(path):
    try:
        return pd.read_json(path, lines=True, nrows=5)
    except Exception:
        try:
            return pd.read_json(path)
        except Exception:
            return None


def inspect_dataframe(df):
    lines = []

    lines.append("Columns:")
    for column in df.columns:
        lines.append(f"  - {column}")

    lines.append("")
    lines.append("Important-looking columns:")
    important_columns = [
        column for column in df.columns
        if any(keyword in str(column).lower() for keyword in KEYWORDS)
    ]

    if len(important_columns) == 0:
        lines.append("  None found")
    else:
        for column in important_columns:
            lines.append(f"  - {column}")

    lines.append("")
    lines.append("Sample rows:")
    lines.append(df.head(3).to_string(index=False))

    return "\n".join(lines)


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    supported_extensions = [".csv", ".xlsx", ".xls", ".json", ".jsonl"]
    files = [
        path for path in ROOT_FOLDER.rglob("*")
        if path.is_file() and path.suffix.lower() in supported_extensions
    ]

    output_lines = []
    output_lines.append(f"Root folder: {ROOT_FOLDER}")
    output_lines.append(f"Files found: {len(files)}")
    output_lines.append("=" * 100)

    for path in files:
        output_lines.append("")
        output_lines.append("=" * 100)
        output_lines.append(f"FILE: {path}")
        output_lines.append(f"SIZE: {file_size_mb(path)} MB")
        output_lines.append(f"TYPE: {path.suffix.lower()}")

        df = None

        if path.suffix.lower() == ".csv":
            df = read_csv_sample(path)

        elif path.suffix.lower() in [".xlsx", ".xls"]:
            df = read_excel_sample(path)

        elif path.suffix.lower() in [".json", ".jsonl"]:
            df = read_json_sample(path)

        if df is None:
            output_lines.append("Could not read sample.")
            continue

        output_lines.append(inspect_dataframe(df))

    OUTPUT_FILE.write_text("\n".join(output_lines), encoding="utf-8")

    print(f"Inspection complete.")
    print(f"Saved report to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()