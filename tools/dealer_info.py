import os
import pandas as pd
import pandasql as ps
from sqlalchemy import create_engine
from .utils import create_pwa_log
from bot.variables.variables import load_variables

async def get_dealers_info_handler(sql_query):
    """Query dealer information including name, address, phone, services offered, and business details"""
    try:
        # Database connection parameters
        DB_USER = os.getenv("DB_USER")
        DB_PASSWORD = os.getenv("DB_PASSWORD")
        DB_HOST = os.getenv("DB_HOST")
        DB_PORT = os.getenv("DB_PORT")
        DB_NAME = os.getenv("DB_NAME")
        
        # Create database connection
        engine = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        
        # Load dealer information
        variables = load_variables()
        dealer_id = variables["dealer_id"]
        dealers_df = pd.read_sql_query(f"SELECT * FROM dealers_info WHERE dealer_id = {dealer_id}", engine)
        
        # Execute the SQL query
        env = {'dealers_df': dealers_df}
        result_df = ps.sqldf(sql_query, env)
        
        # Return the results as a string
        return result_df.to_string(index=False)
    except Exception as e:
        create_pwa_log(f"Error in get_dealers_info: {str(e)}")
        return f"I'm sorry, I encountered an error while trying to retrieve dealer information: {str(e)}"

