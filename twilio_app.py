"""
FastAPI application for Twilio integration with OpenAI Realtime API.
"""

import os
import json
import asyncio
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
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
        twilio_params = {k: v for k, v in form_data.items()}
    else:
        twilio_params = dict(request.query_params)
    
    logging.info(f"Twilio Inbound Details: {json.dumps(twilio_params, indent=2)}")
    
    # Extract caller's number and session ID (CallSid)
    caller_number = twilio_params.get("From", "Unknown")
    session_id = twilio_params.get("CallSid")
    logging.info(f"Caller Number: {caller_number}")
    logging.info(f"Session ID (CallSid): {session_id}")
    
    # Set default first message
    first_message = "Hello, welcome to our service. How can I assist you today?"
    
    # Set up a new session for this call
    session = {
        "transcript": "",
        "stream_sid": None,
        "caller_number": caller_number,
        "call_details": twilio_params,
        "first_message": first_message
    }
    sessions[session_id] = session
    
    # Respond to Twilio with TwiML
    host = request.headers.get("host", "localhost:8000")
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
                       <Response>
                           <Say>Please wait while we connect you to our AI assistant.</Say>
                           <Pause length="1"/>
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