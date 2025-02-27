"""
FastAPI application for Twilio integration with OpenAI Realtime API.
"""

import os
import json
import asyncio
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
import requests
from dotenv import load_dotenv

from routes.websocket import handle_media_stream

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Retrieve the OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAKE_WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL", "")

# Check if the API key is missing
if not OPENAI_API_KEY:
    logging.error("Missing OpenAI API key. Please set it in the .env file.")
    exit(1)

# Initialize FastAPI server
app = FastAPI()

# Session management: Store session data for ongoing calls
sessions = {}

# Root route - just for checking if the server is running
@app.get("/")
async def root():
    return {"message": "Twilio Media Stream Server is running!"}

# Handle incoming calls from Twilio
@app.post("/incoming-call")
@app.get("/incoming-call")
async def incoming_call(request: Request):
    logging.info("Incoming call")
    
    # Get all incoming call details from the request
    if request.method == "POST":
        form_data = await request.form()
        twillio_params = {k: v for k, v in form_data.items()}
    else:
        twillio_params = dict(request.query_params)
    
    logging.info(f"Twilio Inbound Details: {json.dumps(twillio_params, indent=2)}")
    
    # Extract caller's number and session ID (CallSid)
    caller_number = twillio_params.get("From", "Unknown")
    session_id = twillio_params.get("CallSid")
    logging.info(f"Caller Number: {caller_number}")
    logging.info(f"Session ID (CallSid): {session_id}")
    
    # Send the caller's number to Make.com webhook to get a personalized first message
    first_message = "Hello, welcome to Bart's Automotive. How can I assist you today?"
    
    try:
        # Send a POST request to Make.com webhook
        webhook_response = requests.post(
            MAKE_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            json={
                "route": "1",
                "data1": caller_number,
                "data2": "empty"
            }
        )
        
        if webhook_response.ok:
            response_text = webhook_response.text
            logging.info(f"Make.com webhook response: {response_text}")
            try:
                response_data = json.loads(response_text)
                if response_data and response_data.get("firstMessage"):
                    first_message = response_data["firstMessage"]
                    logging.info(f"Parsed firstMessage from Make.com: {first_message}")
            except json.JSONDecodeError as parse_error:
                logging.error(f"Error parsing webhook response: {parse_error}")
                first_message = response_text.strip()
        else:
            logging.error(f"Failed to send data to Make.com webhook: {webhook_response.status_code} - {webhook_response.reason}")
    except Exception as error:
        logging.error(f"Error sending data to Make.com webhook: {error}")
    
    # Set up a new session for this call
    session = {
        "transcript": "",
        "stream_sid": None,
        "caller_number": caller_number,
        "call_details": twillio_params,
        "first_message": first_message
    }
    sessions[session_id] = session
    
    # Respond to Twilio with TwiML
    host = request.headers.get("host", "localhost:8000")
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
                       <Response>
                           <Connect>
                               <Stream url="wss://{host}/media-stream">
                                   <Parameter name="firstMessage" value="{first_message}" />
                                   <Parameter name="callerNumber" value="{caller_number}" />
                               </Stream>
                           </Connect>
                       </Response>"""
    
    return Response(content=twiml_response, media_type="text/xml")

# WebSocket route for the media stream
@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    # Use Twilio's CallSid as the session ID or create a new one
    headers = dict(websocket.headers)
    session_id = headers.get("x-twilio-call-sid", f"session_{int(asyncio.get_event_loop().time())}")
    session = sessions.get(session_id, {"transcript": "", "stream_sid": None})
    
    # Handle the WebSocket connection
    await handle_media_stream(websocket, session_id, session)
    
    # Clean up the session
    if session_id in sessions:
        del sessions[session_id]

# Run the FastAPI application with uvicorn
if __name__ == "__main__":
    import uvicorn
    PORT = int(os.getenv("PORT", "5050"))
    uvicorn.run(app, host="0.0.0.0", port=PORT)

