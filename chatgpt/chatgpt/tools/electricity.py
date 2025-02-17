import requests
import datetime

# Global VAT rate, will be set by the bot
vat = 1.0

def fetch_electricity_prices(user, date):
    """Get electricity prices for a given date."""
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

    return formatted_string

# Tool definition for electricity prices
electricity_tool = {
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
