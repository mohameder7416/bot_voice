from pymysql import Error
import os
from .db import DataBase
from variables.variables import load_variables


DB_HOST_READ = os.getenv("DB_HOST_READ")
DB_USER_READ = os.getenv("DB_USER_READ")
DB_PASSWORD_READ = os.getenv("DB_PASSWORD_READ")
DB_NAME_READ = os.getenv("DB_NAME_READ")
DB_PORT_READ = os.getenv("DB_PORT_READ", 3306)  # Providing a default value for the port









def get_dealer_name_bot():
    """
    Retrieve bot name for a dealer from the dealer_info table.
    
    Args:
        db (DataBase): An instance of the DataBase class
        variables (dict, optional): Dictionary containing variables including dealer_id.
                                   If None, will attempt to load variables.
    
    Returns:
        str: The dealer's bot name or None if not found
    """
    try:
        # Get dealer_id from variables
        db = DataBase(
            host=DB_HOST_READ ,
            user=DB_USER_READ ,
            password=DB_PASSWORD_READ,
            database=DB_NAME_READ,
            port=3306
        )
        variables = load_variables()
        
        dealer_id = variables.get("dealer_id")
        
        if not dealer_id:
            print("Error: dealer_id not found in variables")
            return None
        
        # Establish database connection
        conn = db.connexion()
        if not conn:
            print("Error: Could not establish database connection")
            return None
        
        # Query to get bot_name from dealer_info table
        query = """
            SELECT bot_name FROM dealers_info 
            WHERE dealer_id = %s
        """
        
        # Execute query and get results
        results = db.readQuery(conn, query, (dealer_id,))
        
        # Close the connection
        conn.close()
        
        # Return the bot_name value if results exist
        if results and len(results) > 0:
            return results[0][0]  # First row, first column (bot_name)
        else:
            print(f"No bot name found for dealer ID: {dealer_id}")
            return None
    
    except Error as e:
        error_mes = f"get_dealer_name_bot function => {str(e)}"
        print(error_mes)
        return None