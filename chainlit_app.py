"""
Chainlit application for OpenAI Realtime API integration.
"""

import os
import asyncio
import traceback
import chainlit as cl
from uuid import uuid4
from chainlit.logger import logger
from dotenv import load_dotenv

from realtime.client import RealtimeClient
from config.system_prompts import get_system_prompt
from tools import tools

# Load environment variables
load_dotenv()

async def setup_openai_realtime():
    """Instantiate and configure the OpenAI Realtime Client"""
    openai_realtime = RealtimeClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        system_message=get_system_prompt("chainlit")
    )
    cl.user_session.set("track_id", str(uuid4()))

    async def handle_conversation_updated(event):
        """Currently used to stream audio back to the client."""
        delta = event.get("delta")
        if delta:
            # Only one of the following will be populated for any given event
            if "audio" in delta:
                audio = delta["audio"]  # Int16Array, audio added
                await cl.context.emitter.send_audio_chunk(
                    cl.OutputAudioChunk(
                        mimeType="pcm16",
                        data=audio,
                        track=cl.user_session.get("track_id"),
                    )
                )
            if "transcript" in delta:
                transcript = delta["transcript"]  # string, transcript added
                pass
            if "arguments" in delta:
                arguments = delta["arguments"]  # string, function arguments added
                pass

    async def handle_item_completed(item):
        """Used to populate the chat context with transcription once an item is completed."""
        pass

    async def handle_conversation_interrupt(event):
        """Used to cancel the client previous audio playback."""
        cl.user_session.set("track_id", str(uuid4()))
        await cl.context.emitter.send_audio_interrupt()

    async def handle_error(event):
        logger.error(event)

    openai_realtime.on("conversation.updated", handle_conversation_updated)
    openai_realtime.on("conversation.item.completed", handle_item_completed)
    openai_realtime.on("conversation.interrupted", handle_conversation_interrupt)
    openai_realtime.on("error", handle_error)

    cl.user_session.set("openai_realtime", openai_realtime)
    
    # Register all tools
    coros = [
        openai_realtime.add_tool(tool_def, tool_handler)
        for tool_def, tool_handler in tools
    ]
    await asyncio.gather(*coros)


@cl.on_chat_start
async def start():
    await cl.Message(content="Hello! I'm here. Press `P` to talk!").send()
    await setup_openai_realtime()


@cl.on_message
async def on_message(message: cl.Message):
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime and openai_realtime.is_connected():
        # TODO: Try image processing with message.elements
        await openai_realtime.send_user_message_content(
            [{"type": "input_text", "text": message.content}]
        )
    else:
        await cl.Message(
            content="Please activate voice mode before sending messages!"
        ).send()


@cl.on_audio_start
async def on_audio_start():
    try:
        openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
        await openai_realtime.connect()
        logger.info("Connected to OpenAI realtime")
        return True
    except Exception as e:
        print(traceback.format_exc())
        await cl.ErrorMessage(
            content=f"Failed to connect to OpenAI realtime: {e}"
        ).send()
        return False


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.InputAudioChunk):
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime.is_connected():
        await openai_realtime.append_input_audio(chunk.data)
    else:
        logger.info("RealtimeClient is not connected")


@cl.on_audio_end
@cl.on_chat_end
@cl.on_stop
async def on_end():
    openai_realtime: RealtimeClient = cl.user_session.get("openai_realtime")
    if openai_realtime and openai_realtime.is_connected():
        await openai_realtime.disconnect()

