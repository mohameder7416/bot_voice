import os
from .db import DataBase
from variables.variables import load_variables
from pymysql import Error
       # Get database connection parameters from environment variables
DB_HOST_READ = os.getenv("DB_HOST_READ")
DB_USER_READ = os.getenv("DB_USER_READ")
DB_PASSWORD_READ = os.getenv("DB_PASSWORD_READ")
DB_NAME_READ = os.getenv("DB_NAME_READ")
DB_PORT_READ = int(os.getenv("DB_PORT_READ", 3306))  # Providing a default value for the port

def get_dealer_voice():
    """
    Retrieve voice information for a dealer from the dealer_info table.
    
    Returns:
        str: The dealer's voice information or "alloy" if not found
    """
    try:
        # Get dealer_id from variables
        db = DataBase(
            host=DB_HOST_READ ,
            user=DB_USER_READ ,
            password=DB_PASSWORD_READ,
            database=DB_NAME_READ,
            port=DB_PORT_READ 
        )
        variables = load_variables()
        
        dealer_id = variables.get("dealer_id")
        
        if not dealer_id:
            print("Error: dealer_id not found in variables")
            return "alloy"
        
        # Establish database connection
        conn = db.connexion()
        if not conn:
            print("Error: Could not establish database connection")
            return "alloy"
        
        # Query to get dealer voice from dealer_info table
        query = """
            SELECT voice FROM dealers_info 
            WHERE dealer_id = %s
        """
        
        # Execute query and get results
        results = db.readQuery(conn, query, (dealer_id,))
        
        # Close the connection
        conn.close()
        
        # Return the voice value if results exist
        if results and len(results) > 0:
            return results[0][0]  # First row, first column (voice)
        else:
            print(f"No voice information found for dealer ID: {dealer_id}")
            return "alloy"
    
    except Error as e:
        error_mes = f"get_dealer_voice function => {str(e)}"
        print(error_mes)
        return "alloy"
