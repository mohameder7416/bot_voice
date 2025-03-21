import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def llm_call(
    prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    task: str = "default"
) -> str:
    """
    Call OpenAI models with system prompt and user prompt to generate a result.
    
    Args:
        prompt: The user prompt/query
        system_prompt: The system instructions for the model
        task: Task type to determine model configuration (default, creative, precise)
        
    Returns:
        Generated text response
    """
    # Static configuration for different tasks
    MODEL_CONFIG = {
        "default": {
            "name": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1000
        },
        "creative": {
            "name": "gpt-4o",
            "temperature": 0.9,
            "max_tokens": 2000
        },
        "precise": {
            "name": "gpt-4o-mini",
            "temperature": 0.1,
            "max_tokens": 1000
        }
    }
    
    # Get API key from environment variables (loaded from .env)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OPENAI_API_KEY not found in environment variables")
        return "Error: OpenAI API key not found. Please check your .env file."
    
    try:
        # Get configuration based on task
        config = MODEL_CONFIG.get(task, MODEL_CONFIG["default"])
        
        # Initialize OpenAI client
        client = OpenAI(api_key=api_key)
        
        # Prepare messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        # Call the API
        response = client.chat.completions.create(
            model=config["name"],
            messages=messages,
            temperature=config["temperature"],
            max_tokens=config["max_tokens"]
        )
        
        # Return the generated text
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"❌ Error calling OpenAI LLM for task '{task}': {str(e)}")
        
        # Attempt fallback to a more reliable model
        try:
            logger.info("gpt-4o")
            client = OpenAI(api_key=api_key)
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
            
        except Exception as fallback_error:
            logger.error(f"❌ Fallback also failed: {str(fallback_error)}")
            return "Failed to generate text with LLM, including fallback attempt."

