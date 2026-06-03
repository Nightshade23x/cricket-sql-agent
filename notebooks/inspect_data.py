from pathlib import Path
import pandas as pd

raw_folder= Path("data/raw/ipl_csv2")#folder where the csv files are kept
csv_files=list(raw_folder.glob("*.csv"))#get all the csv files from the folder
print("Num of csv files:", len(csv_files))
first_file=csv_files[0]
print("first file:",first_file)
df=pd.read_csv(first_file)#read first csv into a Panda dataframe
print("shape", df.shape)#print shape aka rows and cols
print("\nCols:")
print(df.columns.tolist())
print("\nFirst 5 rows:")
print(df.head())