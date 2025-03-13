from pymysql import Error

from db import Database
from variables.variables import load_variables

def get_dealer_name_bot(db):
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
        db=Database()
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
            SELECT bot_name FROM dealer_info 
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