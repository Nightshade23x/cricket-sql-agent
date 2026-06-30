from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm_agent import answer_question_with_fallback


TESTS = [

    {
        "question": "who won orange cap in 2008",
        "expected_columns": ["season", "batter", "runs"],
    },
    {
        "question": "who won purple cap in 2010",
        "expected_columns": ["season", "bowler", "wickets"],
    },
    {
        "question": "who scored the most runs in a season",
        "expected_columns": ["season", "batter", "runs"],
    },
    {
        "question": "who took the most wickets in a season",
        "expected_columns": ["season", "bowler", "wickets"],
    },
    {
        "question": "top 10 run scorers in 2010",
        "expected_columns": ["season", "batter", "runs"],
    },
    {
        "question": "top 10 wicket takers in 2010",
        "expected_columns": ["season", "bowler", "wickets"],
    },


    {
        "question": "best strike rate at New Chandigarh min 50 balls faced",
        "expected_columns": ["batter", "team", "balls", "strike_rate"],
    },
    {
        "question": "best economy rate at New Chandigarh min 50 balls bowled",
        "expected_columns": ["bowler", "team", "legal_balls", "economy"],
    },


    {
        "question": "best strike rate in ipl min 500 balls faced",
        "expected_columns": ["batter", "team", "balls", "strike_rate"],
    },
    {
        "question": "who has the best average at chepauk min 5 matches played",
        "expected_columns": ["batter", "team", "matches", "batting_average"],
    },
    {
        "question": "best economy rate in ipl min 700 balls bowled",
        "expected_columns": ["bowler", "team", "legal_balls", "economy"],
    },
    {
        "question": "best strike rate for csk min 300 balls",
        "expected_columns": ["batter", "team", "balls", "strike_rate"],
    },
    {
        "question": "best economy rate at chepauk min 300 balls bowled",
        "expected_columns": ["bowler", "team", "legal_balls", "economy"],
    },


    {
        "question": "best bowlers against Dhoni at Chepauk",
        "expected_columns": ["bowler", "team", "balls", "dismissals", "batter_sr"],
    },


    {
        "question": "top 10 run scorers in wankhede",
        "expected_columns": ["batter", "team", "runs", "batting_average", "strike_rate"],
    },
    {
        "question": "who has the most runs in wankhede",
        "expected_columns": ["batter", "team", "runs", "batting_average", "strike_rate"],
    },
    {
        "question": "top 10 wicket takers in wankhede",
        "expected_columns": ["bowler", "team", "innings", "wickets", "economy"],
    },
    {
        "question": "who has the most wickets in wankhede",
        "expected_columns": ["bowler", "team", "innings", "wickets", "economy"],
    },
    {
        "question": "wankhede top 10 run scorers",
        "expected_columns": ["batter", "team", "runs", "batting_average", "strike_rate"],
    },


    {
        "question": "how many fifties does Kohli have against CSK",
        "expected_columns": ["player", "fifties", "hundreds"],
    },
    {
        "question": "how many hundreds does Kohli have against CSK",
        "expected_columns": ["player", "fifties", "hundreds"],
    },
    {
        "question": "who has taken the most wickets against csk",
        "expected_columns": ["bowler", "team", "wickets", "economy"],
    },


    {
        "question": "analyse Bumrah",
        "expected_columns": ["resolved_player", "player", "wickets", "economy"],
    },


    {
        "question": "best bowlers against Kohli for dc",
        "expected_columns": ["issue", "action"],
    },
    {
        "question": "best bowlers against Kohli for Delhi Capitals",
        "expected_columns": ["bowler", "team", "balls", "dismissals", "batter_sr"],
    },


    {
        "question": "who are top 10 run scorers in 2026",
        "expected_columns": ["batter", "team", "runs", "batting_average", "strike_rate"],
    },
    {
        "question": "top 10 wicket takers in 2026",
        "expected_columns": ["bowler", "team", "wickets", "economy"],
    },


    {
        "question": "who are top 10 run scoers in 2026",
        "expected_columns": ["batter", "runs", "batting_average", "strike_rate"],
    },
    {
        "question": "top 10 wicket takers in 2026",
        "expected_columns": ["bowler", "wickets", "economy"],
    },
    {
        "question": "top 10 wicket takers for csk in 2026",
        "expected_columns": ["bowler", "wickets", "economy"],
    },
    {
        "question": "top 10 run scorers at Wankhede",
        "expected_columns": ["batter", "runs", "batting_average", "strike_rate"],
    },
    {
        "question": "top 10 wicket takers at Wankhede",
        "expected_columns": ["bowler", "wickets", "economy"],
    },


    {
        "question": "who has won the most trophies",
        "expected_columns": ["team", "trophies", "years_won"],
    },
    {
        "question": "which team has the best win percentage",
        "expected_columns": ["team", "matches", "wins", "win_percentage"],
    },
    {
        "question": "who are top 10 run scorers for csk in 2026",
        "expected_columns": ["batter", "runs", "strike_rate"],
    },


    {
        "question": "how many fifties does Sooryavanshi have",
        "expected_columns": ["player", "fifties", "hundreds"],
    },
    {
        "question": "analyze Bumrah",
        "expected_columns": ["player", "wickets", "economy"],
    },


    {
        "question": "who has the fastest 100 in IPL history",
        "expected_columns": ["batter", "balls_to_hundred", "innings_runs"],
    },
    {
        "question": "which kkr bowler should bowl to gaikwad in middle overs",
        "expected_columns": ["section", "action"],
    },


    {
        "question": "who has the fastest 50 in IPL history",
        "expected_columns": ["batter", "balls_to_fifty", "innings_runs"],
    },
    {
        "question": "who has the fastest 50 for MI",
        "expected_columns": ["batter", "balls_to_fifty", "batting_team"],
    },
    {
        "question": "how can KKR bowl to Gaikwad in middle overs",
        "expected_columns": ["section", "action"],
    },


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
