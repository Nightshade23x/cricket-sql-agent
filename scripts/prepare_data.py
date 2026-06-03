from pathlib import Path
import pandas as pd
import csv

def parse_info_file(info_file):#func is meant to extract match level info from one info file
    match_data={}#dict will store important match info
    match_id=info_file.stem.replace("_info","")
    match_data["match_id"]=match_id#get match id from filename
    with open(info_file,"r",encoding="utf-8") as file:
        reader=csv.reader(file)
        for row in reader:
            if len(row)<3:
                continue
            row_type=row[0]
            key=row[1]#gets the metadata key
            value=row[2]#gets the metadata value
            if row_type !="info":
                continue
            if key=="season":#check if row contains value then store it
                match_data["season"]=value
            elif key=="date":
                match_data["start_date"]=value
            elif key =="event":
                match_data["event"]=value
            elif key=="venue":
                match_data["venue"]=value
            elif key=="city":
                match_data["city"]=value
            elif key=="toss_winner":
                match_data["toss_winner"]=value
            elif key=="toss_decision":
                match_data["toss_decision"]=value
            elif key=="winner":
                match_data["winner"]=value
            elif key=="winner_runs":
                match_data["winner_runs"]=value
            elif key=="winner_wickets":
                match_data["winner_wickets"]=value
            elif key=="player_of_match":
                match_data["player_of_match"]=value
    return match_data

def main():
    raw_folder=Path("data/raw/ipl_csv2")
    processed_folder=Path("data/processed")
    processed_folder.mkdir(parents=True,exist_ok=True)
    all_csv_files=list(raw_folder.glob("*.csv"))
    info_files=list(raw_folder.glob("*_info.csv"))
    delivery_files=[]
    for file in all_csv_files:
        if not file.name.endswith("_info.csv"):
            delivery_files.append(file)
    print("delivery files found:",len(delivery_files))
    print("info files found",len(info_files))
    delivery_dataframes=[]
    for file in delivery_files:
        df=pd.read_csv(file)
        delivery_dataframes.append(df)
    all_deliveries=pd.concat(delivery_dataframes,ignore_index=True)
    all_deliveries.to_csv(processed_folder/"deliveries.csv",index=False)
    match_rows=[]
    for info_file in info_files:
        match_data= parse_info_file(info_file)
        match_rows.append(match_data)
    matches=pd.DataFrame(match_rows)
    matches.to_csv(processed_folder/"matches.csv", index=False)
    print("processed deliveries shape",all_deliveries.shape)
    print("processed matches shape",matches.shape)
    print("saved data/processed/deliveries.csv")
    print("saved data/processed/matches.csv")

if __name__=="__main__":
    main()
