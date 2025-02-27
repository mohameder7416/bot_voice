"""
Main script for testing Twilio with OpenAI Realtime API.
"""

import os
import logging
import uvicorn
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def main():
    """Main function to run the Twilio FastAPI application."""
    try:
        # Check if OpenAI API key is set
        if not os.getenv("OPENAI_API_KEY"):
            logger.error("OPENAI_API_KEY environment variable is not set")
            return
        
        # Check if Make webhook URL is set
        if not os.getenv("MAKE_WEBHOOK_URL"):
            logger.warning("MAKE_WEBHOOK_URL environment variable is not set")
        
        # Run the FastAPI application
        PORT = int(os.getenv("PORT", "5050"))
        uvicorn.run("twilio_app:app", host="0.0.0.0", port=PORT, reload=True)
    except Exception as e:
        logger.error(f"Error running Twilio application: {e}")

if __name__ == "__main__":
    main()

