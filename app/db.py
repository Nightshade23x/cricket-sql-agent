from urllib.parse import quote_plus #helps prepare the sql server connection string for sqlAlchemy
import pandas as pd
from sqlalchemy import create_engine,text# used to connect to sql server and run sql queries

def get_engine():# func creates and returns a database connection engine
    server=r"localhost\SQLEXPRESS"
    database="CricketAnalytics"
    connection_string=(
        "DRIVER={ODBC Driver 17 for SQL Server};"  # This uses the installed ODBC driver
        f"SERVER={server};"  # This tells Python which SQL Server to connect to
        f"DATABASE={database};"  # This tells Python which database to use
        "Trusted_Connection=yes;"  # This uses Windows Authentication
        "TrustServerCertificate=yes;"  # This avoids certificate issues on local SQL Server
    )
    connection_url= quote_plus(connection_string)#make the connection string url safe
    engine=create_engine(f"mssql+pyodbc:///?odbc_connect={connection_url}")
    return engine

def run_query(sql_query): #runs a sql query and returns the result
    engine=get_engine()
    with engine.connect() as connection:
        result=pd.read_sql(text(sql_query),connection)
    return result