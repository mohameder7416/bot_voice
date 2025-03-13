import sys
sys.path.append('..')
import os
import json
import logging
import datetime as dt
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
from variables.variables import load_variables
from utils.create_token import create_token

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# Load environment variables
secret_key = os.getenv("secret_key")
PWA_CRM_API_URL = os.getenv("PWA_CRM_API_URL")

def get_availability(dealer_id):
    if not PWA_CRM_API_URL:
        raise ValueError("PWA_CRM_API_URL is not set in environment variables")
    
    time_url = f"{PWA_CRM_API_URL}/task/availability?user_id={dealer_id}"
    headers = create_token()
    
    logger.info(f"Making API request to: {time_url}")
    logger.debug(f"Headers: {headers}")
    
    response = requests.get(time_url, headers=headers)
    
    # Log response details for debugging
    logger.info(f"API response status code: {response.status_code}")
    logger.info(f"API response headers: {response.headers}")
    logger.debug(f"API response content: {response.text}")
    
    return response

def parse_response_safely(response):
    """Safely parse the response and handle potential JSON decode errors"""
    try:
        # Check if response has content
        if not response.text or response.text.isspace():
            logger.error("API returned empty response")
            return {"error": "Empty response from API"}
        
        # Try to parse as JSON
        return response.json()
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        logger.error(f"Response content: {response.text}")
        
        # Return a structured error response
        return {
            "error": "Invalid JSON response",
            "details": str(e),
            "response_text": response.text[:500],  # First 500 chars for debugging
            "status_code": response.status_code
        }

# Define the function definition for the tool
get_availability_def = {
    "name": "get_availability",
    "description": "Finds the nearest available time slot for a dealer based on customer's preferred time.",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "The date to check availability for in YYYY-MM-DD format.",
            },
            "time": {
                "type": "string",
                "description": "The preferred time in HH:MM format (24-hour).",
            },
            "time_window": {
                "type": "integer",
                "description": "Optional time window in hours to search for available slots (default: 3).",
            }
        },
        "required": ["date", "time"]
    },
}

async def get_availability_handler(date: str, time: str, time_window: int = 3):
    """
    Finds the nearest available time slot for a dealer based on customer's preferred time.
    
    Args:
        date: The date to check availability for in YYYY-MM-DD format
        time: The preferred time in HH:MM format (24-hour)
        time_window: Optional time window in hours to search for available slots (default: 3)
        
    Returns:
        JSON response with the nearest available time slot
    """
    load_dotenv()
    
    try:
        logger.info(f"🔍 Checking dealer availability near date: {date}, time: {time}")
        
        # Load dealer_id from variables
        variables = load_variables()
        dealer_id = variables.get("dealer_id")
        
        if not dealer_id:
            logger.error("❌ dealer_id not found in variables")
            return {"error": "dealer_id not found in configuration"}
        
        logger.info(f"Using dealer_id: {dealer_id}")
        
        # Parse requested datetime
        try:
            requested_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            logger.info(f"Requested datetime: {requested_datetime}")
        except ValueError as e:
            logger.error(f"❌ Date/time parsing error: {str(e)}")
            return {"error": f"Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time."}
        
        # Call the existing get_availability function
        response = get_availability(dealer_id)
        
        if response.status_code != 200:
            logger.error(f"❌ API request failed with status code: {response.status_code}")
            logger.error(f"Response content: {response.text}")
            return {
                "error": f"Failed to retrieve availability. Status code: {response.status_code}",
                "details": response.text
            }
        
        # Parse the response safely
        availability_data = parse_response_safely(response)
        
        # Check if there was an error parsing the response
        if "error" in availability_data:
            logger.error(f"❌ Error parsing API response: {availability_data['error']}")
            return availability_data
        
        logger.info(f"Successfully parsed availability data")
        
        # Find the nearest available time slot
        nearest_slot = None
        min_time_diff = timedelta(hours=24*7)  # Initialize with a large value (1 week)
        all_available_slots = []
        
        # Check if slots exist in the response
        if "slots" not in availability_data or not availability_data["slots"]:
            logger.warning("⚠️ No slots found in the availability data")
            return {
                "available": False,
                "message": "No available slots found in the dealer's calendar",
                "nearest_slot": None,
                "alternative_slots": []
            }
        
        for slot in availability_data.get("slots", []):
            # Ensure slot has required fields
            if "date" not in slot or "time" not in slot:
                logger.warning(f"⚠️ Skipping slot with missing date or time: {slot}")
                continue
                
            try:
                # Make sure we're using the correct format from the API response
                slot_datetime = datetime.strptime(f"{slot['date']} {slot['time']}", "%Y-%m-%d %H:%M")
                
                # Only consider future slots
                if slot_datetime < datetime.now():
                    logger.debug(f"Skipping past slot: {slot['date']} {slot['time']}")
                    continue
                
                # Calculate time difference
                time_diff = abs(slot_datetime - requested_datetime)
                
                # Store all slots within the time window for additional options
                if time_diff <= timedelta(hours=time_window):
                    all_available_slots.append({
                        "date": slot["date"],
                        "time": slot["time"],
                        "time_diff_minutes": int(time_diff.total_seconds() / 60),
                        "datetime": slot_datetime.strftime("%Y-%m-%d %H:%M")
                    })
                
                # Update nearest slot if this one is closer
                if time_diff < min_time_diff:
                    min_time_diff = time_diff
                    nearest_slot = slot
            except ValueError as e:
                # Log and skip slots with invalid date/time format
                logger.warning(f"⚠️ Invalid date/time format in slot: {slot}. Error: {str(e)}")
                continue
        
        if not nearest_slot:
            logger.warning(f"⚠️ No availability found near {date} {time}")
            return {
                "available": False,
                "message": f"No available slots found near {date} at {time}",
                "nearest_slot": None,
                "alternative_slots": []
            }
        
        # Sort alternative slots by time difference
        sorted_alternatives = sorted(all_available_slots, key=lambda x: x["time_diff_minutes"])
        
        # Format the time difference for the nearest slot
        nearest_diff_minutes = int(min_time_diff.total_seconds() / 60)
        time_diff_str = f"{nearest_diff_minutes} minute{'s' if nearest_diff_minutes != 1 else ''}"
        if nearest_diff_minutes >= 60:
            hours = nearest_diff_minutes // 60
            minutes = nearest_diff_minutes % 60
            time_diff_str = f"{hours} hour{'s' if hours != 1 else ''}"
            if minutes > 0:
                time_diff_str += f" and {minutes} minute{'s' if minutes != 1 else ''}"
        
        logger.info(f"✅ Found nearest available slot: {nearest_slot['date']} at {nearest_slot['time']} ({time_diff_str} from requested time)")
        
        return {
            "available": True,
            "message": f"Found available slot {time_diff_str} from your requested time",
            "nearest_slot": {
                "date": nearest_slot["date"],
                "time": nearest_slot["time"],
                "time_diff_minutes": nearest_diff_minutes,
                "datetime": datetime.strptime(f"{nearest_slot['date']} {nearest_slot['time']}", "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
            },
            "alternative_slots": sorted_alternatives[:5]  # Return up to 5 alternatives
        }
        
    except Exception as e:
        logger.error(f"❌ Error retrieving availability: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {"error": str(e)}

# Create the tool tuple
get_availability_tools = (get_availability_def, get_availability_handler)

# Example usage
if __name__ == "__main__":
    # For testing purposes
    import asyncio
    
    async def test_availability():
        try:
            # Load variables for testing
            variables = load_variables()
            dealer_id = variables.get("dealer_id")
            
            if not dealer_id:
                print("ERROR: dealer_id not found in variables")
                return
                
            print(f"Using dealer_id: {dealer_id}")
            
            # First, get the raw response
            response = get_availability(dealer_id)
            
            print("\nRaw API Response Status Code:", response.status_code)
            print("Raw API Response Headers:", dict(response.headers))
            print("Raw API Response Content:")
            print(response.text)
            
            # Try to parse the response safely
            print("\nTrying to parse response as JSON:")
            parsed_data = parse_response_safely(response)
            print(json.dumps(parsed_data, indent=2))
            
            # Only test the handler if we got a valid response
            if response.status_code == 200 and "error" not in parsed_data:
                print("\nTesting handler with parsed data...")
                result = await get_availability_handler("2023-05-15", "14:00", 5)
                print("\nHandler Result:")
                print(json.dumps(result, indent=2))
            else:
                print("\nSkipping handler test due to API response issues")
                
        except Exception as e:
            print(f"Error in test: {str(e)}")
            import traceback
            print(traceback.format_exc())
    
    asyncio.run(test_availability())