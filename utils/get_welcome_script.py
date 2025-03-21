import os
from .db import DataBase
from variables.variables import load_variables
from pymysql import Error

def get_welcome_script():
    """
    Retrieve welcome script for a dealer from the dealers_info table.
    
    Returns:
        str: The dealer's welcome script or a default message if not found
    """
    try:
        # Get database connection parameters from environment variables
        DB_HOST_READ = os.getenv("DB_HOST_READ")
        DB_USER_READ = os.getenv("DB_USER_READ")
        DB_PASSWORD_READ = os.getenv("DB_PASSWORD_READ")
        DB_NAME_READ = os.getenv("DB_NAME_READ")
        DB_PORT_READ = int(os.getenv("DB_PORT_READ", 3306))  # Providing a default value for the port

        
        # Initialize database connection
        db = DataBase(
            host=DB_HOST_READ ,
            user=DB_USER_READ ,
            password=DB_PASSWORD_READ,
            database=DB_NAME_READ,
            port=DB_PORT_READ 
        )
        
        # Get dealer_id from variables
        variables = load_variables()
        dealer_id = variables.get("dealer_id")
        
        if not dealer_id:
            print("Error: dealer_id not found in variables")
            return "Welcome! How can I assist you today?"
        
        # Establish database connection
        conn = db.connexion()
        if not conn:
            print("Error: Could not establish database connection")
            return "Welcome! How can I assist you today?"
        
        # Query to get welcome script from dealer_info table
        query = """
            SELECT welcome_script FROM dealers_info 
            WHERE dealer_id = %s
        """
        
        # Execute query and get results
        results = db.readQuery(conn, query, (dealer_id,))
        
        # Close the connection
        conn.close()
        
        # Return the welcome_script value if results exist
        if results and len(results) > 0 and results[0][0]:
            print("result",results[0][0])
            return results[0][0]  # First row, first column (welcome_script)
        else:
            print(f"No welcome script found for dealer ID: {dealer_id}")
            return "hello this is mohamed from auto delers digital "
    
    except Error as e:
        error_mes = f"get_welcome_script function => {str(e)}"
        print(error_mes)
        return "hello this is mohamed from auto delers digital "