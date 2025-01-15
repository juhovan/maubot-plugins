import aiohttp
from typing import Type
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import TextMessageEventContent, MessageType, EventType, Format, EventID, RelatesTo, RelationType
from mautrix.util import markdown
from openai import OpenAI
import fmi_weather_client as fmi
from fmi_weather_client.errors import ClientError, ServerError
import time
import re
import datetime
from typing import Tuple
import json

import requests

vat = 1

weather_map = {
    1: "Selkeää",
    2: "Enimmäkseen selkeää",
    4: "Puolipilvistä",
    6: "Enimmäkseen pilvistä",
    7: "Pilvistä",
    9: "Sumua",
    71: "Yksittäisiä ukkoskuuroja",
    74: "Paikoin ukkoskuuroja",
    77: "Ukkoskuuroja",
    21: "Yksittäisiä sadekuuroja",
    24: "Paikoin sadekuuroja",
    14: "Sadekuuroja Jäätävää tihkua",
    17: "Jäätävää sadetta",
    11: "Tihkusadetta",
    31: "Puolipilvistä ja ajoittain heikkoa vesisadetta",
    34: "Enimmäkseen pilvistä ja ajoittain heikkoa vesisadetta",
    37: "Heikkoa vesisadetta",
    32: "Puolipilvistä ja ajoittain kohtalaista vesisadetta",
    35: "Enimmäkseen pilvistä ja ajoittain kohtalaista vesisadetta",
    38: "Kohtalaista vesisadetta",
    33: "Puolipilvistä ja ajoittain voimakasta vesisadetta",
    36: "Enimmäkseen pilvistä ja ajoittain voimakasta vesisadetta",
    39: "Voimakasta vesisadetta",
    41: "Puolipilvistä ja ajoittain heikkoa räntäsadetta tai räntäkuuroja",
    44: "Enimmäkseen pilvistä ja ajoittain heikkoa räntäsadetta tai räntäkuuroja",
    47: "Heikkoa räntäsadetta",
    42: "Puolipilvistä ja ajoittain kohtalaista räntäsadetta tai räntäkuuroja",
    45: "Enimmäkseen pilvistä ja ajoittain kohtalaista räntäsadetta tai räntäkuuroja",
    48: "Kohtalaista räntäsadetta",
    43: "Puolipilvistä ja ajoittain voimakasta räntäsadetta tai räntäkuuroja",
    46: "Enimmäkseen pilvistä ja ajoittain voimakasta räntäsadetta tai räntäkuuroja",
    49: "Voimakasta räntäsadetta",
    51: "Puolipilvistä ja ajoittain heikkoa lumisadetta tai lumikuuroja",
    54: "Enimmäkseen pilvistä ja ajoittain heikkoa lumisadetta tai lumikuuroja",
    57: "Heikkoa lumisadetta",
    52: "Puolipilvistä ja ajoittain kohtalaista lumisadetta tai lumikuuroja",
    55: "Enimmäkseen pilvistä ja ajoittain kohtalaista lumisadetta tai lumikuuroja",
    58: "Kohtalaista lumisadetta",
    53: "Puolipilvistä ja ajoittain sakeaa lumisadetta tai lumikuuroja",
    56: "Enimmäkseen pilvistä ja ajoittain sakeaa lumisadetta tai lumikuuroja",
    59: "Runsasta lumisadetta",
    61: "Yksittäisiä raekuuroja",
    64: "Paikoin raekuuroja",
    67: "Raekuuroja"
}
def weather(user, location):
    try:
        current_data = fmi.weather_by_place_name(location)
    except ClientError as err:
        print(f"Client error with status {err.status_code}: {err.message}")
    except ServerError as err:
        print(f"Server error with status {err.status_code}: {err.body}")

    try:
        forecast_data = fmi.forecast_by_place_name(location, timestep_hours = 6)
    except ClientError as err:
        print(f"Client error with status {err.status_code}: {err.message}")
    except ServerError as err:
        print(f"Server error with status {err.status_code}: {err.body}")

    # Extract the relevant information from the current weather data
    current_temperature = current_data.data.temperature
    current_feels_like = current_data.data.feels_like
    current_humidity = current_data.data.humidity
    try:
        current_weather = weather_map[current_data.data.symbol.value if current_data.data.symbol.value < 100 else current_data.data.symbol.value - 100]
    except:
        current_weather = "Tuntematon"
    current_wind_speed = current_data.data.wind_speed
    current_wind_deg = current_data.data.wind_direction
    current_gust_speed = current_data.data.wind_gust
    current_clouds = current_data.data.cloud_cover
    current_pressure = current_data.data.pressure
    current_precipitation = current_data.data.precipitation_amount

    # Format the current weather as a string
    current_weather_str = f"Tämänhetkinen sää: {current_temperature.value}{current_temperature.unit} (Tuntuu kuin {current_feels_like.value:2f}{current_feels_like.unit}), {current_weather}, {current_humidity.value}{current_humidity.unit} ilmankosteus, tuulen nopeus: {current_wind_speed.value}{current_wind_speed.unit}, tuulen suunta {current_wind_deg.value}{current_wind_deg.unit} (Puuskissa {current_gust_speed.value}{current_gust_speed.unit}), Pilvisyys: {current_clouds.value}{current_clouds.unit}, Sademäärä: {current_precipitation.value}{current_precipitation.unit}, ilmanpaine {current_pressure.value}{current_precipitation.unit}"

    # Extract the relevant information from the forecasted weather data
    forecasted_weather_str = "Ennustettu sää:\n"
    for forecast in forecast_data.forecasts:
        forecast_time = forecast.time
        forecast_temperature = forecast.temperature
        forecast_humidity = forecast.humidity
        try:
            forecast_weather = weather_map[forecast.symbol.value if forecast.symbol.value < 100 else forecast.symbol.value - 100]
        except:
            forecast_weather = "Tuntematon"
        forecast_wind_speed = forecast.wind_speed
        forecast_precipitation = forecast.precipitation_amount

        # Get the weekday for the forecasted time
        weekday = forecast_time.strftime("%A")

        forecasted_weather_str += f"{weekday} - {forecast_time}: {forecast_temperature.value}{forecast_temperature.unit}, {forecast_weather}, {forecast_humidity.value}{forecast_humidity.unit} ilmankosteus, Tuulen nopeus: {forecast_wind_speed.value}{forecast_wind_speed.unit}, Sademäärä: {forecast_precipitation.value}{forecast_precipitation.unit}\n"

    # Combine the current and forecasted weather into a single string
    weather_str = f"{current_weather_str}\n\n{forecasted_weather_str}"

    return weather_str

fetch_electricity_prices_cache = {}
def fetch_electricity_prices(user, date):
    # Define the base URL template
    url_template = "https://www.sahkohinta-api.fi/api/v1/halpa?tunnit=24&tulos=sarja&aikaraja={date}"

    if date == "today":
        # Get today's date
        today = datetime.datetime.today()
        date = today.strftime('%Y-%m-%d')
    elif date == "tomorrow":
        # Get tomorrow's date
        today = datetime.datetime.today()
        tomorrow = today + datetime.timedelta(days=1)
        date = tomorrow.strftime('%Y-%m-%d')

    # Check if the data is cached and valid
    if date in fetch_electricity_prices_cache:
        cached_data = fetch_electricity_prices_cache[date]
        print("Returning cached data")
        return cached_data['data']

    url = url_template.format(date=date)

    # Fetch the data
    response = requests.get(url)
    if response.status_code == 200:
        price_data = response.json()
    else:
        return f"Error: Unable to fetch data for {date} (status code {response.status_code}) Maybe date is in the future? Prices for the next day are available around 14:00 UTC+2."

    # Extract the 'hinta' values and convert them to floats
    prices = [float(item['hinta'])*vat for item in price_data]

    # Calculate the average of 'hinta'
    average_price = sum(prices) / len(prices)

    # Now convert the parsed data into a string
    formatted_string = f"Sähkön hinta on keskimäärin {average_price}. Kaikki hinnat ovat pyöristettyjä sentteinä. Hinnat sisältävät arvonlisäveron {round(vat*100-100,2)}%. Älä mainitse verotuksesta ellei erikseen kysytä. Kellonajat ovat Suomen aikaa. Vältä koko listan tulostamista käyttäjälle ja pyri kirjoittamaan kiinnostava kooste:\n"
    for entry in price_data:
        price = round(float(entry['hinta'])*vat,2)
        formatted_string += f"{entry['aikaleima_suomi']}: {price} c/kWh"
        if price > average_price:
            formatted_string += " (Kalliimpi kuin keskiarvo)"
        elif price < average_price:
            formatted_string += " (Halvempi kuin keskiarvo)"
        formatted_string += "\n"

    # Store the fetched data in cache with a timestamp
    fetch_electricity_prices_cache[date] = {
        'data': formatted_string
    }

    return formatted_string

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("api-key")
        helper.copy("bot-name")
        helper.copy("model")
        helper.copy("vat")

class ChatGPTBot(Plugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assistant_replies = {}
        self.max_messages = 100  # Set the maximum number of stored messages

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()
        global vat
        vat = self.config["vat"]

    async def chat_gpt_request(self, query: str, conversation_history: list, evt: MessageEvent, event_id: EventID) -> None:
        sender_name = evt["sender"]
        pattern = re.compile(r"^@([a-zA-Z0-9]+):")
        match = pattern.search(sender_name)
        filtered_name = match.group(1) if match else ""

        # Get the current time in UTC
        utc_now = datetime.datetime.now(datetime.timezone.utc)

        # Define a timezone offset (e.g., Europe/Helsinki UTC+2, but adjusting for daylight saving time)
        # Let's assume we are using UTC+2 for simplicity (during standard time)
        # For daylight saving time, you would use UTC+3. You can adjust this manually.
        helsinki_offset = datetime.timedelta(hours=2)  # Adjust for the Helsinki time zone, for standard time
        helsinki_now = utc_now.astimezone(datetime.timezone(helsinki_offset))

        current_date = helsinki_now.strftime("%A %B %d, %Y")
        current_time = helsinki_now.strftime("%H:%M %Z")
        messages = [
            {"role": "system", "content": f"You are ChatGPT, a large language model trained by OpenAI. Your role is to be a chatbot called Matrix. Today is {current_date} and time is {current_time}. Prefer metric units. Do not use latex, always use markdown."},
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Get the current and forecasted weather in a given location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city, default to Espoo, Finland",
                            }
                        },
                        "required": ["location"],
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_electricity_prices",
                    "description": "Get the electricity prices in Finland in cents for a given date",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "The date for which to get the electricity prices (can be 'today' or 'tomorrow' or a specific date formatted as YYYY-MM-DD)",
                            }
                        },
                        "required": ["date"],
                    }
                }
            }
        ]

        if conversation_history:
            # Append conversation history to messages
            messages.extend(conversation_history)

        messages.extend([{"role": "user", "name": filtered_name, "content": query}])

        start_time = time.time()

        max_retries = 5
        for i2 in range(4 + max_retries + 1):
            for retry in range(max_retries + 1):  # +1 to include the initial attempt
                try:
                    client = OpenAI(api_key=self.config["api-key"])
                    chat_completion = client.chat.completions.create(
                        model=self.config["model"],
                        messages=messages,
                        tools=tools,
                        stream=True,
                    )
                    break  # If successful, exit the loop
                except Exception as e:
                    if retry < max_retries:
                        # Handle the exception and retry
                        print(f"Retry {retry + 1}/{max_retries}: {e}")
                    else:
                        await self._edit(evt.room_id, event_id, f"OpenAI API Error: {e}")
                        return

            # create variables to collect the stream of chunks
            collected_chunks = []
            collected_messages = []
            collected_functions = {}
            delay = 1

            # iterate through the stream of events
            #try:
            for i, chunk in enumerate(chat_completion):
                self.log.debug(chunk)
                chunk_time = time.time() - start_time  # calculate the time delay of the chunk
                collected_chunks.append(chunk)  # save the event response
                chunk_message = chunk.choices[0].delta.content  # extract the message
                if chunk.choices[0].delta.tool_calls != None:
                    for tool_call in chunk.choices[0].delta.tool_calls:
                        if tool_call.id is not None:
                            tool_call_id = tool_call.id
                        if tool_call.function.name != None:
                            collected_functions[tool_call_id] = {}
                            collected_functions[tool_call_id]["name"] = tool_call.function.name
                            collected_functions[tool_call_id]["arguments"] = ""
                        if tool_call.function.arguments != None:
                            collected_functions[tool_call_id]["arguments"] += tool_call.function.arguments
                if chunk_message != None: collected_messages.append(chunk_message)  # save the message
                last_edit_time = getattr(self, "_last_edit_time", None)

                if last_edit_time is not None:
                    elapsed_time = time.time() - last_edit_time
                    if elapsed_time < delay and chunk.choices[0].finish_reason == None:
                        continue

                self._last_edit_time = time.time()
                try:
                    full_reply_content = ''.join(collected_messages)
                except:
                    pass

                if chunk.choices[0].finish_reason == None or chunk.choices[0].finish_reason == "tool_calls":
                    full_reply_content += "…"
                await self._edit(evt.room_id, event_id, f"{full_reply_content}")

            if len(collected_functions) > 0:
                self.log.debug(collected_functions)

                full_reply_content = "Calling functions: "
                for tool_id, collected_function in collected_functions.items():
                    function_args = json.loads(collected_function["arguments"])
                    full_reply_content += f"{collected_function['name']}({function_args}) "
                await self._edit(evt.room_id, event_id, f"{full_reply_content}")

                available_functions = {
                    "weather": weather,
                    "fetch_electricity_prices": fetch_electricity_prices
                }

                for tool_id, collected_function in collected_functions.items():
                    try:
                        function_args = json.loads(collected_function["arguments"])
                        function_args["user"] = sender_name
                    except:
                        function_args = []

                    try:
                        function_to_call = available_functions[collected_function["name"]]
                        self.log.debug(f"Calling function '{collected_function['name']}' with parameters '{function_args}'")
                        function_response = function_to_call(**function_args)
                    except Exception as e:
                        self.log.debug(f"Error: {e}")
                        available_functions = str(list(available_functions.keys()))
                        function_response = f"Function error: {e}"

                    # Step 4: send the info on the function call and function response to GPT
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tool_id,
                            "type": "function",
                            "function": {
                                "name": collected_function["name"],
                                "arguments": json.dumps(function_args)
                            }
                        }]
                    })  # extend conversation with assistant's reply
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": collected_function["name"],
                            "content": function_response,
                        }
                    )  # extend conversation with function response

                continue

            # print the time delay and text received
            full_reply_content = ''.join(collected_messages)
            self.log.debug(f"Full response received {chunk_time:.2f} seconds after request")
            self.log.debug(f"Full conversation received: {full_reply_content}")
            return
            #except Exception as e:
            #    if i2 < max_retries:
            #        # Handle the exception and retry
            #        self.log.debug(f"Retry {i2 + 1}/{max_retries}: {e}")
            #        continue
            #    else:
            #        await self._edit(evt.room_id, event_id, f"Error: {e}")
            #        return

    async def get_conversation_history(self, evt: MessageEvent, event_id: str) -> list:
        history = []
        bot_name = self.config["bot-name"]
        pattern = re.compile(r"^@([a-zA-Z0-9]+):")
        userIdPattern = re.compile(fr'<a href="https://matrix\.to/#/{re.escape(bot_name)}">.*?</a>:? ?')

        while event_id:
            event = await self.client.get_event(evt.room_id, event_id)
            self.log.debug(event)
            if event["type"] == EventType.ROOM_MESSAGE:
                sender_name = event["sender"]
                match = pattern.search(sender_name)
                filtered_name = match.group(1) if match else ""
                role = "assistant" if sender_name == bot_name else "user"
                if sender_name == bot_name:
                    content = self.assistant_replies.get(event_id, event['content']['body'])
                else:
                    content = userIdPattern.sub('', event['content']['formatted_body'] if event['content']['formatted_body'] != None else event['content']['body'])
                history.insert(0, {"role": role, "name": filtered_name, "content": content})
                self.log.debug(history)
            if event.content.get("_relates_to") and event.content["_relates_to"]["in_reply_to"].get("event_id"):
                event_id = event["content"]["_relates_to"]["in_reply_to"]["event_id"]
            else:
                break
        return history

    @command.new("chatgpt", aliases=["c"], help="Chat with ChatGPT from Matrix.")
    @command.argument("query", pass_raw=True)
    async def chat_gpt_handler(self, evt: MessageEvent, query: str) -> None:
        query = query.strip()

        if not query:
            await evt.reply("Please provide a message to chat with ChatGPT.")
            return

        self.log.debug(evt.content)
        if evt.content.get("_relates_to") and evt.content["_relates_to"]["in_reply_to"].get("event_id"):
            in_reply_to_event_id = evt.content["_relates_to"]["in_reply_to"]["event_id"]
            self.log.debug("Relates to event: %s", in_reply_to_event_id)
            conversation_history = await self.get_conversation_history(evt, in_reply_to_event_id)
        else:
            conversation_history = []

        event_id = await evt.reply("…", allow_html=True)

        await self.chat_gpt_request(query, conversation_history, evt, event_id)

    @command.passive(".*")
    async def on_message(self, evt: MessageEvent, match: Tuple[str]) -> None:
        self.log.debug(evt)
        bot_name = self.config["bot-name"]

        if evt.content.get("msgtype") == MessageType.TEXT:
            formatted_body = evt.content["formatted_body"] if evt.content["formatted_body"] != None else evt.content["body"]
            pattern = re.compile(fr'<a href="https://matrix\.to/#/{re.escape(bot_name)}">.*?</a>:? ?')
            if evt.content.get("_relates_to") and evt.content["_relates_to"]["in_reply_to"].get("event_id"):
                in_reply_to_event_id = evt.content["_relates_to"]["in_reply_to"]["event_id"]
            if pattern.search(formatted_body) or in_reply_to_event_id in self.assistant_replies:
                # Extract the user's query from the formatted body
                query = pattern.sub('', formatted_body)
                # Process the user's query with ChatGPT
                if evt.content.get("_relates_to") and evt.content["_relates_to"]["in_reply_to"].get("event_id"):
                    in_reply_to_event_id = evt.content["_relates_to"]["in_reply_to"]["event_id"]
                    self.log.debug("Relates to event: %s", in_reply_to_event_id)
                    conversation_history = await self.get_conversation_history(evt, in_reply_to_event_id)
                else:
                    conversation_history = []

                event_id = await evt.reply("…", allow_html=True)
                await self.chat_gpt_request(query, conversation_history, evt, event_id)

    async def _edit(self, room_id: str, event_id: EventID, text: str) -> None:
        content = TextMessageEventContent(msgtype=MessageType.NOTICE, body=text, format=Format.HTML,
                                          formatted_body=markdown.render(text))
        content.set_edit(event_id)

        # Log the edited message content
        self.log.debug(f"Editing message: {content}. RoomID: {room_id}")

        await self.client.send_message(room_id, content)
        self.assistant_replies[event_id] = text
        # Check if the number of stored messages exceeds the maximum
        if len(self.assistant_replies) > self.max_messages:
            # Remove the oldest stored message to maintain the limit
            oldest_event_id = next(iter(self.assistant_replies))
            del self.assistant_replies[oldest_event_id]
