from .weather import weather, weather_tool
from .electricity import fetch_electricity_prices, electricity_tool, vat

# List of available tools for the bot
available_tools = [
    weather_tool,
    electricity_tool
]

# Map of function names to their implementations
function_map = {
    "weather": weather,
    "fetch_electricity_prices": fetch_electricity_prices
} 
