from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.util.config import BaseProxyConfig
from mautrix.types import MessageType, EventType, Format, TextMessageEventContent
from mautrix.util import markdown
import re
import json
import logging
from typing import Tuple
import datetime
import difflib

from .config import Config
from .client import OpenRouterClient, OpenRouterError
from .tools import available_tools, function_map, vat
from .utils import (
    format_message_history,
    parse_function_call,
    truncate_message_history,
    clean_markdown,
    format_error_message
)

class ChatGPTBot(Plugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assistant_replies = {}
        self.max_messages = 100
        self.log = logging.getLogger("maubot.chatgpt")
        self.log.setLevel(logging.DEBUG)

    async def start(self) -> None:
        self.log.info("Starting ChatGPT bot...")
        self.config.load_and_update()
        self.log.debug(f"Loaded config: bot_name={self.config['bot-name']}, model={self.config['model']}")
        self.log.debug(f"Max price per token: {self.config['max_price_per_token']}")

        self.openrouter_client = OpenRouterClient(
            api_key=self.config["api-key"],
            site_url=self.config["site_url"],
            site_name=self.config["site_name"],
            config=self.config
        )
        self.log.info("OpenRouter client initialized")

        # Set global VAT rate for electricity prices
        global vat
        vat = self.config["vat"]
        self.log.debug(f"Set global VAT rate to {vat}")

    async def get_conversation_history(self, evt: MessageEvent, event_id: str) -> list:
        """Get the conversation history for a given event."""
        history = []
        bot_name = self.config["bot-name"]
        pattern = re.compile(r"^@([a-zA-Z0-9]+):")
        userIdPattern = re.compile(fr'<a href="https://matrix\.to/#/{re.escape(bot_name)}">.*?</a>:? ?')

        while event_id:
            event = await self.client.get_event(evt.room_id, event_id)
            if event["type"] == EventType.ROOM_MESSAGE:
                sender_name = event["sender"]
                match = pattern.search(sender_name)
                filtered_name = match.group(1) if match else ""
                role = "assistant" if sender_name == bot_name else "user"
                if sender_name == bot_name:
                    content = self.assistant_replies.get(event_id, event['content']['body'])
                else:
                    content = userIdPattern.sub('', event['content']['formatted_body'] if event['content']['formatted_body'] else event['content']['body'])
                history.insert(0, {"role": role, "name": filtered_name, "content": content})

            if event.content.get("_relates_to") and event.content["_relates_to"]["in_reply_to"].get("event_id"):
                event_id = event["content"]["_relates_to"]["in_reply_to"]["event_id"]
            else:
                break

        return history

    @command.new("chatgpt", aliases=["c"], help="Chat with ChatGPT from Matrix.")
    @command.argument("query", pass_raw=True)
    async def chat_gpt_handler(self, evt: MessageEvent, query: str) -> None:
        """Handle the chatgpt command."""
        query = query.strip()
        if not query:
            await evt.reply("Please provide a message to chat with ChatGPT.")
            return

        if evt.content.get("_relates_to") and evt.content["_relates_to"]["in_reply_to"].get("event_id"):
            in_reply_to_event_id = evt.content["_relates_to"]["in_reply_to"]["event_id"]
            conversation_history = await self.get_conversation_history(evt, in_reply_to_event_id)
        else:
            conversation_history = []

        event_id = await evt.reply("…", allow_html=True)
        await self.chat_gpt_request(query, conversation_history, evt, event_id)

    @command.passive(".*")
    async def on_message(self, evt: MessageEvent, match: Tuple[str]) -> None:
        """Handle passive messages that mention the bot or reply to its messages."""
        # Ignore messages from the bot itself
        if evt.sender == self.config["bot-name"]:
            return

        if evt.content.get("msgtype") == MessageType.TEXT:
            formatted_body = evt.content.get("formatted_body", "") or evt.content["body"]
            bot_name = self.config["bot-name"]
            pattern = re.compile(fr'<a href="https://matrix\.to/#/{re.escape(bot_name)}">.*?</a>:? ?')

            # Check if this is a reply to the bot's message
            is_reply_to_bot = False
            in_reply_to_event_id = None
            if evt.content.get("_relates_to") and evt.content["_relates_to"]["in_reply_to"].get("event_id"):
                in_reply_to_event_id = evt.content["_relates_to"]["in_reply_to"]["event_id"]
                try:
                    in_reply_to_event = await self.client.get_event(evt.room_id, in_reply_to_event_id)
                    is_reply_to_bot = in_reply_to_event.sender == bot_name
                except Exception:
                    pass

            # Check if the bot is mentioned
            is_mentioned = bool(pattern.search(formatted_body))

            # Only respond if the message is a reply to the bot or mentions it
            if not (is_reply_to_bot or is_mentioned):
                return

            # Get conversation history if this is a reply
            conversation_history = []
            if is_reply_to_bot and in_reply_to_event_id:
                conversation_history = await self.get_conversation_history(evt, in_reply_to_event_id)

            # Remove bot mention from the message
            if is_mentioned:
                query = pattern.sub('', formatted_body)
                # Also remove any trailing colon and whitespace
                query = re.sub(r'^\s*:?\s*', '', query)
                # Convert any remaining HTML to plain text
                query = re.sub(r'<[^>]+>', '', query).strip()
            else:
                query = evt.content["body"]

            # Send the response
            event_id = await evt.reply("…", allow_html=True)
            await self.chat_gpt_request(query, conversation_history, evt, event_id)

    async def chat_gpt_request(self, query: str, conversation_history: list, evt: MessageEvent, event_id: str) -> None:
        """Process a chat request."""
        current_content = ""
        last_update = datetime.datetime.now()
        update_interval = datetime.timedelta(milliseconds=1000)  # Update every 300ms at most

        try:
            self.log.info(f"Processing chat request from {evt['sender']}")
            self.log.debug(f"Original query: {query}")

            # Get user info
            sender_name = evt["sender"]
            pattern = re.compile(r"^@([a-zA-Z0-9]+):")
            match = pattern.search(sender_name)
            filtered_name = match.group(1) if match else ""
            self.log.debug(f"Filtered sender name: {filtered_name}")

            # Get current time in Helsinki timezone
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            helsinki_offset = datetime.timedelta(hours=2)  # Adjust for Helsinki timezone
            helsinki_now = utc_now.astimezone(datetime.timezone(helsinki_offset))
            current_date = helsinki_now.strftime("%A %B %d, %Y")
            current_time = helsinki_now.strftime("%H:%M %Z")

            # Prepare messages
            messages = [
                {"role": "system", "content": f"Your role is to be a chatbot called Matrix. Prefer metric units. Do not use latex, always use markdown. Today is {current_date} and time is {current_time}."},
            ]

            # Add conversation history if exists
            if conversation_history:
                self.log.debug(f"Adding conversation history: {len(conversation_history)} messages")
                messages.extend(conversation_history)

            # Add the current query
            messages.extend([{"role": "user", "name": filtered_name, "content": query}])
            # Look for model override
            pattern = re.compile(r"!([\w/:.-]+)")  # Match allowed model string
            override_model = None
            online_requested = False
            for message in messages:
                content = message.get("content")
                if not content:
                    continue
                match = pattern.search(content)
                if match:
                    raw_override = match.group(1)
                    if ":online" in raw_override:
                        online_requested = True
                        raw_override = raw_override.replace(":online", "")
                    override_model = raw_override
                    self.log.info(f"Found model override: {override_model}" + (f" with :online" if online_requested else ""))
                    message["content"] = re.sub(pattern, "", content, count=1).strip()
                    # Fetch available models and pick the closest match
                    all_models_json = self.openrouter_client.fetch_all_models()
                    all_ids = [model["id"] for model in all_models_json.get("data", [])]
                    closest_matches = difflib.get_close_matches(override_model, all_ids, n=1, cutoff=0.3)
                    if closest_matches:
                        self.log.info(f"Replacing override '{override_model}' with closest match '{closest_matches[0]}'")
                        override_model = closest_matches[0]
                    else:
                        self.log.debug("No close match found for override; using provided override")
                    # If :online was requested, adjust the model name accordingly
                    if online_requested:
                        if override_model.endswith(":free"):
                            override_model = override_model[:-5] + ":online"
                        elif not override_model.endswith(":online"):
                            override_model = f"{override_model}:online"
                    break

            selected_model = override_model if override_model else self.config["model"]
            # Only add the free suffix if :online was not requested
            if not online_requested and not selected_model.endswith(":free"):
                free_candidate = f"{selected_model}:free"
                all_models_json = self.openrouter_client.fetch_all_models()
                all_ids = [model["id"] for model in all_models_json.get("data", [])]
                if free_candidate in all_ids:
                    selected_model = free_candidate
            self.log.info(f"Using model: {selected_model}")
            await self._edit(evt.room_id, event_id, f"Using model: {selected_model}")

            # Log the full message context being sent
            self.log.debug(f"Full message context being sent to API: {json.dumps(messages, indent=2)}")

            # Create chat completion with streaming
            self.log.debug("Making streaming API request to OpenRouter...")
            stream = self.openrouter_client.create_chat_completion(
                messages=messages,
                model=selected_model,
                temperature=0.7,
                tools=available_tools,
                stream=True,
                include_reasoning=True
            )

            async def process_chunks():
                nonlocal current_content, last_update
                async for chunk in stream:
                    self.log.debug(f"Received chunk: {chunk}")
                    if not isinstance(chunk, dict):
                        chunk = json.loads(chunk.model_dump_json())

                    if "choices" in chunk and chunk["choices"]:
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"] is not None:
                            current_content += delta["content"]
                        elif "tool_calls" in delta and delta["tool_calls"]:
                            # Append tool call details as JSON so that function call can be parsed later
                            current_content += json.dumps(delta["tool_calls"][0]["function"])
                        # Added support for reasoning: format as markdown italic for Matrix
                        # Use separate accumulators for reasoning and content.
                        if "content" in delta and delta["content"] is not None:
                            # If content starts, append it.
                            if "accumulated_content" not in locals():
                                accumulated_content = ""
                            if "accumulated_reasoning" not in locals():
                                accumulated_reasoning = ""
                            accumulated_content += delta["content"]
                        else:
                            # No content; accumulate reasoning.
                            if "accumulated_reasoning" not in locals():
                                accumulated_reasoning = ""
                            if delta.get("reasoning") is not None:
                                accumulated_reasoning += f"{delta['reasoning']}"

                        # Determine what to preview:
                        if "accumulated_content" not in locals() or not accumulated_content:
                            # Only reasoning so far; show it as-is.
                            preview = "*Reasoning...*<br>" + accumulated_reasoning.replace("\n", "<br>")
                        else:
                            # Content has started; display content normally and move reasoning into a <details> block if present.
                            preview = accumulated_content
                            if "accumulated_reasoning" in locals() and accumulated_reasoning:
                                preview += f"<br><details><summary>Reasoning</summary><br>{accumulated_reasoning.replace('\n', '<br>')}<br></details>"

                        now = datetime.datetime.now()
                        if now - last_update >= update_interval and (delta.get("content") or delta.get("reasoning")):
                            await self._edit(evt.room_id, event_id, preview)
                            last_update = now

                # Final update with complete content
                if ("accumulated_content" in locals() and accumulated_content) or ("accumulated_reasoning" in locals() and accumulated_reasoning):
                    if "accumulated_content" in locals() and accumulated_content:
                        final = accumulated_content
                        if "accumulated_reasoning" in locals() and accumulated_reasoning:
                            final += f"<br><details><summary>Reasoning</summary><br>{accumulated_reasoning.replace('\n', '<br>')}<br></details>"
                    else:
                        final = accumulated_reasoning.replace("\n", "<br>")
                    self.log.debug(f"Final streaming complete content: {final}")
                    await self._edit(evt.room_id, event_id, final)

            # Process the initial response
            await process_chunks()

            # Check for function calls in the complete response
            try:
                function_call = json.loads(current_content)
                if not (isinstance(function_call, dict) and "name" in function_call and "arguments" in function_call):
                    function_call = None
            except json.JSONDecodeError:
                function_call = None
            if function_call:
                self.log.info(f"Function call detected: {function_call['name']}")
                # Get the function and its arguments
                func_name = function_call["name"]
                func_args = function_call["arguments"]
                # Convert string arguments to dict if necessary
                if isinstance(func_args, str):
                    try:
                        func_args = json.loads(func_args)
                    except Exception:
                        func_args = {"raw": func_args}
                self.log.debug(f"Function arguments: {json.dumps(func_args, indent=2)}")
                if func_name in function_map:
                    # Add user info to arguments
                    func_args["user"] = sender_name
                    # Execute the function
                    self.log.debug(f"Executing function {func_name} with args: {json.dumps(func_args, indent=2)}")
                    function_response = function_map[func_name](**func_args)
                    self.log.debug(f"Function response: {function_response}")

                    # Add function result to messages
                    messages.append({
                        "role": "assistant",
                        "content": current_content,
                        "tool_calls": [{
                            "id": "1",  # We don't have a real ID in streaming mode
                            "type": "function",
                            "function": {
                                "name": func_name,
                                "arguments": json.dumps(func_args)
                            }
                        }]
                    })
                    messages.append({
                        "role": "tool",
                        "content": str(function_response),
                        "tool_call_id": "1"
                    })

                    # Get a new streaming response that includes the function result
                    self.log.debug("Making second streaming API request with function results...")
                    current_content = ""  # Reset content for the second response
                    stream = self.openrouter_client.create_chat_completion(
                        messages=messages,
                        model=selected_model,
                        temperature=0.7,
                        stream=True
                    )
                    await process_chunks()

        except OpenRouterError as e:
            self.log.error(f"OpenRouter API Error: {str(e)}", exc_info=True)
            error_msg = f"OpenRouter API Error: {str(e)}"
            self.log.debug(f"Sending error message to user: {error_msg}")
            await self._edit(evt.room_id, event_id, error_msg)
        except Exception as e:
            self.log.error(f"Unexpected error: {str(e)}", exc_info=True)
            error_msg = f"Error: {str(e)}"
            self.log.debug(f"Sending error message to user: {error_msg}")
            await self._edit(evt.room_id, event_id, error_msg)

    async def _edit(self, room_id: str, event_id: str, text: str) -> None:
        """Edit a message with new content."""
        content = TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            body=text,
            format=Format.HTML,
            formatted_body=markdown.render(text, allow_html=True)
        )
        content.set_edit(event_id)
        await self.client.send_message(room_id, content)
        self.assistant_replies[event_id] = text

        # Maintain message limit
        if len(self.assistant_replies) > self.max_messages:
            oldest_event_id = next(iter(self.assistant_replies))
            del self.assistant_replies[oldest_event_id]

    @classmethod
    def get_config_class(cls) -> type[BaseProxyConfig]:
        return Config
