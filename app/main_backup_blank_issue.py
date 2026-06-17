import pandas as pd
import streamlit as st
from app.llm_agent import answer_question_with_fallback


st.set_page_config(
    page_title="Cricket SQL Agent",
    page_icon="🏏",
    layout="wide",
)


EXAMPLE_QUESTION_GROUPS = {
    "Match plans": [
        "How can CSK beat GT?",
        "How can CSK beat GT at Chepauk?",
        "How can RCB beat MI at Chinnaswamy?",
        "How can MI beat KKR at Wankhede?",
    ],
    "Squad and prediction": [
        "Who will win next season?",
        "Which team has the strongest current squad?",
        "Analyse CSK squad",
        "Analyse RCB squad",
        "Analyse GT",
        "Analyse CSK",
    ],
    "Tactical matchups": [
        "Which GT bowler should bowl to Pooran?",
        "What length should Hazlewood bowl against Dhoni?",
        "What line should Rashid bowl to Maxwell?",
        "Best matchups for Bumrah",
    ],
    "Player analysis": [
        "Analyse Virat Kohli",
        "Analyse MS Dhoni",
        "How does Pooran get out?",
        "What shots does Maxwell play?",
    ],
    "Classic analytics": [
        "Top 10 run scorers",
        "Top 10 wicket takers",
        "Who has the most runs at Chepauk?",
        "Who has the most wickets at Wankhede?",
    ],
}


def set_example_question(question):
    st.session_state.question_input = question


def is_non_empty_dataframe(value):
    return isinstance(value, pd.DataFrame) and not value.empty

def should_show_table(value):
    if value is None:
        return False

    if isinstance(value, pd.DataFrame):
        return not value.empty

    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0

    return True

def display_result(title, value):
    if value is None:
        return

    if isinstance(value, pd.DataFrame):
        if value.empty:
            st.info(f"No rows returned for {title}.")
        else:
            clean_value = value.copy()

            numeric_columns = clean_value.select_dtypes(include=["float", "float64"]).columns
            clean_value[numeric_columns] = clean_value[numeric_columns].round(2)

            st.dataframe(clean_value, use_container_width=True, hide_index=True)

            long_text_columns = [
                col for col in clean_value.columns
                if col.lower() in ["reason", "why", "insight", "summary", "trophy_summary", "result_summary"]
            ]

            if long_text_columns:
                st.markdown("#### Full text details")

                for row_index, row in clean_value.iterrows():
                    label_parts = []

                    for possible_label in [
                        "display_name",
                        "player",
                        "team_a_bowler",
                        "team_a_batter",
                        "phase",
                        "section",
                        "analysis_area",
                        "team",
                    ]:
                        if possible_label in clean_value.columns:
                            label_parts.append(str(row.get(possible_label, "")))

                    label = " – ".join([part for part in label_parts if part and part != "nan"])

                    if not label:
                        label = f"Row {row_index + 1}"

                    for text_col in long_text_columns:
                        text_value = row.get(text_col, "")

                        if pd.notna(text_value) and str(text_value).strip():
                            st.markdown(f"**{label}**")
                            st.write(str(text_value))
        return

    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            st.info(f"No rows returned for {title}.")
        else:
            st.write(value)
        return

    if isinstance(value, dict):
        if len(value) == 0:
            st.info(f"No data returned for {title}.")
        else:
            st.json(value)
        return

    st.write(value)