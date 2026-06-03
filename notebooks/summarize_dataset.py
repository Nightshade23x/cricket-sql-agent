from pathlib import Path  
import pandas as pd  


def main():  
    raw_folder = Path("data/raw/ipl_csv2")  
    all_csv_files = list(raw_folder.glob("*.csv"))  
    info_files = list(raw_folder.glob("*_info.csv")) 
    delivery_files = []  # Empty list for delivery files
    for file in all_csv_files:  # Goes through every CSV file
        if not file.name.endswith("_info.csv"):  # Checks that file is not an info file
            delivery_files.append(file)  # Adds it to delivery files
    print("Total CSV files:", len(all_csv_files))  
    print("Delivery files:", len(delivery_files))  
    print("Info files:", len(info_files))  
    first_delivery_file = delivery_files[0] 
    first_info_file = info_files[0]  
    delivery_df = pd.read_csv(first_delivery_file)  
    print("\nFirst delivery file:", first_delivery_file)  
    print("Delivery shape:", delivery_df.shape)  # Prints rows and columns
    print("Delivery columns:")  
    print(delivery_df.columns.tolist())  # Prints column names
    print("\nFirst 5 delivery rows:")  
    print(delivery_df.head())  # Prints first 5 delivery rows
    print("\nFirst info file:", first_info_file)  # Prints info file path
    print("\nFirst 30 lines from info file:")  # Heading
    lines = first_info_file.read_text(encoding="utf-8").splitlines()  # Reads info file as plain text
    for line in lines[:30]:  # Loops through first 30 lines
        print(line)  # Prints each line

if __name__ == "__main__":  
    main()  