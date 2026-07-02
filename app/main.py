import re

import pandas as pd
import streamlit as st

from app.llm_agent import answer_question_with_fallback


APP_TITLE = "IPL SQL Agent"
APP_SUBTITLE = "Ask IPL analytics questions using your local SQL Server database."

EXAMPLE_QUESTION_GROUPS = {'Classic analytics': ['who are the top 10 run scorers in IPL',
                       'who are the top 10 wicket takers in IPL',
                       'who has the fastest 50 in IPL history',
                       'which team has the most trophies'],
 'Player profiles': ['analyse Kohli',
                     'analyse Bumrah',
                     'analyse Suryavanshi',
                     'analyse Rohit Sharma'],
 'Match plans': ['how can CSK beat RCB at Chinnaswamy',
                 'how can RCB beat PBKS',
                 'how can KKR beat GT at Eden Gardens',
                 'how can SRH beat RR at Uppal'],
 'Venue profiles': ['tell me about Eden Gardens',
                    'tell me about Chepauk',
                    'tell me about Wankhede',
                    'tell me about Chinnaswamy'],
 'Squad analysis': ['analyse CSK squad',
                    'analyse RCB squad',
                    'analyse Delhi Capitals squad',
                    'which team has the best win percentage'],
 'Tactical matchups': ['how should Bumrah bowl to Kohli',
                       'what length should Rashid bowl to Suryavanshi',
                       'best bowlers against Kohli for Delhi Capitals',
                       'best bowlers against KL Rahul at Arun Jaitley'],
 'Rate and filter leaderboards': ['best strike rate in IPL min 500 balls faced',
                                  'who has the best average at Chepauk min 5 matches played',
                                  'best economy rate in IPL min 700 balls bowled',
                                  'best economy rate at Wankhede min 300 balls bowled'],
 'Filtered player records': ['how many fifties does Kohli have against CSK',
                             'how many hundreds does JC Buttler have at Wankhede',
                             'who has taken the most wickets against CSK',
                             'best bowlers against Rohit Sharma at Chepauk']}


HIDDEN_COLUMNS = {
    "watch_score",
    "rank_score",
    "priority_score",
    "is_priority_player",
    "matchup_score",
    "sort_score",
    "raw_score",

    "cricsheet_name",
    "cricsheet name",
    "is_overseas",
    "is overseas",
    "is_active",
    "is active",
    "full_name_striker",
    "full name striker",
    "full_name_bowler",
    "full name bowler",}

def setup_page():
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🏏",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1280px;
            padding-top: 2rem;
            padding-bottom: 2.5rem;
        }

        .main-title {
            text-align: center;
            font-size: 3.2rem;
            font-weight: 850;
            letter-spacing: -0.04em;
            margin-bottom: 0.25rem;
        }

        .main-subtitle {
            text-align: center;
            color: rgba(250, 250, 250, 0.62);
            font-size: 1.05rem;
            margin-bottom: 2rem;
        }

        .hero-card {
            border: 1px solid rgba(250, 250, 250, 0.10);
            border-radius: 22px;
            padding: 1.25rem 1.35rem;
            background:
                radial-gradient(circle at top left, rgba(255, 184, 77, 0.09), transparent 35%),
                linear-gradient(135deg, rgba(255, 255, 255, 0.045), rgba(255, 255, 255, 0.015));
            margin-bottom: 1.25rem;
        }

        .section-title {
            font-size: 1.45rem;
            font-weight: 780;
            margin: 1.15rem 0 0.65rem 0;
        }

        .small-muted {
            color: rgba(250, 250, 250, 0.60);
            font-size: 0.92rem;
        }

        .result-card {
            border: 1px solid rgba(250, 250, 250, 0.10);
            border-radius: 18px;
            padding: 1.1rem 1.2rem;
            background: rgba(255, 255, 255, 0.025);
            margin: 0.9rem 0;
        }

        .answer-text {
            font-size: 1.06rem;
            line-height: 1.65;
        }

        .footer {
            text-align: center;
            color: rgba(250, 250, 250, 0.50);
            font-size: 0.92rem;
            margin-top: 3rem;
            padding-top: 1.5rem;
            border-top: 1px solid rgba(250, 250, 250, 0.08);
        }

        div[data-testid="stSidebar"] button {
            width: 100%;
            text-align: left;
            justify-content: flex-start;
            white-space: normal;
            min-height: 2.6rem;
            border-radius: 12px;
        }

        div[data-testid="stButton"] button {
            border-radius: 12px;
        }

        div[data-testid="stDataFrame"] {
            border-radius: 14px;
            overflow: hidden;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.45rem;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 999px;
            padding: 0.45rem 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def select_question(question):
    st.session_state.question_input = question
    st.session_state.run_requested = True


def normalise_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def format_table_name(name):
    text = str(name or "").strip()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)

    known = {
        "h2h": "Head To Head",
        "head to head": "Head To Head",
        "recent h2h": "Recent Head To Head",
        "recent head to head": "Recent Head To Head",
        "bowler matchups": "Bowler Matchups",
        "bowling phase matchups": "Bowling Phase Matchups",
        "opponent current key batters": "Opponent Current Key Batters",
    }

    return known.get(text.lower(), text.title())


def clean_dataframe(df):
    if df is None:
        return None

    if not isinstance(df, pd.DataFrame):
        return df

    if df.empty:
        return df


    display_df = df.copy()

    if "#" not in display_df.columns:
        display_df.insert(0, "#", range(1, len(display_df) + 1))

    columns_to_drop = [
        column
        for column in display_df.columns
        if str(column).lower() in HIDDEN_COLUMNS
    ]

    if columns_to_drop:
        display_df = display_df.drop(columns=columns_to_drop)

    display_df = display_df.rename(
        columns={
            column: str(column).replace("_", " ").title()
            for column in display_df.columns
        }
    )

    return display_df


def render_details(df):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return

    detail_col = None

    for candidate in ["battle_note", "Battle Note", "summary", "Summary", "analysis", "Analysis", "note", "Note"]:
        if candidate in df.columns:
            detail_col = candidate
            break

    if not detail_col:
        return

    title_columns = [
        "bowler",
        "Bowler",
        "batter",
        "Batter",
        "team_a_bowler",
        "Team A Bowler",
        "team_b_batter",
        "Team B Batter",
        "display_name",
        "Display Name",
        "player",
        "Player",
    ]

    st.markdown("**Details**")

    for index, row in df.head(8).iterrows():
        pieces = []

        for column in title_columns:
            if column in df.columns and pd.notna(row.get(column)):
                pieces.append(str(row.get(column)))

        title = " - ".join(pieces) if pieces else f"Detail {index + 1}"

        with st.expander(title):
            st.markdown(_ipl_frontend_clean_text(row.get(detail_col)))


# IPL SQL Agent clean Streamlit dataframe display START

def _clean_dataframe_for_streamlit_display(df):
    """Remove schema-compatibility duplicate columns before UI rendering."""
    if df is None or not hasattr(df, "columns"):
        return df

    try:
        import re
        import pandas as pd

        df = df.copy()

        def base_name(col):
            name = str(col).strip()
            name = re.sub(r"\s*\(\d+\)$", "", name)
            name = name.replace("_", " ")
            name = re.sub(r"\s+", " ", name)
            return name

        def norm(col):
            name = base_name(col).lower()
            return re.sub(r"[^a-z0-9]+", "", name)

        def is_blank_or_zero(series):
            try:
                as_text = series.fillna("").astype(str).str.strip()
                as_text_lower = as_text.str.lower()
                if bool((as_text == "").all()) or bool(as_text_lower.isin(["", "none", "nan", "nat"]).all()):
                    return True

                nums = pd.to_numeric(series, errors="coerce")
                if nums.notna().any() and bool(nums.fillna(0).eq(0).all()):
                    return True
            except Exception:
                return False

            return False

        # 1) Drop exact duplicate column names, keeping the first useful occurrence.
        kept_positions = []
        seen_exact = set()

        for idx, col in enumerate(list(df.columns)):
            key = str(col)
            if key not in seen_exact:
                kept_positions.append(idx)
                seen_exact.add(key)

        df = df.iloc[:, kept_positions]

        # 2) Drop semantic duplicates: Batter/batter, Runs/Runs (2), strike_rate/Strike Rate.
        keep_cols = []
        seen_norm = {}

        for col in list(df.columns):
            key = norm(col)

            if key not in seen_norm:
                seen_norm[key] = col
                keep_cols.append(col)
                continue

            existing = seen_norm[key]

            if is_blank_or_zero(df[existing]) and not is_blank_or_zero(df[col]):
                keep_cols = [c for c in keep_cols if c != existing]
                keep_cols.append(col)
                seen_norm[key] = col

        df = df.loc[:, keep_cols]

        # 3) Remove schema/test filler columns only when they are blank/zero.
        filler_norms = {
            "batter",
            "bowler",
            "team",
            "battingteam",
            "bowlingteam",
            "matches",
            "innings",
            "wickets",
            "legalballs",
            "runsconceded",
            "oversbowled",
            "dotballs",
            "fours",
            "sixes",
            "battersr",
            "bowlingstrikerate",
            "resolvedplayer",
            "teamcode",
            "keyplayerscore",
            "suggestedrole",
            "xino",
            "targetprofile",
            "playoffseasons",
            "yearswon",
            "venueprofile",
            "avgfirstinningsscore",
        }

        drop_cols = []

        for col in list(df.columns):
            if norm(col) in filler_norms and is_blank_or_zero(df[col]):
                if len(df.columns) - len(drop_cols) > 3:
                    drop_cols.append(col)

        if drop_cols:
            df = df.drop(columns=drop_cols)

        # 4) Final exact duplicate pass.
        final_cols = []
        final_seen = set()

        for col in list(df.columns):
            key = str(col)
            if key not in final_seen:
                final_cols.append(col)
                final_seen.add(key)

        df = df.loc[:, final_cols]

        return df

    except Exception:
        return df


def _safe_st_dataframe(data=None, *args, **kwargs):
    data = _clean_dataframe_for_streamlit_display(data)
    data = _tactical_display_drop_empty_stats(data)
    return st.dataframe(data, *args, **kwargs)

# IPL SQL Agent clean Streamlit dataframe display END



# IPL SQL Agent tactical main-result display cleanup START

def _tactical_display_drop_empty_stats(df):
    # Hide empty schema-compatibility stat columns from tactical summary tables only.
    if df is None or not hasattr(df, "columns"):
        return df

    try:
        import re
        import pandas as pd

        df = df.copy()

        def norm(col):
            return re.sub(r"[^a-z0-9]+", "", str(col).lower())

        def emptyish(series):
            try:
                txt = series.fillna("").astype(str).str.strip().str.lower()

                if bool(txt.isin(["", "none", "nan", "nat"]).all()):
                    return True

                nums = pd.to_numeric(series, errors="coerce")

                if nums.notna().any() and bool(nums.fillna(0).eq(0).all()):
                    return True

            except Exception:
                return False

            return False

        cols_norm = {norm(c) for c in df.columns}

        is_summary_table = (
            ("analysisarea" in cols_norm and "insight" in cols_norm)
            or ("recommendation" in cols_norm and "insight" in cols_norm)
        )

        if not is_summary_table:
            return df

        removable = {
            "runs",
            "balls",
            "dismissals",
            "strikerate",
            "battingaverage",
            "economy",
            "matches",
            "innings",
            "wickets",
            "legalballs",
            "runsconceded",
            "oversbowled",
            "dotballs",
            "fours",
            "sixes",
            "battersr",
            "bowlingstrikerate",
            "batter",
            "bowler",
            "team",
            "battingteam",
            "bowlingteam",
        }

        drop_cols = []

        for col in list(df.columns):
            if norm(col) in removable and emptyish(df[col]) and len(df.columns) - len(drop_cols) > 2:
                drop_cols.append(col)

        if drop_cols:
            df = df.drop(columns=drop_cols)

        return df

    except Exception:
        return df

# IPL SQL Agent tactical main-result display cleanup END


def render_dataframe(df, name=None):
    display_df = clean_dataframe(df)

    if display_df is None:
        return

    if isinstance(display_df, pd.DataFrame):
        if display_df.empty:
            st.info("No rows returned for this section.")
            return

        _safe_st_dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            column_config={
                "#": st.column_config.NumberColumn(
                    "#",
                    width="small",
                )
            } if "#" in display_df.columns else None,
        )

        render_details(df)

    else:
        st.write(display_df)



# IPL SQL Agent display polish START

def _ipl_frontend_clean_text(value):
    import re

    if value is None:
        return value

    text = str(value)

    def repl(match):
        try:
            number = float(match.group(0))
            return f"{number:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return match.group(0)

    text = re.sub(r"(?<![0-9])\d+\.\d{4,}(?![0-9])", repl, text)
    text = text.replace("shot-events", "shot events")

    return text


def _ipl_frontend_column_key(column):
    return str(column).strip().lower().replace("_", " ")


def _ipl_frontend_should_drop_column(column, series):
    key = _ipl_frontend_column_key(column)

    always_hide = {
        "cricsheet name",
        "is overseas",
        "is active",
        "full name striker",
        "full name bowler",
    }

    if key in always_hide:
        return True

    hide_if_empty = {
        "batting style",
        "bowling style",
        "bowling arm",
    }

    if key not in hide_if_empty:
        return False

    try:
        values = [str(x).strip().lower() for x in series.dropna().tolist()]
        useful = [
            x for x in values
            if x not in {"", "unknown", "nan", "none", "null"}
        ]
        return len(useful) == 0
    except Exception:
        return False


def _ipl_frontend_is_summary_only_dataframe(value):
    if not isinstance(value, pd.DataFrame) or value.empty:
        return False

    cols = {
        str(c).strip().lower().replace("_", " ")
        for c in value.columns
    }

    return cols.issubset({"section", "summary", "#"})


def clean_dataframe(df):
    if df is None:
        return None

    if not isinstance(df, pd.DataFrame):
        return df

    if df.empty:
        return df

    display_df = df.copy()

    drop_cols = []

    for col in display_df.columns:
        if str(col).lower() in HIDDEN_COLUMNS:
            drop_cols.append(col)
            continue

        if _ipl_frontend_should_drop_column(col, display_df[col]):
            drop_cols.append(col)

    if drop_cols:
        display_df = display_df.drop(columns=drop_cols)

    if "#" not in display_df.columns:
        display_df.insert(0, "#", range(1, len(display_df) + 1))

    display_df = display_df.rename(
        columns={
            column: str(column).replace("_", " ").title()
            for column in display_df.columns
        }
    )

    display_df = display_df.drop(
        columns=[
            c for c in display_df.columns
            if c in {
                "Cricsheet Name",
                "Is Overseas",
                "Is Active",
                "Full Name Striker",
                "Full Name Bowler",
            }
        ],
        errors="ignore",
    )

    return display_df

# IPL SQL Agent display polish END


def render_answer(result):
    if not isinstance(result, dict):
        st.write(result)
        return

    paragraph = (
        result.get("analysis_paragraph")
        or result.get("paragraph")
        or result.get("answer")
        or result.get("summary")
    )

    if isinstance(paragraph, pd.DataFrame):
        paragraph = None

    if paragraph:
        st.markdown(
            f"""
            <div class="result-card answer-text">
                {_ipl_frontend_clean_text(paragraph)}
            </div>
            """,
            unsafe_allow_html=True,
        )

    main_result = result.get("result")

    if (
        isinstance(main_result, pd.DataFrame)
        and not main_result.empty
        and not _ipl_frontend_is_summary_only_dataframe(main_result)
    ):
        st.markdown('<div class="section-title">Main result</div>', unsafe_allow_html=True)
        render_dataframe(main_result, "Main result")

    extra_tables = result.get("extra_tables") or {}

    if isinstance(extra_tables, dict) and extra_tables:
        st.markdown('<div class="section-title">Extra analysis tables</div>', unsafe_allow_html=True)

        tabs = st.tabs([format_table_name(name) for name in extra_tables.keys()])

        for tab, (name, table) in zip(tabs, extra_tables.items()):
            with tab:
                render_dataframe(table, name)

    sql_query = result.get("sql_query")

    if sql_query:
        with st.expander("SQL used"):
            st.code(sql_query, language="sql")

    similar_questions = result.get("similar_questions") or []

    if similar_questions:
        st.markdown('<div class="section-title">Similar questions and deep dives</div>', unsafe_allow_html=True)

        cols = st.columns(2)

        for index, question in enumerate(similar_questions[:4]):
            with cols[index % 2]:
                st.button(
                    question,
                    key=f"similar_{index}_{question}",
                    on_click=select_question,
                    args=(question,),
                    width="stretch",
                )


def render_sidebar_examples():
    st.sidebar.markdown("## Example questions")
    st.sidebar.caption("Pick one to send it to the question box.")

    for group_name, questions in EXAMPLE_QUESTION_GROUPS.items():
        with st.sidebar.expander(group_name, expanded=False):
            for question in questions:
                st.button(
                    question,
                    key=f"sidebar_example_{group_name}_{question}",
                    on_click=select_question,
                    args=(question,),
                    width="stretch",
                )


def _ipl_clear_question_box():
    """Clear the question input safely through a Streamlit callback."""
    st.session_state["question_input"] = ""
    st.session_state["run_requested"] = False


def render_top_question_box():
    st.markdown('<div class="section-title">Ask your question</div>', unsafe_allow_html=True)

    if "question_input" not in st.session_state:
        st.session_state["question_input"] = ""

    if "run_requested" not in st.session_state:
        st.session_state["run_requested"] = False

    question_text = st.text_area(
        "Ask your IPL question",
        key="question_input",
        placeholder="Example: best bowlers against Kohli for GT",
        label_visibility="collapsed",
        height=140,
    )

    col_submit, col_clear = st.columns([1, 1])

    with col_submit:
        ask_clicked = st.button(
            "Ask",
            width="stretch",
            type="primary",
        )

    with col_clear:
        st.button(
            "Clear",
            width="stretch",
            on_click=_ipl_clear_question_box,
        )

    queued_from_example = bool(st.session_state.get("run_requested", False))

    if ask_clicked or queued_from_example:
        st.session_state["run_requested"] = True
        return str(st.session_state.get("question_input", question_text)).strip()

    return ""

def run_question_if_needed(question):
    question = normalise_text(question)

    should_run = bool(st.session_state.get("run_requested", False)) or bool(question)

    if not should_run:
        return

    st.session_state["run_requested"] = False

    if not question:
        question = normalise_text(st.session_state.get("question_input", ""))

    if not question:
        st.warning("Type a question first.")
        return

    with st.spinner("Running IPL analysis..."):
        try:
            result = answer_question_with_fallback(question)
            st.session_state.latest_result = result
            st.session_state.latest_question = question

        except Exception as error:
            st.session_state.latest_result = {
                "analysis_paragraph": f"Something failed while answering this question: {error}",
                "extra_tables": {},
            }
            st.session_state.latest_question = question

# IPL SQL Agent route badge UI override START

def _ipl_badge_text(result):
    if not isinstance(result, dict):
        return ""

    route = result.get("route_used")
    sources = result.get("data_sources")
    normalised = result.get("normalised_question")

    parts = []

    if route:
        parts.append(f"Route: {route}")

    if sources:
        parts.append(f"Data: {sources}")

    if normalised:
        parts.append(f"Corrected query: {normalised}")

    return " • ".join(parts)


def _ipl_is_empty_table(value):
    return hasattr(value, "empty") and value.empty


def render_answer(result):
    if result is None:
        return

    if not isinstance(result, dict):
        st.write(result)
        return

    paragraph = (
        result.get("analysis_paragraph")
        or result.get("paragraph")
        or result.get("answer")
        or ""
    )

    badge_text = _ipl_badge_text(result)

    if paragraph:
        st.markdown(
            f"""
            <div class="answer-card">
                {paragraph}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if badge_text:
        st.caption(badge_text)

    fallback_note = result.get("fallback_note")

    if fallback_note:
        st.info(str(fallback_note))

    main_result = result.get("result")
    extra_tables = result.get("extra_tables") or {}

    if isinstance(extra_tables, dict):
        extra_tables = {
            name: table
            for name, table in extra_tables.items()
            if table is not None and not _ipl_is_empty_table(table)
        }

    if isinstance(main_result, pd.DataFrame) and not main_result.empty:
        # Avoid repeating one-row summary-only tables when richer tables exist.
        lower_cols = {
            str(column).lower().replace("_", " ")
            for column in main_result.columns
        }

        summary_only = lower_cols.issubset({"section", "summary", "#"})

        if not summary_only:
            st.markdown('<div class="section-title">Main result</div>', unsafe_allow_html=True)
            render_dataframe(main_result, "Main result")

    if extra_tables:
        tab_names = list(extra_tables.keys())
        tabs = st.tabs(tab_names)

        for tab, name in zip(tabs, tab_names):
            with tab:
                render_dataframe(extra_tables[name], name)

    sql_query = result.get("sql_query")

    if sql_query:
        with st.expander("SQL used"):
            st.code(str(sql_query), language="sql")

    similar_questions = result.get("similar_questions") or []

    if similar_questions:
        st.markdown('<div class="section-title">Try a related question</div>', unsafe_allow_html=True)

        for index, question in enumerate(similar_questions[:6]):
            st.button(
                question,
                key=f"similar_question_{index}_{question}",
                on_click=select_question,
                args=(question,),
                width="stretch",
            )

# IPL SQL Agent route badge UI override END

def render_latest_result():
    latest_result = st.session_state.get("latest_result")
    latest_question = st.session_state.get("latest_question")

    if latest_result is None:
        return

    if latest_question:
        st.markdown(
            f"""
            <div class="small-muted">
                Showing result for: <b>{latest_question}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_answer(latest_result)


def render_footer():
    st.markdown(
        """
        <div class="footer">
            Made by Samar Mahajan
        </div>
        """,
        unsafe_allow_html=True,
    )


def main():
    setup_page()

    st.markdown(f'<div class="main-title">{APP_TITLE}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="main-subtitle">{APP_SUBTITLE}</div>', unsafe_allow_html=True)

    render_sidebar_examples()

    if "question_input" not in st.session_state:
        st.session_state["question_input"] = ""

    if "run_requested" not in st.session_state:
        st.session_state.run_requested = False

    question = render_top_question_box()

    run_question_if_needed(question)

    render_latest_result()

    render_footer()


if __name__ == "__main__":
    main()


