"""
Tools for OpenAI Realtime API assistants.
"""

import sys
sys.path.append('..')
import datetime as dt
import requests
from datetime import timezone
import os
import json 
from dotenv import load_dotenv
from bot.utils.create_token import create_token
from bot.variables.variables import load_variables
import redis
import pandas as pd
import pandasql as ps
from sqlalchemy import create_engine
from typing import Dict, Any, List, Tuple, Callable
from config.system_prompts import system_prompt_manager

# Load environment variables
load_dotenv()

secret_key = os.getenv("secret_key")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

def get_stored_arguments(lead_id):
    """Load stored arguments for a specific lead from Redis."""
    stored_args = redis_client.get(f"lead_arguments:{lead_id}")
    return json.loads(stored_args) if stored_args else {}

def save_arguments(lead_id, new_arguments):
    """
    Save arguments for a specific lead ID to Redis.
    Updates existing arguments instead of overwriting them.
    """
    existing_args = get_stored_arguments(lead_id)
    existing_args.update(new_arguments)
    redis_client.set(f"lead_arguments:{lead_id}", json.dumps(existing_args))
    key = f"lead_arguments:{lead_id}"
    print(f"Filters saved for lead {lead_id}: {existing_args}")
    
    return key  # Return the key used to store the filters

def create_pwa_log(message):
    """Log messages to a central system."""
    print(f"PWA LOG: {message}")
    # Implement actual logging logic here

async def make_appointment_handler():
    """Generate a link for a customer to book an appointment with available time slots"""
    try:
        variables = load_variables()
        lead_id_crm = variables["lead_crm_id"]
        
        url = f"{os.getenv('PWA_API_CRM', '')}/appointment/link"
        payload = json.dumps({
            "lead_id": int(lead_id_crm),
            "source": "AI Bot"
        })
        
        headers = create_token()
        response = requests.request("GET", url, headers=headers, data=payload)
        
        if response.ok:
            result = response.json().get('result', '')
            return f"Here's your appointment booking link: {result}"
        else:
            return "I'm sorry, I couldn't generate an appointment link at this time."
    except Exception as e:
        create_pwa_log(f"Error in make_appointment: {str(e)}")
        return "I'm sorry, I encountered an error while trying to generate an appointment link."

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

def get_products_info(*args, **kwargs):
    """
    Get products information from the API with optional filters.

    Parameters:
        args: A single dictionary of filters (optional)
        kwargs: Keyword arguments for filters

    Filters can include:
        vin (str): Vehicle Identification Number
        year (int): Year of manufacture
        make (str): Make of the vehicle
        model (str): Model of the vehicle
        isadded (bool): Whether the product is added
        mileage (int): Mileage of the vehicle
        condition (str): Condition of the vehicle
        title (str): Title of the product
        price (float): Price of the product
        price_type (str): Type of price

    Returns:
        dict: A dictionary containing either a list of products or an error message.
    """
    variables = load_variables()
    lead_id = variables["lead_id"]
    dealer_id = variables["dealer_id"]
    product_id = variables["product_id"]
    if not lead_id:
        raise ValueError("lead_id not found in variables")

    # Load filters for this lead from Redis
    filters = get_stored_arguments(lead_id)
    
    # Update with new arguments if provided
    if args and isinstance(args[0], dict):
        filters.update(args[0])
    filters.update(kwargs)
    
    # Save updated arguments to Redis
    save_arguments(lead_id, filters)

    api_url = os.getenv("base_url_products_invontaire")
    headers = create_token()
    product_data = {
        "user_id": dealer_id,
        "product_id": product_id,
        "fields": ["make"]
    }

    try:
        product_response = requests.get(api_url, json=product_data, headers=headers)
        product_response.raise_for_status()
        product_details = product_response.json().get("data", [])
        
        if not product_details:
            return {"error": "Product not found"}
        
        product_make = product_details[0].get("make")
    except requests.RequestException as e:
        return {"error": f"Failed to fetch product details. Error: {str(e)}"}

    # Compare the make from the API with the make from the arguments
    if 'make' in filters and product_make != filters['make']:
        # If they don't match, don't include product_id in the main query
        product_id = None
    # Build API filters using ALL stored filters
    api_filters = []
    filter_mapping = {
        'vin': ['serial_number', '='],
        'year': ['year', '='],
        'make': ['make', '='],
        'model': ['model', '='],
        'mileage': ['mileage', '='],
        'price': ['price', '='],
        'condition': ['condition', '='],
        'title': ['title', '='],
        'isadded': ['is_added', '='],
        'price_type': ['price_type', '=']
    }

    # Debug print to see what filters we're working with
    print(f"Debug - Current filters: {filters}")
    make_filter = filters.get('make')
    # Process ALL filters from storage
    for key, value in filters.items():
        if key in filter_mapping:
            field, operator = filter_mapping[key]
            api_filters.append([field, operator, value])

    data = {
        "user_id": dealer_id,
        "status": "published",
        "filters": api_filters,
        "fields": [
            "year", "make", "model", "mileage", "price", 
            "factory_color", "serial_number", "carfax_url", 
            "condition", "title", "is_added", "price_type"
        ]
    }
    if product_id:
        data["product_id"] = product_id

    print(f"Debug - API request data: {data}")

    try:
        response = requests.get(api_url, json=data, headers=headers)
        response.raise_for_status()
        products = response.json().get("data", [])
        print(f"Debug - API response: {products}")
        
        if not products:
            return {"message": "No products found matching the criteria."}
        return {"products": products}
    except requests.RequestException as e:
        return {"error": f"Failed to fetch products. Error: {str(e)}"}

# List of tools with their definitions and handlers
tools: List[Tuple[Dict[str, Any], Callable]] = [
    (
        {
            "name": "make_appointment",
            "description": "Generate a link for a customer to book an appointment with available time slots",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        make_appointment_handler
    ),
    (
        {
            "name": "get_dealers_info",
            "description": "Query dealer information including name, address, phone, services offered, and business details",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql_query": {
                        "type": "string",
                        "description": "SQL query to execute on the dealers_df table"
                    }
                },
                "required": ["sql_query"]
            }
        },
        get_dealers_info_handler
    ),
    (
        {
            "name": "get_products_info",
            "description": "Get products information from the API with optional filters",
            "parameters": {
                "type": "object",
                "properties": {
                    "vin": {"type": "string"},
                    "year": {"type": "integer"},
                    "make": {"type": "string"},
                    "model": {"type": "string"},
                    "isadded": {"type": "boolean"},
                    "mileage": {"type": "integer"},
                    "condition": {"type": "string"},
                    "title": {"type": "string"},
                    "price": {"type": "number"},
                    "price_type": {"type": "string"}
                }
            }
        },
        get_products_info
    )
]

# Store the tools in the SystemPromptManager
system_prompt_manager.store([tool[1] for tool in tools])

