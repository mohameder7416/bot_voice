


from db import Database
from variables.variables import load_variables
from pymysql import Error

def get_dealer_voice(db):
    """
    Retrieve voice information for a dealer from the dealer_info table.
    
   
        str: The dealer's voice information or None if not found
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
        
        # Query to get dealer voice from dealer_info table
        query = """
            SELECT voice FROM dealer_info 
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
            return None
    
    except Error as e:
        error_mes = f"get_dealer_voice function => {str(e)}"
        print(error_mes)
        return None