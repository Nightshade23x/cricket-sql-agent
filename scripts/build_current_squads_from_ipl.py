from pathlib import Path
import re
import sys
from difflib import get_close_matches

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

import pandas as pd
import requests
from bs4 import BeautifulSoup

from app.db import run_query


OUTPUT_PATH = PROJECT_ROOT / "data" / "current_squads_2026.csv"

TEAM_PAGES = {
    "CSK": {
        "team_name": "Chennai Super Kings",
        "url": "https://www.iplt20.com/teams/chennai-super-kings",
    },
    "DC": {
        "team_name": "Delhi Capitals",
        "url": "https://www.iplt20.com/teams/delhi-capitals",
    },
    "GT": {
        "team_name": "Gujarat Titans",
        "url": "https://www.iplt20.com/teams/gujarat-titans",
    },
    "KKR": {
        "team_name": "Kolkata Knight Riders",
        "url": "https://www.iplt20.com/teams/kolkata-knight-riders",
    },
    "LSG": {
        "team_name": "Lucknow Super Giants",
        "url": "https://www.iplt20.com/teams/lucknow-super-giants",
    },
    "MI": {
        "team_name": "Mumbai Indians",
        "url": "https://www.iplt20.com/teams/mumbai-indians",
    },
    "PBKS": {
        "team_name": "Punjab Kings",
        "url": "https://www.iplt20.com/teams/punjab-kings",
    },
    "RR": {
        "team_name": "Rajasthan Royals",
        "url": "https://www.iplt20.com/teams/rajasthan-royals",
    },
    "RCB": {
        "team_name": "Royal Challengers Bengaluru",
        "url": "https://www.iplt20.com/teams/royal-challengers-bengaluru",
    },
    "SRH": {
        "team_name": "Sunrisers Hyderabad",
        "url": "https://www.iplt20.com/teams/sunrisers-hyderabad",
    },
}


# Manual fixes for common display-name -> Cricsheet-name differences.
# Add more here whenever the script prints unmatched names.
NAME_ALIASES = {
    "Virat Kohli": "V Kohli",
    "MS Dhoni": "MS Dhoni",
    "Ruturaj Gaikwad": "RD Gaikwad",
    "Rishabh Pant": "RR Pant",
    "Nicholas Pooran": "N Pooran",
    "Jasprit Bumrah": "JJ Bumrah",
    "Rohit Sharma": "RG Sharma",
    "Hardik Pandya": "HH Pandya",
    "Shubman Gill": "Shubman Gill",
    "Sai Sudharsan": "Sai Sudharsan",
    "Rashid Khan": "Rashid Khan",
    "Kagiso Rabada": "K Rabada",
    "Mohammed Siraj": "Mohammed Siraj",
    "Bhuvneshwar Kumar": "B Kumar",
    "Shivam Dube": "S Dube",
    "Sanju Samson": "SV Samson",
    "KL Rahul": "KL Rahul",
    "Kuldeep Yadav": "Kuldeep Yadav",
    "Axar Patel": "AR Patel",
    "T. Natarajan": "T Natarajan",
    "Lungisani Ngidi": "L Ngidi",
    "Noor Ahmad": "Noor Ahmad",
    "Josh Hazlewood": "JR Hazlewood",
    "Phil Salt": "PD Salt",
    "Jos Buttler": "JC Buttler",
    "David Miller": "DA Miller",
    "Glenn Phillips": "GD Phillips",
    "Washington Sundar": "Washington Sundar",
    "Rahul Tewatia": "R Tewatia",
    "Shahrukh Khan": "M Shahrukh Khan",
    "Prasidh Krishna": "M Prasidh Krishna",
    "Ishant Sharma": "I Sharma",
    "Jason Holder": "JO Holder",
    "Aiden Markram": "AK Markram",
    "Mitchell Marsh": "MR Marsh",
    "Anrich Nortje": "A Nortje",
    "Mohammad Shami": "Mohammed Shami",
    "Avesh Khan": "Avesh Khan",
    "Mayank Yadav": "Mayank Yadav",
    "Sunil Narine": "SP Narine",
    "Varun Chakaravarthy": "CV Varun",
    "Rinku Singh": "RK Singh",
    "Ajinkya Rahane": "AM Rahane",
    "Venkatesh Iyer": "VR Iyer",
    "Andre Russell": "AD Russell",
    "Tristan Stubbs": "T Stubbs",
    "Tim David": "TH David",
    "Romario Shepherd": "R Shepherd",
    "Krunal Pandya": "KH Pandya",
    "Yash Dayal": "Yash Dayal",
    "Suyash Sharma": "Suyash Sharma",
    "Devdutt Padikkal": "D Padikkal",
    "Jitesh Sharma": "JM Sharma",
}
NAME_ALIASES.update({
    # CSK
    "Dewald Brevis": "D Brevis",
    "Sarfaraz Khan": "SN Khan",
    "Matthew William Short": "MW Short",
    "Shreyas Gopal": "S Gopal",
    "Matt Henry": "MJ Henry",
    "Rahul Chahar": "RD Chahar",
    "Akeal Hosein": "AJ Hosein",

    # DC
    "Karun Nair": "KK Nair",
    "Prithvi Shaw": "PP Shaw",
    "Nitish Rana": "N Rana",
    "Mitchell Starc": "MA Starc",
    "Dushmantha Chameera": "PVD Chameera",
    "Kyle Jamieson": "KA Jamieson",

    # GT
    "Mohd. Arshad Khan": "Arshad Khan",
    "Jayant Yadav": "J Yadav",
    "Kulwant Khejroliya": "K Khejroliya",

    # KKR
    "Manish Pandey": "MK Pandey",
    "Finn Allen": "FH Allen",
    "Tim Seifert": "TL Seifert",
    "Rovman Powell": "R Powell",
    "Cameron Green": "C Green",
    "Rachin Ravindra": "R Ravindra",

    # LSG
    "Aiden Markram": "AK Markram",
    "Mitchell Marsh": "MR Marsh",
    "Josh Inglis": "JP Inglis",
    "Ayush Badoni": "A Badoni",

    # MI
    "Surya Kumar Yadav": "SA Yadav",
    "Sherfane Rutherford": "SE Rutherford",
    "Quinton de Kock": "Q de Kock",
    "Mahipal Lomror": "MK Lomror",
    "Will Jacks": "WG Jacks",
    "Shardul Thakur": "SN Thakur",
    "Trent Boult": "TA Boult",
    "Mayank Markande": "M Markande",
    "Deepak Chahar": "DL Chahar",
    "Keshav Maharaj": "KA Maharaj",

    # PBKS
    "Shreyas Iyer": "SS Iyer",
    "Nehal Wadhera": "N Wadhera",
    "Prabhsimran Singh": "P Simran Singh",
    "Marcus Stoinis": "MP Stoinis",
    "Marco Jansen": "M Jansen",
    "Yuzvendra Chahal": "YS Chahal",
    "Vyshak Vijaykumar": "V Vyshak",
    "Xavier Bartlett": "X Bartlett",
    "Pravin Dubey": "P Dubey",
    "Lockie Ferguson": "LH Ferguson",

    # RR
    "Shimron Hetmyer": "SO Hetmyer",
    "Yashasvi Jaiswal": "YBK Jaiswal",
    "Riyan Parag": "R Parag",
    "Ravindra Jadeja": "RA Jadeja",
    "Dasun Shanaka": "MD Shanaka",
    "Jofra Archer": "JC Archer",
    "Tushar Deshpande": "TU Deshpande",
    "Adam Milne": "AF Milne",
    "Kuldeep Sen": "KR Sen",
    "Nandre Burger": "N Burger",

    # RCB
    "Rajat Patidar": "RM Patidar",
    "Jordan Cox": "JL Cox",
    "Richard Gleeson": "RJW Gleeson",

    # SRH
    "Heinrich Klaasen": "H Klaasen",
    "Travis Head": "TM Head",
    "Harshal Patel": "HV Patel",
    "Pat Cummins": "PJ Cummins",
    "Jaydev Unadkat": "JD Unadkat",
})
NAME_ALIASES.update({
    # CSK
    "Anshul Kamboj": "AS Kamboj",

    # GT
    "Luke Wood": "L Wood",
    "Nishant Sindhu": "N Sindhu",
    "Manav Suthar": "M Suthar",

    # KKR
    "Angkrish Raghuvanshi": "A Raghuvanshi",
    "Anukul Roy": "AS Roy",
    "Vaibhav Arora": "VG Arora",
    "Prashant Solanki": "P Solanki",
    "Blessing Muzarabani": "B Muzarabani",

    # LSG
    "Arshin Kulkarni": "A Kulkarni",
    "George Linde": "GF Linde",

    # MI
    "Ryan Rickelton": "R Rickelton",
    "Raj Angad Bawa": "Raj Bawa",
    "Corbin Bosch": "C Bosch",

    # RR
    "Vaibhav Sooryavanshi": "Vaibhav Suryavanshi",
    "Donovan Ferreira": "D Ferreira",
    "Lhuan-dre Pretorious": "Lhuan-dre Pretorius",
    "Yudhvir Singh Charak": "Yudhvir Singh",
    "Kwena Maphaka": "K Maphaka",
    "Vignesh Puthur": "V Puthur",

    # RCB
    "Jacob Bethell": "J Bethell",
    "Rasikh Dar": "Rasikh Salam",
    "Jacob Duffy": "JA Duffy",

    # SRH
    "Kamindu Mendis": "PHKD Mendis",
    "Dilshan Madushanka": "D Madushanka",
    "Gerald Coetzee": "G Coetzee",
})
NAME_ALIASES.update({
    # CSK remaining unmatched
    "Prashant Veer": "Prashant Veer",
    "Zak Foulkes": "Zak Foulkes",
    "Macneil Noronha": "Macneil Noronha",
    "Dian Forrester": "Dian Forrester",
    "Spencer Johnson": "Spencer Johnson",
    

    # DC remaining unmatched
    "Pathum Nissanka": "Pathum Nissanka",
    "Sahil Parakh": "Sahil Parakh",
    "Vipraj Nigam": "Vipraj Nigam",
    "Ajay Mandal": "Ajay Mandal",
    "Tripurana Vijay": "Tripurana Vijay",
    "Madhav Tiwari": "Madhav Tiwari",
    "Rehan Ahmed": "Rehan Ahmed",

    # GT remaining unmatched
    "Connor Esterhuizen": "Connor Esterhuizen",
    "Gurnoor Singh Brar": "Gurnoor Singh Brar",

    # KKR remaining unmatched
    "Tejasvi Singh": "Tejasvi Singh",
    "Luvnith Sisodia": "Luvnith Sisodia",
    "Sarthak Ranjan": "Sarthak Ranjan",
    "Daksh Kamra": "Daksh Kamra",
    "Saurabh Dubey": "Saurabh Dubey",

    # LSG remaining unmatched
    "Matthew Breetzke": "Matthew Breetzke",
    "Mukul Choudhary": "Mukul Choudhary",
    "Digvesh Singh": "Digvesh Singh",
    "Naman Tiwari": "Naman Tiwari",

    # MI remaining unmatched
    "Robin Minz": "Robin Minz",
    "Danish Malewar": "Danish Malewar",
    "Ruchit Ahir": "Ruchit Ahir",
    "Mayank Rawat": "Mayank Rawat",
    "Mohammad Izhar": "Mohammad Izhar",
    "Allah Ghazanfar": "Allah Ghazanfar",

    # PBKS remaining unmatched
    "Harnoor Pannu": "Harnoor Pannu",
    "Pyla Avinash": "Pyla Avinash",
    "Mitch Owen": "Mitch Owen",
    "Cooper Connolly": "Cooper Connolly",
    "Vishal Nishad": "Vishal Nishad",

    # RR remaining unmatched
    "Shubham Dubey": "Shubham Dubey",
    "Aman Rao Perala": "Aman Rao Perala",
    "Emanjot Chahal": "Emanjot Chahal",
    "Sushant Mishra": "Sushant Mishra",

    # RCB remaining unmatched
    "Satvik Deswal": "Satvik Deswal",
    "Mangesh Yadav": "Mangesh Yadav",
    "Vicky Ostwal": "Vicky Ostwal",
    "Vihaan Malhotra": "Vihaan Malhotra",
    "Kanishk Chouhan": "Kanishk Chouhan",

    # SRH remaining unmatched
    "Smaran Ravichandran": "Smaran Ravichandran",
    "Krains Fuletra": "Krains Fuletra",
    "R.S Ambrish": "R.S Ambrish",
    "Eshan Malinga": "Eshan Malinga",
    "Onkar Tarmale": "Onkar Tarmale",
    "Amit Kumar": "Amit Kumar",
    "Praful Hinge": "Praful Hinge",
})
NAME_ALIASES.update({
    "Kuldip Yadav": "Kuldip Yadav",
})
def normalize_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def get_database_player_names() -> list[str]:
    query = """
SELECT DISTINCT player_name
FROM (
    SELECT striker AS player_name FROM deliveries
    UNION
    SELECT bowler AS player_name FROM deliveries
    UNION
    SELECT striker AS player_name FROM shot_events
    UNION
    SELECT bowler AS player_name FROM shot_events
) x
WHERE player_name IS NOT NULL
ORDER BY player_name;
"""
    df = run_query(query)

    if df is None or df.empty:
        return []

    return df["player_name"].dropna().astype(str).tolist()


def map_to_cricsheet_name(display_name: str, db_names: list[str]) -> tuple[str, str]:
    if display_name in NAME_ALIASES:
        return NAME_ALIASES[display_name], "manual_alias"

    if display_name in db_names:
        return display_name, "exact"

    normalized_db = {normalize_name(name): name for name in db_names}
    normalized_display = normalize_name(display_name)

    if normalized_display in normalized_db:
        return normalized_db[normalized_display], "normalized_exact"

    matches = get_close_matches(normalized_display, normalized_db.keys(), n=1, cutoff=0.86)

    if matches:
        return normalized_db[matches[0]], "fuzzy"

    return display_name, "unmatched"


def infer_basic_bowling_arm(role: str, bowling_style: str) -> str:
    style = (bowling_style or "").lower()

    if "left" in style:
        return "Left-arm"

    if "right" in style:
        return "Right-arm"

    if "bowler" in role.lower() or "all" in role.lower():
        return "Unknown"

    return "Unknown"


def scrape_team(team_code: str, team_name: str, url: str, db_names: list[str]) -> list[dict]:
    print(f"Scraping {team_code}: {url}")

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n")

    lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        # Remove extra spaces
        line = re.sub(r"\s+", " ", line)

        lines.append(line)

    rows = []
    current_section = None

    valid_roles = {
        "Batter",
        "WK-Batter",
        "All-Rounder",
        "Bowler",
    }

    section_map = {
        "batters": "Batter",
        "batter": "Batter",
        "wicketkeepers": "WK-Batter",
        "wicket-keepers": "WK-Batter",
        "wicket keepers": "WK-Batter",
        "all rounders": "All-Rounder",
        "all-rounders": "All-Rounder",
        "allrounders": "All-Rounder",
        "bowlers": "Bowler",
        "bowler": "Bowler",
    }

    skip_words = {
        "squad",
        "fixtures",
        "results",
        "videos",
        "news",
        "archive",
        "official team site",
        "captain",
        "coach",
        "owner",
        "venue",
        "team",
        "contact",
        "sponsorship",
        "privacy policy",
        "terms & conditions",
        "copyright",
        "accept cookies",
        "what are cookies?",
    }

    i = 0

    while i < len(lines):
        line = lines[i]
        lower_line = line.lower()

        if lower_line in section_map:
            current_section = section_map[lower_line]
            i += 1
            continue

        if current_section is None:
            i += 1
            continue

        if lower_line in skip_words:
            i += 1
            continue

        # Case 1: same-line format, e.g. "Shubman Gill Batter"
        same_line_match = re.match(
            r"^(?P<name>.+?)\s+(?P<role>WK-Batter|Batter|All-Rounder|Bowler)$",
            line,
        )

        if same_line_match is not None:
            display_name = same_line_match.group("name").strip()
            role = same_line_match.group("role").strip()

            cricsheet_name, match_method = map_to_cricsheet_name(display_name, db_names)

            rows.append(
                {
                    "season": 2026,
                    "team_code": team_code,
                    "team_name": team_name,
                    "display_name": display_name,
                    "cricsheet_name": cricsheet_name,
                    "role": role,
                    "batting_style": "",
                    "bowling_style": "",
                    "bowling_arm": infer_basic_bowling_arm(role, ""),
                    "is_overseas": 0,
                    "is_active": 1,
                    "name_match_method": match_method,
                }
            )

            i += 1
            continue

        # Case 2: split-line format, e.g.
        # "Shubman Gill"
        # "Batter"
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()

            if next_line in valid_roles:
                display_name = line.strip()
                role = next_line

                # avoid garbage names
                if (
                    len(display_name) >= 3
                    and not display_name.lower().startswith("image")
                    and display_name.lower() not in skip_words
                    and not display_name.isdigit()
                ):
                    cricsheet_name, match_method = map_to_cricsheet_name(display_name, db_names)

                    rows.append(
                        {
                            "season": 2026,
                            "team_code": team_code,
                            "team_name": team_name,
                            "display_name": display_name,
                            "cricsheet_name": cricsheet_name,
                            "role": role,
                            "batting_style": "",
                            "bowling_style": "",
                            "bowling_arm": infer_basic_bowling_arm(role, ""),
                            "is_overseas": 0,
                            "is_active": 1,
                            "name_match_method": match_method,
                        }
                    )

                    i += 2
                    continue

        i += 1

    print(f"  Found {len(rows)} players for {team_code}")
    return rows


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    db_names = get_database_player_names()
    print(f"Loaded {len(db_names)} player names from local database.")

    all_rows = []

    for team_code, info in TEAM_PAGES.items():
        all_rows.extend(
            scrape_team(
                team_code=team_code,
                team_name=info["team_name"],
                url=info["url"],
                db_names=db_names,
            )
        )

    df = pd.DataFrame(all_rows)

    if df.empty:
        raise RuntimeError("No squad rows scraped. Check page structure or internet access.")

    # Keep exact loader columns first, plus match method for checking.
    column_order = [
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
        "name_match_method",
    ]

    df = df[column_order]

    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"\nSaved squad CSV to: {OUTPUT_PATH}")
    print(f"Rows: {len(df)}")

    print("\nRows by team:")
    print(df.groupby("team_code").size().sort_index())

    unmatched = df[df["name_match_method"] == "unmatched"]

    if not unmatched.empty:
        print("\nUNMATCHED NAMES - review these manually in the CSV:")
        print(unmatched[["team_code", "display_name", "cricsheet_name", "role"]].to_string(index=False))
    else:
        print("\nAll names matched by exact/alias/fuzzy logic.")

    print("\nNext command:")
    print("python -m scripts.load_current_squads")


if __name__ == "__main__":
    main()