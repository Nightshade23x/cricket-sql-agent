import pandas as pd

def main():
    deliveries=pd.read_csv("data/processed/deliveries.csv",low_memory=False)
    matches=pd.read_csv("data/processed/matches.csv",low_memory=False)
    print("deliveries shape",deliveries.shape)
    print("Matches shape",matches.shape)
    print("\ndeliveries columns")
    print(deliveries.columns.tolist())
    print("\nmatches cols:")
    print(matches.columns.tolist())
    print("\nfirst 5 matches:")
    print(matches.head())
    print("\n first 5 deliveries")
    print(deliveries.head())
    print("\n missing values in matches")
    print(matches.isna().sum())
    print("\n missing values in deliveries")
    print(deliveries.isna().sum())

if __name__=="__main__":
    main()