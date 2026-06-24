from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm_agent import answer_question_with_fallback


TESTS = [

    {
        "question": "tell me about Chepauk stats",
        "expected_columns": ["venue_profile", "matches", "avg_first_innings_score"],
    },
    {
        "question": "tell me about Eden Gardens stats",
        "expected_columns": ["venue_profile", "matches", "avg_first_innings_score"],
    },

    {
        "question": "analyse Suresh Raina",
        "expected_columns": ["resolved_player"],
    },
    {
        "question": "analyse Kohli",
        "expected_columns": ["resolved_player"],
    },
    {
        "question": "compare CSK and MI",
        "expected_columns": ["team_code", "trophies", "playoff_seasons"],
    },
    {
        "question": "which players are key for CSK",
        "expected_columns": ["team_code", "player", "key_player_score"],
    },
    {
        "question": "how can CSK win next year",
        "expected_columns": ["priority", "need"],
    },
    {
        "question": "best current XI for CSK",
        "expected_columns": ["xi_no", "player", "suggested_role"],
    },
    {
        "question": "what type of players should CSK buy",
        "expected_columns": ["priority", "target_profile"],
    },
    {
        "question": "how can CSK beat GT at Chepauk",
        "expected_columns": ["section", "action"],
    },
    {
        "question": "who has the most wickets in powerplay",
        "expected_columns": ["bowler", "wickets"],
    },
    {
        "question": "who has bowled the most dot balls in death overs",
        "expected_columns": ["bowler", "dot_balls"],
    },
    {
        "question": "who are the top 10 run scorers in IPL",
        "expected_columns": ["batter", "matches", "innings", "runs"],
    },
    {
        "question": "who are the top 10 wicket takers in IPL",
        "expected_columns": ["bowler", "matches", "innings", "overs_bowled", "wickets"],
    },
]


def get_columns(result):
    table = result.get("result") if isinstance(result, dict) else None

    if hasattr(table, "columns"):
        return {str(column).lower() for column in table.columns}

    return set()


def main():
    failures = []

    for item in TESTS:
        question = item["question"]
        expected = {column.lower() for column in item.get("expected_columns", [])}

        try:
            result = answer_question_with_fallback(question)
        except Exception as error:
            failures.append((question, f"crashed: {error}"))
            continue

        if not isinstance(result, dict):
            failures.append((question, "result is not a dict"))
            continue

        paragraph = result.get("analysis_paragraph") or result.get("paragraph") or ""

        if not str(paragraph).strip():
            failures.append((question, "missing paragraph"))

        table = result.get("result")

        if not hasattr(table, "empty") or table.empty:
            failures.append((question, "empty or missing result table"))
            continue

        actual_columns = get_columns(result)
        missing = expected - actual_columns

        if missing:
            failures.append((question, f"missing columns: {sorted(missing)}"))

    if failures:
        print("FAILED TESTS")
        for question, reason in failures:
            print(f"- {question}: {reason}")
        raise SystemExit(1)

    print(f"All {len(TESTS)} core IPL SQL Agent tests passed.")


if __name__ == "__main__":
    main()
