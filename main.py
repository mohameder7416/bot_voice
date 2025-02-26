# Import required modules
import os
import json
from typing import Dict, Any, Optional
import asyncio
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
import websockets
import requests
from dotenv import load_dotenv
import base64
import sys
sys.path.append('..')
import pandasql as ps
import pandas as pd
from sqlalchemy import create_engine
from bot.utils.load_variables import load_variables
from bot.utils.db import DataBase
from bot.utils.logging import create_pwa_log
import datetime as dt
import jwt
from bot.utils.create_token import create_token

# Load environment variables from .env file
load_dotenv()

# Retrieve the OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PWA_API_CRM = os.getenv("PWA_API_CRM")
print("PWA_API_CRM", PWA_API_CRM)

variables = load_variables()
lead_id_crm = variables["lead_crm_id"]

# Check if the API key is missing
if not OPENAI_API_KEY:
    logging.error("Missing OpenAI API key. Please set it in the .env file.")
    exit(1)

# Initialize FastAPI server
app = FastAPI()

# System message template for the AI assistant's behavior and persona
SYSTEM_MESSAGE = """
### Role
You are an AI assistant named Sophie, working at Bart's Automotive. Your role is to answer customer questions about automotive services and repairs, and assist with booking tow services.
### Persona
- You have been a receptionist at Bart's Automotive for over 5 years.
- You are knowledgeable about both the company and cars in general.
- Your tone is friendly, professional, and efficient.
- You keep conversations focused and concise, bringing them back on topic if necessary.
- You ask only one question at a time and respond promptly to avoid wasting the customer's time.
### Conversation Guidelines
- Always be polite and maintain a medium-paced speaking style.
- When the conversation veers off-topic, gently bring it back with a polite reminder.
### First Message
The first message you receive from the customer is their name and a summary of their last call, repeat this exact message to the customer as the greeting.
### Handling FAQs
Use the function `question_and_answer` to respond to common customer queries.
### Booking a Tow
When a customer needs a tow:
1. Ask for their current address.
2. Once you have the address, use the `book_tow` function to arrange the tow service.
### Scheduling Appointments
When a customer wants to schedule an appointment, use the `make_appointment` function to generate a booking link with available time slots.
### Dealer Information
When a customer asks about the dealer's information, services, or location, use the `get_dealers_info` function to query the appropriate details.
"""

# Some default constants used throughout the application
VOICE = 'alloy'
PORT = int(os.getenv("PORT", "5050"))
MAKE_WEBHOOK_URL = "<your Make.com URL>"

# Session management: Store session data for ongoing calls
sessions = {}

# Event types to log to the console for debugging purposes
LOG_EVENT_TYPES = [
    'response.content.done',
    'rate_limits.updated',
    'response.done',
    'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started',
    'session.created',
    'response.text.done',
    'conversation.item.input_audio_transcription.completed'
]

def get_dealers_info(sql_query: str):
    """
    Execute an SQL query on the dealers_df DataFrame, a table for dealers informations that offers buying services. 
    This table contains columns: (dealer_name, address, phone, credit_app_link, inventory_link, 
    offers_test_drive, welcome_message, shipping, trade_ins, opening_hours offer_finance)
    dealer_name: The name of the dealership. It is typically the brand or business name that customers associate with the dealership, such as "XYZ Motors."

address: The physical location of the dealership. This includes the street address, city, state, and zip code. It helps customers find the dealership.

phone: The contact number of the dealership, allowing customers to call for inquiries, appointments, or other services.

credit_app_link: A link to the dealership's online credit application form. This allows customers to apply for financing or credit pre-approval for vehicle purchases.

inventory_link: A link to the dealership's inventory page, where customers can view available vehicles, their specifications, prices, and other relevant details.

offers_test_drive: Indicates whether the dealership offers test drives for customers interested in trying out a vehicle before making a purchase.

welcome_message: A greeting or introductory message displayed on the dealership's website or sent to customers when they interact with the dealership. It could be something like, "Welcome to XYZ Motors, where we find the perfect vehicle for you!"

shipping: Information regarding shipping options available for purchasing vehicles. This could include delivery to a customer's home or specific areas, and details on shipping fees and timelines.

trade_ins: Describes whether the dealership accepts trade-in vehicles from customers. If so, it might include information on how the trade-in process works, such as valuation or appraisal details.

opening_hours: The hours during which the dealership is open to the public. This typically includes specific opening and closing times for each day of the week.

offer_finance: Indicates whether the dealership provides financing options for customers. It could include details about loan terms, interest rates, and how customers can apply for financing.
    Parameters:
        sql_query (str or dict): An SQL query string or a dictionary with key "sql_query".

        Example: 'SELECT dealer_name, address, phone FROM dealers_df'

    Returns:
        str: Query results as a string, or None if an error occurs.
    """
    load_dotenv()
   
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_NAME = os.getenv("DB_NAME")
    engine = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    if isinstance(sql_query, dict):
        sql_query = sql_query.get('sql_query', '')
    
    try:
        # Load dealer_id from JSON file
        variables = load_variables()
        dealer_id = variables["dealer_id"]
        dealers_df = pd.read_sql_query(f"SELECT * FROM dealers_info WHERE dealer_id = {dealer_id}", engine)
        env = {'dealers_df': dealers_df}
        result_df = ps.sqldf(sql_query, env)
        print("result_df",result_df)
        
        return result_df.to_string(index=False)
        
    except Exception as e:
        error_message = f"Error executing query: {str(e)}"
        create_pwa_log(error_message)
        return None

def make_appointment():
    """
    Generate a link to make an appointment between the customer and the dealer. 
    The link contains available time slots when the dealer is available
    
    Returns:
        string: A link to book the appointment.
    """
    url = f"{PWA_API_CRM}/appointment/link"
    payload = json.dumps({
        "lead_id": int(lead_id_crm),
        "source": "AI Bot"
    })

    headers = create_token()
    response = requests.request("GET", url, headers=headers, data=payload)
    return response.json()['result']

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

# Async function to send data to the Make.com webhook
async def send_to_webhook(payload):
    logging.info(f"Sending data to webhook: {json.dumps(payload, indent=2)}")
    try:
        response = requests.post(
            MAKE_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            json=payload
        )
        
        logging.info(f"Webhook response status: {response.status_code}")
        if response.ok:
            response_text = response.text
            logging.info(f"Webhook response: {response_text}")
            return response_text
        else:
            logging.error(f"Failed to send data to webhook: {response.reason}")
            raise Exception("Webhook request failed")
    except Exception as error:
        logging.error(f"Error sending data to webhook: {error}")
        raise

# WebSocket route for the media stream
@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    logging.info("Client connected to media-stream")
    
    first_message = ""
    stream_sid = ""
    openai_ws_ready = False
    queued_first_message = None
    thread_id = ""
    
    # Use Twilio's CallSid as the session ID or create a new one
    headers = dict(websocket.headers)
    session_id = headers.get("x-twilio-call-sid", f"session_{int(asyncio.get_event_loop().time())}")
    session = sessions.get(session_id, {"transcript": "", "stream_sid": None})
    sessions[session_id] = session
    
    # Retrieve the caller number from the session
    caller_number = session.get("caller_number")
    logging.info(f"Caller Number: {caller_number}")
    
    # Connect to OpenAI Realtime API
    async with websockets.connect(
        "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        openai_ws_ready = True
        logging.info("Connected to the OpenAI Realtime API")
        
        # Send session configuration to OpenAI
        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad"},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice": VOICE,
                "instructions": SYSTEM_MESSAGE,
                "modalities": ["text", "audio"],
                "temperature": 0.8,
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "tools": [
                    {
                        "type": "function",
                        "name": "question_and_answer",
                        "description": "Get answers to customer questions about automotive services and repairs",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"}
                            },
                            "required": ["question"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "book_tow",
                        "description": "Book a tow service for a customer",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "address": {"type": "string"}
                            },
                            "required": ["address"]
                        }
                    },
                    {
                        "type": "function",
                        "name": "make_appointment",
                        "description": "Generate a link for a customer to book an appointment with available time slots",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    },
                    {
                        "type": "function",
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
                    }
                ],
                "tool_choice": "auto"
            }
        }
        
        logging.info(f"Sending session update: {json.dumps(session_update)}")
        await openai_ws.send(json.dumps(session_update))
        
        # Function to send the first message
        async def send_first_message():
            if queued_first_message and openai_ws_ready:
                logging.info(f"Sending queued first message: {queued_first_message}")
                await openai_ws.send(json.dumps(queued_first_message))
                await openai_ws.send(json.dumps({"type": "response.create"}))
                return None
            return queued_first_message
        
        # Send the first message if it's already queued
        queued_first_message = await send_first_message()
        
        # Function to send error response
        async def send_error_response():
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "I apologize, but I'm having trouble processing your request right now. Is there anything else I can help you with?"
                }
            }))
        
        # Process WebSocket messages concurrently
        async def receive_from_twilio():
            try:
                nonlocal queued_first_message, stream_sid, first_message
                
                while True:
                    data_str = await websocket.receive_text()
                    data = json.loads(data_str)
                    
                    if data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
                        call_sid = data["start"]["callSid"]
                        custom_parameters = data["start"].get("customParameters", {})
                        
                        logging.info(f"CallSid: {call_sid}")
                        logging.info(f"StreamSid: {stream_sid}")
                        logging.info(f"Custom Parameters: {custom_parameters}")
                        
                        # Capture callerNumber and firstMessage from custom parameters
                        caller_number = custom_parameters.get("callerNumber", "Unknown")
                        session["caller_number"] = caller_number
                        first_message = custom_parameters.get("firstMessage", "Hello, how can I assist you?")
                        
                        logging.info(f"First Message: {first_message}")
                        logging.info(f"Caller Number: {caller_number}")
                        
                        # Prepare the first message
                        queued_first_message = {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": first_message}]
                            }
                        }
                        
                        # Send the first message if OpenAI is ready
                        queued_first_message = await send_first_message()
                        
                    elif data["event"] == "media":
                        # Send audio data to OpenAI
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data["media"]["payload"]
                        }
                        await openai_ws.send(json.dumps(audio_append))
                        
            except WebSocketDisconnect:
                logging.info(f"Twilio WebSocket disconnected")
            except Exception as e:
                logging.error(f"Error in receive_from_twilio: {e}")
        
        async def receive_from_openai():
            nonlocal thread_id
            
            try:
                while True:
                    data_str = await openai_ws.recv()
                    response = json.loads(data_str)
                    
                    # Handle audio responses from OpenAI
                    if response["type"] == "response.audio.delta" and response.get("delta"):
                        await websocket.send_text(json.dumps({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": response["delta"]}
                        }))
                    
                    # Handle function calls
                    if response["type"] == "response.function_call_arguments.done":
                        logging.info(f"Function called: {response}")
                        function_name = response["name"]
                        args = json.loads(response["arguments"])
                        
                        if function_name == "question_and_answer":
                            question = args["question"]
                            try:
                                webhook_response = await send_to_webhook({
                                    "route": "3",
                                    "data1": question,
                                    "data2": thread_id
                                })
                                
                                logging.info(f"Webhook response: {webhook_response}")
                                
                                # Parse the webhook response
                                parsed_response = json.loads(webhook_response)
                                answer_message = parsed_response.get("message", "I'm sorry, I couldn't find an answer to that question.")
                                
                                # Update the threadId if provided
                                if parsed_response.get("thread"):
                                    thread_id = parsed_response["thread"]
                                    logging.info(f"Updated thread ID: {thread_id}")
                                
                                function_output_event = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "role": "system",
                                        "output": answer_message
                                    }
                                }
                                await openai_ws.send(json.dumps(function_output_event))
                                
                                # Trigger AI response
                                await openai_ws.send(json.dumps({
                                    "type": "response.create",
                                    "response": {
                                        "modalities": ["text", "audio"],
                                        "instructions": f'Respond to the user\'s question "{question}" based on this information: {answer_message}. Be concise and friendly.'
                                    }
                                }))
                            except Exception as error:
                                logging.error(f"Error processing question: {error}")
                                await send_error_response()
                                
                        elif function_name == "book_tow":
                            address = args["address"]
                            try:
                                webhook_response = await send_to_webhook({
                                    "route": "4",
                                    "data1": session["caller_number"],
                                    "data2": address
                                })
                                
                                logging.info(f"Webhook response: {webhook_response}")
                                
                                # Parse the webhook response
                                parsed_response = json.loads(webhook_response)
                                booking_message = parsed_response.get("message", "I'm sorry, I couldn't book the tow service at this time.")
                                
                                function_output_event = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "role": "system",
                                        "output": booking_message
                                    }
                                }
                                await openai_ws.send(json.dumps(function_output_event))
                                
                                # Trigger AI response
                                await openai_ws.send(json.dumps({
                                    "type": "response.create",
                                    "response": {
                                        "modalities": ["text", "audio"],
                                        "instructions": f"Inform the user about the tow booking status: {booking_message}. Be concise and friendly."
                                    }
                                }))
                            except Exception as error:
                                logging.error(f"Error booking tow: {error}")
                                await send_error_response()
                                
                        elif function_name == "make_appointment":
                            try:
                                # Call the make_appointment function to get the booking link
                                booking_link = make_appointment()
                                
                                appointment_message = f"I've generated a booking link for you. You can schedule your appointment by visiting: {booking_link}"
                                
                                function_output_event = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "role": "system", 
                                        "output": appointment_message
                                    }
                                }
                                await openai_ws.send(json.dumps(function_output_event))
                                
                                # Trigger AI response
                                await openai_ws.send(json.dumps({
                                    "type": "response.create",
                                    "response": {
                                        "modalities": ["text", "audio"],
                                        "instructions": f"Inform the user about the appointment booking link: {booking_link}. Tell them they can use this link to see available time slots and schedule an appointment. Be concise and friendly."
                                    }
                                }))
                            except Exception as error:
                                logging.error(f"Error generating appointment link: {error}")
                                await send_error_response()
                                
                        elif function_name == "get_dealers_info":
                            sql_query = args["sql_query"]
                            try:
                                query_result = get_dealers_info(sql_query)
                                
                                # Create a readable response message
                                result_message = query_result if query_result else "I couldn't find the dealer information you're looking for."
                                
                                function_output_event = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "role": "system",
                                        "output": result_message
                                    }
                                }
                                await openai_ws.send(json.dumps(function_output_event))
                                
                                # Trigger AI response
                                await openai_ws.send(json.dumps({
                                    "type": "response.create",
                                    "response": {
                                        "modalities": ["text", "audio"],
                                        "instructions": f"Share this dealer information with the customer: {result_message}. Present it in a customer-friendly way."
                                    }
                                }))
                            except Exception as error:
                                logging.error(f"Error querying dealer information: {error}")
                                await send_error_response()
                    
                    # Log agent response
                    if response["type"] == "response.done":
                        try:
                            output_items = response["response"]["output"]
                            for item in output_items:
                                for content in item.get("content", []):
                                    if content.get("transcript"):
                                        agent_message = content["transcript"]
                                        session["transcript"] += f"Agent: {agent_message}\n"
                                        logging.info(f"Agent ({session_id}): {agent_message}")
                        except (KeyError, IndexError) as e:
                            logging.error(f"Error extracting agent message: {e}")
                    
                    # Log user transcription
                    if response["type"] == "conversation.item.input_audio_transcription.completed" and response.get("transcript"):
                        user_message = response["transcript"].strip()
                        session["transcript"] += f"User: {user_message}\n"
                        logging.info(f"User ({session_id}): {user_message}")
                    
                    # Log other relevant events
                    if response["type"] in LOG_EVENT_TYPES:
                        logging.info(f"Received event: {response['type']}, {response}")
                        
            except websockets.exceptions.ConnectionClosed:
                logging.info("OpenAI WebSocket closed")
            except Exception as e:
                logging.error(f"Error in receive_from_openai: {e}")
        
        # Run the two receive functions concurrently
        receive_twilio_task = asyncio.create_task(receive_from_twilio())
        receive_openai_task = asyncio.create_task(receive_from_openai())
        
        # Wait for either task to complete (which typically means a disconnect)
        done, pending = await asyncio.wait(
            [receive_twilio_task, receive_openai_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel the remaining task
        for task in pending:
            task.cancel()
            
        # Send the transcript to the webhook
        logging.info(f"Client disconnected ({session_id}).")
        logging.info("Full Transcript:")
        logging.info(session["transcript"])
        logging.info(f"Final Caller Number: {session.get('caller_number')}")
        
        try:
            await send_to_webhook({
                "route": "2",
                "data1": session.get("caller_number"),
                "data2": session["transcript"]
            })
        except Exception as e:
            logging.error(f"Error sending transcript to webhook: {e}")
        
        # Clean up the session
        if session_id in sessions:
            del sessions[session_id]

# Run the FastAPI application with uvicorn
if __name__ == "__main__":
    import uvicorn
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    uvicorn.run(app, host="0.0.0.0", port=PORT)