import os
import asyncio
from .event_handler import RealtimeEventHandler
from .api import RealtimeAPI
from .conversation import RealtimeConversation
from .utils import get_realtime_instructions

class RealtimeClient(RealtimeEventHandler):
    def __init__(self, url=None, api_key=None, system_message=None):
        super().__init__()
        self.default_session_config = {
            "modalities": ["text", "audio"],
            "instructions": system_message or get_realtime_instructions(),
            "voice": "shimmer",
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            "turn_detection": {"type": "server_vad"},
            "tools": [],
            "tool_choice": "auto",
            "temperature": 0.8,
            "max_response_output_tokens": 4096,
        }
        self.session_config = {}
        self.transcription_models = [{"model": "whisper-1"}]
        self.default_server_vad_config = {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 200,
        }
        self.realtime = RealtimeAPI(
            url=url,
            api_key=api_key,
        )
        self.conversation = RealtimeConversation()
        self._reset_config()
        self._add_api_event_handlers()

    def _reset_config(self):
        self.session_created = False
        self.tools = {}
        self.session_config = self.default_session_config.copy()
        self.input_audio_buffer = bytearray()
        return True

    def _add_api_event_handlers(self):
        self.realtime.on("client.*", self._log_event)
        self.realtime.on("server.*", self._log_event)
        self.realtime.on("server.session.created", self._on_session_created)
        self.realtime.on("server.response.created", self._process_event)
        self.realtime.on("server.response.output_item.added", self._process_event)
        self.realtime.on("server.response.content_part.added", self._process_event)
        self.realtime.on("server.input_audio_buffer.speech_started", self._on_speech_started)
        self.realtime.on("server.input_audio_buffer.speech_stopped", self._on_speech_stopped)
        self.realtime.on("server.conversation.item.created", self._on_item_created)
        self.realtime.on("server.conversation.item.truncated", self._process_event)
        self.realtime.on("server.conversation.item.deleted", self._process_event)
        self.realtime.on(
            "server.conversation.item.input_audio_transcription.completed",
            self._process_event,
        )
        self.realtime.on("server.response.audio_transcript.delta", self._process_event)
        self.realtime.on("server.response.audio.delta", self._process_event)
        self.realtime.on("server.response.text.delta", self._process_event)
        self.realtime.on("server.response.function_call_arguments.delta", self._process_event)
        self.realtime.on("server.response.output_item.done", self._on_output_item_done)

    def _log_event(self, event):
        realtime_event = {
            "time": datetime.utcnow().isoformat(),
            "source": "client" if event["type"].startswith("client.") else "server",
            "event": event,
        }
        self.dispatch("realtime.event", realtime_event)

    def _on_session_created(self, event):
        self.session_created = True

    def _process_event(self, event, *args):
        item, delta = self.conversation.process_event(event, *args)
        if item:
            self.dispatch("conversation.updated", {"item": item, "delta": delta})
        return item, delta

    def _on_speech_started(self, event):
        self._process_event(event)
        self.dispatch("conversation.interrupted", event)

    def _on_speech_stopped(self, event):
        self._process_event(event, self.input_audio_buffer)

    def _on_item_created(self, event):
        item, delta = self._process_event(event)
        self.dispatch("conversation.item.appended", {"item": item})
        if item and item["status"] == "completed":
            self.dispatch("conversation.item.completed", {"item": item})

    async def _on_output_item_done(self, event):
        item, delta = self._process_event(event)
        if item and item["status"] == "completed":
            self.dispatch("conversation.item.completed", {"item": item})
        if item and item.get("formatted", {}).get("tool"):
            await self._call_tool(item["formatted"]["tool"])

    async def _call_tool(self, tool):
        try:
            json_arguments = json.loads(tool["arguments"])
            tool_config = self.tools.get(tool["name"])
            if not tool_config:
                raise Exception(f'Tool "{tool["name"]}" has not been added')
            result = await tool_config["handler"](**json_arguments)
            await self.realtime.send(
                "conversation.item.create",
                {
                    "item": {
                        "type": "function_call_output",
                        "call_id": tool["call_id"],
                        "output": json.dumps(result),
                    }
                },
            )
        except Exception as e:
            logger.error(f"Tool call error: {json.dumps({"error": str(e)})}")
            await self.realtime.send(
                "conversation.item.create",
                {
                    "item": {
                        "type": "function_call_output",
                        "call_id": tool["call_id"],
                        "output": json.dumps({"error": str(e)}),
                    }
                },
            )
        await self.create_response()

    def is_connected(self):
        return self.realtime.is_connected()

    def reset(self):
        self.disconnect()
        self.realtime.clear_event_handlers()
        self._reset_config()
        self._add_api_event_handlers()
        return True

    async def connect(self):
        if self.is_connected():
            raise Exception("Already connected, use .disconnect() first")
        await self.realtime.connect()
        await self.update_session()
        return True

    async def wait_for_session_created(self):
        if not self.is_connected():
            raise Exception("Not connected, use .connect() first")
        while not self.session_created:
            await asyncio.sleep(0.001)
        return True

    async def disconnect(self):
        self.session_created = False
        self.conversation.clear()
        if self.realtime.is_connected():
            await self.realtime.disconnect()

    def get_turn_detection_type(self):
        return self.session_config.get("turn_detection", {}).get("type")

    async def add_tool(self, definition, handler):
        if not definition.get("name"):
            raise Exception("Missing tool name in definition")
        name = definition["name"]
        if name in self.tools:
            raise Exception(
                f'Tool "{name}" already added. Please use .removeTool("{name}") before trying to add again.'
            )
        if not callable(handler):
            raise Exception(f'Tool "{name}" handler must be a function')
        self.tools[name] = {"definition": definition, "handler": handler}
        await self.update_session()
        return self.tools[name]

    def remove_tool(self, name):
        if name not in self.tools:
            raise Exception(f'Tool "{name}" does not exist, can not be removed.')
        del self.tools[name]
        return True

    async def delete_item(self, id):
        await self.realtime.send("conversation.item.delete", {"item_id": id})
        return True

    async def update_session(self, **kwargs):
        self.session_config.update(kwargs)
        use_tools = [
            {**tool_definition, "type": "function"} for tool_definition in self.session_config.get("tools", [])
        ] + [{**self.tools[key]["definition"], "type": "function"} for key in self.tools]
        session = {**self.session_config, "tools": use_tools}
        if self.realtime.is_connected():
            await self.realtime.send("session.update", {"session": session})
        return True

    async def create_conversation_item(self, item):
        await self.realtime.send("conversation.item.create", {"item": item})

    async def send_user_message_content(self, content=[]):
        if content:
            for c in content:
                if c["type"] == "input_audio":
                    if isinstance(c["audio"], (bytes, bytearray)):
                        c["audio"] = array_buffer_to_base64(c["audio"])
            await self.realtime.send(
                "conversation.item.create",
                {
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": content,
                    }
                },
            )
        await self.create_response()
        return True

    async def append_input_audio(self, array_buffer):
        if len(array_buffer) > 0:
            await self.realtime.send(
                "input_audio_buffer.append",
                {
                    "audio": array_buffer_to_base64(np.array(array_buffer)),
                },
            )
            self.input_audio_buffer.extend(array_buffer)
        return True

    async def create_response(self):
        if self.get_turn_detection_type() is None and len(self.input_audio_buffer) > 0:
            await self.realtime.send("input_audio_buffer.commit")
            self.conversation.queue_input_audio(self.input_audio_buffer)
            self.input_audio_buffer = bytearray()
        await self.realtime.send("response.create")
        return True

    async def cancel_response(self, id=None, sample_count=0):
        if not id:
            await self.realtime.send("response.cancel")
            return {"item": None}
        else:
            item = self.conversation.get_item(id)
            if not item:
                raise Exception(f'Could not find item "{id}"')
            if item["type"] != "message":
                raise Exception('Can only cancelResponse messages with type "message"')
            if item["role"] != "assistant":
                raise Exception('Can only cancelResponse messages with role "assistant"')
            await self.realtime.send("response.cancel")
            audio_index = next((i for i, c in enumerate(item["content"]) if c["type"] == "audio"), -1)
            if audio_index == -1:
                raise Exception("Could not find audio on item to cancel")
            await self.realtime.send(
                "conversation.item.truncate",
                {
                    "item_id": id,
                    "content_index": audio_index,
                    "audio_end_ms": int((sample_count / self.conversation.default_frequency) * 1000),
                },
            )
            return {"item": item}

    async def wait_for_next_item(self):
        event = await self.wait_for_next("conversation.item.appended")
        return {"item": event["item"]}

    async def wait_for_next_completed_item(self):
        event = await self.wait_for_next("conversation.item.completed")
        return {"item": event["item"]}

