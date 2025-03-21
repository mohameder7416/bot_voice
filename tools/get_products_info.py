import sys
sys.path.append('..')
import logging
import os
from dotenv import load_dotenv
import requests
from utils.create_token import create_token
from variables.variables import load_variables
# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
from utils.llm_call import llm_call

get_products_info_def = {
    "name": "get_products_info",
    "description": "Retrieves products information from the inventory API with optional filters. This function can filter by VIN, year, make, model, condition, price, and other attributes.",
    "parameters": {
        "type": "object",
        "properties": {
            "filters": {
                "type": "object",
                "description": "A dictionary of filters to apply to the product search.",
                "properties": {
                    "vin": {
                        "type": "string",
                        "description": "Vehicle Identification Number"
                    },
                    "year": {
                        "type": "integer",
                        "description": "Year of manufacture"
                    },
                    "make": {
                        "type": "string",
                        "description": "Make of the vehicle"
                    },
                    "model": {
                        "type": "string",
                        "description": "Model of the vehicle"
                    },
                    "isadded": {
                        "type": "boolean",
                        "description": "Whether the product is added"
                    },
                    "mileage": {
                        "type": "integer",
                        "description": "Mileage of the vehicle"
                    },
                    "condition": {
                        "type": "string",
                        "description": "Condition of the vehicle"
                    },
                    "title": {
                        "type": "string",
                        "description": "Title of the product"
                    },
                    "price": {
                        "type": "number",
                        "description": "Price of the product"
                    },
                    "price_type": {
                        "type": "string",
                        "description": "Type of price"
                    },
                    "dealer_id": {
                        "type": "integer",
                        "description": "Dealer ID (defaults to 102262 if not provided)"
                    }
                }
            }
        },
        "required": ["filters"]
    }
}

async def get_products_info_handler(filters: dict):
    """
    Retrieves product information from the inventory API and analyzes the results using OpenAI's LLM.
    
    Args:
        filters (dict): Dictionary of filters to apply to the product search.
        
    Returns:
        dict: Contains analyzed product insights or an error message.
    """
    load_dotenv()

    try:
        logger.info(f"🔍 Retrieving product information with filters: {filters}")

        api_url = os.getenv("base_url_products_invontaire")
        headers = create_token()

        api_filters = []
        for key, value in filters.items():
            if key == 'vin':
                api_filters.append(["serial_number", "=", value])
            elif key in ['year', 'make', 'model', 'mileage', 'price', 'condition', 'title']:
                api_filters.append([key, "=", value])
            elif key == 'isadded':
                api_filters.append(["is_added", "=", value])
            elif key == 'price_type':
                api_filters.append(["price_type", "=", value])
        
        variables = load_variables()
        dealer_id = variables.get("dealer_id")

        data = {
            "user_id": dealer_id,
            "status": "published",
            "filters": api_filters,
            "fields": ["year", "make", "model", "mileage", "price", "factory_color", 
                      "serial_number", "carfax_url", "condition", "title", "is_added", 
                      "price_type"]
        }

        logger.info(f"📤 Sending API request with data: {data}")

        response = requests.get(api_url, json=data, headers=headers)
        response.raise_for_status()
        products = response.json().get("data", [])

        if not products:
            logger.warning("⚠️ No products found matching the criteria.")
            return {"message": "No products found matching the criteria."}

        logger.info(f"✅ Successfully retrieved {len(products)} products.")

        # Convert product data to a human-readable format for analysis
        product_summary = "\n".join([
            f"- {p['attributes']['year']} {p['attributes']['make']} {p['attributes']['model']} "
            f"({p['attributes']['factory_color']}), {p['attributes']['mileage']} miles, "
            f"Price: ${p['attributes']['price']}"
            for p in products
        ])

        analysis_prompt = f"""
        Here is a list of vehicles in inventory:

        {product_summary}

        You are a business intelligence assistant that analyzes vehicle inventory data and provides insights.
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
        Your task is to analyze the inventory based on these filters and provide key insights.

        Provide a professional summary of your findings.
        """

        # Get analysis from LLM
        analysis = llm_call(prompt=analysis_prompt, task="precise")

        return {"analysis": analysis}
        
    except requests.RequestException as e:
        logger.error(f"❌ API request error: {str(e)}")
        return {"error": f"Failed to fetch products. Error: {str(e)}"}
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}")
        return {"error": str(e)}

# Create the tuple for export
get_products_infos = (get_products_info_def, get_products_info_handler)