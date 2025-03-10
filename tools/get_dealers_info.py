import logging
import os
import pandas as pd
import pandasql as ps
from dotenv import load_dotenv
from sqlalchemy import create_engine
from variables.variables import load_variables
# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

get_dealers_info_def = {
    "name": "get_dealers_info",
    "description": "Executes an SQL query on the dealers_info a table for dealers informations that offers buying services. This table contains columns: (dealer_name, address, phone, credit_app_link, inventory_link,offers_test_drive, welcome_message, shipping, trade_ins, opening_hours offer_finance) dealer_name: The name of the dealership. , It is typically the brand or business name that customers associate with the dealership ",
    "parameters": {
        "type": "object",
        "properties": {
            "sql_query": {
                "type": "string",
                "description": "An SQL query string to filter and retrieve dealer information.",
            },
        },
        "required": ["sql_query"],
    },
}


async def get_dealers_info_handler(sql_query: str):
    """Executes an SQL query on the dealers_info table and returns the result."""
    load_dotenv()
    
    try:
        logger.info(f"🔍 Executing dealer information query: {sql_query}")
        
        # Database connection setup
        DB_USER_READ = os.getenv("DB_USER_READ")
        DB_PASSWORD_READ = os.getenv("DB_PASSWORD_READ")
        DB_HOST_READ = os.getenv("DB_HOST_READ")
        DB_PORT_READ = os.getenv("DB_PORT_READ")
        DB_NAME_READ = os.getenv("DB_NAME_READ")
        engine = create_engine(f"mysql+pymysql://{DB_USER_READ}:{DB_PASSWORD_READ}@{DB_HOST_READ}:{DB_PORT_READ}/{DB_NAME_READ}")
        
        # Load dealer_id from JSON file
        variables = load_variables()
        dealer_id = variables["dealer_id"]
        
        # Load dealers_info data
        dealers_df = pd.read_sql_query(f"SELECT * FROM dealers_info WHERE dealer_id = {dealer_id}", engine)
        print("dealers_df",dealers_df)
        # Execute SQL query on DataFrame
        env = {"dealers_info": dealers_df}
        print("sql_query",sql_query)
        result_df = ps.sqldf(sql_query, env)
        
        if result_df.empty:
            logger.warning("⚠️ No results found for the given query.")
            return {"error": "No matching records found."}
        
        logger.info("✅ Dealer information retrieved successfully.")
        return result_df.to_json()
        
    except Exception as e:
        logger.error(f"❌ Error executing query: {str(e)}")
        return {"error": str(e)}


get_dealers_infos = (get_dealers_info_def, get_dealers_info_handler)
