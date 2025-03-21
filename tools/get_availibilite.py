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
        data = json.loads(response.text)
        
        # Handle the actual API response structure
        if 'result' in data and isinstance(data['result'], list):
            logger.info("Converting 'result' array to 'dates' for compatibility")
            return {"dates": data['result']}
        elif 'dates' in data:
            # Already in the expected format
            return data
        else:
            # Log the structure to help debug
            logger.warning(f"Unexpected API response structure. Top-level keys: {list(data.keys())}")
            return data
            
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
        
        # Helper function to convert 12-hour time to 24-hour time
        def convert_to_24hour(time_str):
            """Convert 12-hour format (e.g., '02:00 PM') to 24-hour format (e.g., '14:00')"""
            try:
                return datetime.strptime(time_str, "%I:%M %p").strftime("%H:%M")
            except ValueError as e:
                logger.error(f"Error converting time: {e}")
                return None
        
        # Find the nearest available time slot
        nearest_slot = None
        min_time_diff = timedelta(hours=24*7)  # Initialize with a large value (1 week)
        all_available_slots = []
        
        # Find the date entry for the requested date
        date_entry = None
        for date_item in availability_data.get("dates", []):
            if date_item["date"] == date:
                date_entry = date_item
                break
        
        # Check if we found the date and it has hours data
        if not date_entry:
            logger.warning(f"⚠️ No data found for date: {date}")
            return {
                "available": False,
                "message": f"No available slots found for {date}",
                "nearest_slot": None,
                "alternative_slots": []
            }
        
        if "hours" not in date_entry or not date_entry["hours"]:
            logger.warning(f"⚠️ No time slots available for date: {date}")
            return {
                "available": False,
                "message": f"No available slots found for {date}",
                "nearest_slot": None,
                "alternative_slots": []
            }
        
        # Process all time slots for this date
        for slot in date_entry["hours"]:
            # Ensure slot has required fields
            if "start" not in slot or "end" not in slot:
                logger.warning(f"⚠️ Skipping slot with missing start or end time: {slot}")
                continue
            
            try:
                # Convert 12-hour format to 24-hour format
                start_time_12h = slot["start"]
                end_time_12h = slot["end"]
                start_time_24h = convert_to_24hour(start_time_12h)
                end_time_24h = convert_to_24hour(end_time_12h)
                
                if not start_time_24h or not end_time_24h:
                    logger.warning(f"⚠️ Could not convert time format for slot: {slot}")
                    continue
                
                # Create datetime objects for comparison
                slot_datetime = datetime.strptime(f"{date} {start_time_24h}", "%Y-%m-%d %H:%M")
                
                # Only consider future slots
                if slot_datetime < datetime.now():
                    logger.debug(f"Skipping past slot: {date} {start_time_12h}")
                    continue
                
                # Calculate time difference
                time_diff = abs(slot_datetime - requested_datetime)
                time_diff_hours = time_diff.total_seconds() / 3600
                
                # Store all slots within the time window for additional options
                if time_diff_hours <= time_window:
                    all_available_slots.append({
                        "date": date,
                        "time": start_time_12h,
                        "end_time": end_time_12h,
                        "time_24h": start_time_24h,
                        "end_time_24h": end_time_24h,
                        "time_diff_minutes": int(time_diff.total_seconds() / 60),
                        "datetime": slot_datetime.strftime("%Y-%m-%d %H:%M"),
                        "agent_ids": slot.get("agent_ids", [])
                    })
                
                # Update nearest slot if this one is closer
                if time_diff < min_time_diff:
                    min_time_diff = time_diff
                    nearest_slot = {
                        "date": date,
                        "time": start_time_12h,
                        "end_time": end_time_12h,
                        "time_24h": start_time_24h,
                        "end_time_24h": end_time_24h,
                        "time_diff_minutes": int(time_diff.total_seconds() / 60),
                        "datetime": slot_datetime.strftime("%Y-%m-%d %H:%M"),
                        "agent_ids": slot.get("agent_ids", [])
                    }
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
        sorted_alternatives = sorted(
            [slot for slot in all_available_slots if slot != nearest_slot],
            key=lambda x: x["time_diff_minutes"]
        )
        
        # Format the time difference for the nearest slot
        nearest_diff_minutes = nearest_slot["time_diff_minutes"]
        time_diff_str = f"{nearest_diff_minutes} minute{'s' if nearest_diff_minutes != 1 else ''}"
        if nearest_diff_minutes >= 60:
            hours = nearest_diff_minutes // 60
            minutes = nearest_diff_minutes % 60
            time_diff_str = f"{hours} hour{'s' if hours != 1 else ''}"
            if minutes > 0:
                time_diff_str += f" and {minutes} minute{'s' if minutes != 1 else ''}"
        
        logger.info(f"✅ Found nearest available slot: {date} at {nearest_slot['time']} ({time_diff_str} from requested time)")
        
        # Format the response
        formatted_nearest_slot = {
            "date": nearest_slot["date"],
            "time": nearest_slot["time"],
            "end_time": nearest_slot["end_time"],
            "time_diff_minutes": nearest_slot["time_diff_minutes"],
            "datetime": nearest_slot["datetime"]
        }
        
        formatted_alternatives = []
        for slot in sorted_alternatives[:5]:  # Return up to 5 alternatives
            formatted_alternatives.append({
                "date": slot["date"],
                "time": slot["time"],
                "end_time": slot["end_time"],
                "time_diff_minutes": slot["time_diff_minutes"],
                "datetime": slot["datetime"]
            })
        
        return {
            "available": True,
            "message": f"Found available slot {time_diff_str} from your requested time",
            "nearest_slot": formatted_nearest_slot,
            "alternative_slots": formatted_alternatives
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
                result = await get_availability_handler("2025-04-18", "14:00", 5)
                print("\nHandler Result:")
                print(json.dumps(result, indent=2))
            else:
                print("\nSkipping handler test due to API response issues")
                
        except Exception as e:
            print(f"Error in test: {str(e)}")
            import traceback
            print(traceback.format_exc())
    
    asyncio.run(test_availability())