import os
import json
import redis
from dotenv import load_dotenv
from bot.utils.create_token import create_token

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

def create_pwa_log(message):
    """Log messages to a central system."""
    print(f"PWA LOG: {message}")
    # Implement actual logging logic here

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

