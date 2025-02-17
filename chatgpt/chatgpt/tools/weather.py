import fmi_weather_client as fmi
from fmi_weather_client.errors import ClientError, ServerError

# Weather symbol mapping
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
        forecast_data = fmi.forecast_by_place_name(location, timestep_hours=6)
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

# Tool definition for weather
weather_tool = {
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
} 
