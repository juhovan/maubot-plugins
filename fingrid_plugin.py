import aiohttp
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import MessageType, EventID, Format, TextMessageEventContent
from mautrix.util import markdown
import time
import datetime

FINGRID_API_URL = "https://www.fingrid.fi/api/graph/power-system-state?language=fi"
PRICE_API_URL = "https://www.svk.se/services/controlroom/v2/map/price?ticks="
VAT_RATE = 0.24
PRICE_ID_MAP = {
    "Norway": "NO4",
    "Estonia": "EE",
    "SEAland": "SE3",
    # Add more mappings as necessary...
}

def rgb_to_hex(red: int, green: int, blue: int) -> str:
    return f"#{red:02x}{green:02x}{blue:02x}"

def price_color(price: float, min_price: float = 0, max_price: float = 300) -> str:
    try:
        if price > max_price:
            price = max_price
        ratio = (price - min_price) / (max_price - min_price)
        red = int(255 * ratio)
        green = int((255 - 38) * (1 - ratio))
        return rgb_to_hex(red, green, 0)
    except:
        return rgb_to_hex(0, 0, 0)

def generate_bar(value: float, segment_size: float, color: str) -> str:
    filled_segments = int(value / segment_size)
    bar = "|" * filled_segments
    return f"<font color='{color}'>{bar}</font>"

def format_status_message(status: dict, price_data: dict) -> str:
    # Extracting values
    consumption = float(status.get("Consumption", 0))
    production = float(status.get("Production", 0))
    net_import_export = float(status.get("NetImportExport", 0))
    hydro_power = float(status.get("HydroPower", 0))
    nuclear_power = float(status.get("NuclearPower", 0))
    cogeneration_district_heating = float(status.get("CogenerationDistrictHeating", 0))
    cogeneration_industry = float(status.get("CogenerationIndustry", 0))
    wind_power = float(status.get("WindPower", 0))
    solar_power = float(status.get("SolarPower", 0))
    other_production = float(status.get("OtherProduction", 0))
    peak_load_power = float(status.get("PeakLoadPower", 0))
    electricity_price = float(status.get("ElectricityPriceInFinland", 0))
    consumption_emission_co2 = float(status.get("ConsumptionEmissionCo2", 0))
    production_emission_co2 = float(status.get("ProductionEmissionCo2", 0))
    price_with_vat = round(electricity_price * (1 + VAT_RATE), 2)
    price_color_vat_free = price_color(electricity_price)

    # Setting up list for all production types
    production_types = [
        ("☢️ Ydinvoima&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", nuclear_power, "orange"),
        ("🏭 Kaukolämmön CHP&nbsp;", cogeneration_district_heating, "gray"),
        ("🏭 Teollisuuden CHP&nbsp;&nbsp;&nbsp;&nbsp;", cogeneration_industry, "darkgray"),
        ("💨 Tuulivoima&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", wind_power, "green"),
        ("☀️ Aurinkovoima&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", solar_power, "darkgoldenrod"),
        ("🔮 Muu tuotanto&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", other_production, "purple"),
        ("💧 Vesivoima&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", hydro_power, "blue"),
        ("🔋 Tehoreservi&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", peak_load_power, "red"),
        ("🔁 Nettotuonti&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", net_import_export*-1, "red" if net_import_export >= 0 else "green")

    ]

    # New section for power transfer
    power_transfers = status.get("PowerTransferMap", [])
    price_dict = {data["id"]: data["value"] for data in price_data.get("Data", [])}

    # Calculate weighted average prices for tuonti and vienti
    tuonti_total = vienti_total = tuonti_weighted_price = vienti_weighted_price = 0

    tuonti_transfers = []
    vienti_transfers = []

    for transfer in power_transfers:
        if not transfer['IsExport'] and abs(transfer['Value']) > 1:
            tuonti_total += abs(transfer['Value'])
            tuonti_weighted_price += abs(transfer['Value']) * price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0)
            spaces = "&nbsp;" * int(37 - len(transfer['Key']) / 0.45)
            tuonti_transfers.append((f"🔁 {transfer['Key']}{spaces}",
                                     transfer['Value'],
                                     "green",
                                     f"<font color='{price_color(price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0))}'>{price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0):.2f}</font>"))

        elif transfer['IsExport'] and abs(transfer['Value']) > 1:
            vienti_total += abs(transfer['Value'])
            vienti_weighted_price += abs(transfer['Value']) * price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0)
            spaces = "&nbsp;" * int(37 - len(transfer['Key']) / 0.45)
            vienti_transfers.append((f"🔁 {transfer['Key']}{spaces}",
                                     transfer['Value'],
                                     "red",
                                     f"<font color='{price_color(price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0))}'>{price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0):.2f}</font>"))

    tuonti_weighted_price = tuonti_weighted_price / tuonti_total if tuonti_total != 0 else 0
    vienti_weighted_price = vienti_weighted_price / vienti_total if vienti_total != 0 else 0

    net_tuonti = sum(transfer['Value'] for transfer in power_transfers if not transfer['IsExport'])
    net_vienti = sum(transfer['Value'] for transfer in power_transfers if transfer['IsExport'])

    # Setting up list for energy values
    energy_values = [
        ("💡 Kulutus&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", consumption, "red", f"<font color='{price_color_vat_free}'>{electricity_price:.2f}</font>"),
        ("⚡ Tuotanto&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", production, "green", ""),
    ]

    # Sorting production types by amount in descending order
    production_types = sorted(production_types, key=lambda x: x[1], reverse=True)

    vienti_transfers = sorted(vienti_transfers, key=lambda x: x[1], reverse=True)

    # Sorting Tuonti transfers by absolute amount in descending order
    tuonti_transfers.sort(key=lambda x: abs(x[1]), reverse=True)

    # Setting up the groups for Tuonti and Vienti
    groups = [
        ("Tuonti&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", tuonti_transfers, abs(net_tuonti), tuonti_weighted_price),
        ("Vienti&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;", vienti_transfers, net_vienti, vienti_weighted_price)
    ]

    # Generating table rows for Tuotanto and Kulutus
    table_rows = []
    for item_name, amount, color, price in energy_values:
        bar = generate_bar(abs(amount), 100, color=color)
        table_rows.append(f"<tr><th>{item_name}</th><th>{amount:.0f}&nbsp;</th><td>{bar}&nbsp;</td><th>{price}<br></th></tr>")

    # Generating table rows for Production types
    for item_name, amount, color in production_types:
        bar = generate_bar(abs(amount), 100, color=color)
        table_rows.append(f"<tr><td>{item_name}</td><td>{amount:.0f}&nbsp;</td><td>{bar}</td><td><br></td></tr>")

    # Generating table rows for each group
    for group_name, items, total, avg_price in groups:
        total_bar = generate_bar(abs(total), 100, color="green" if group_name.startswith("Tuonti") else "red")
        table_rows.append(f"<tr><th>{group_name}&nbsp;</th><th>{total:.0f}&nbsp;</th><td>{total_bar}&nbsp;</td><th><font color='{price_color(avg_price, 0)}'>{avg_price:.2f}</font><br></th></tr>")
        for item_name, amount, color, price in items:
            bar = generate_bar(abs(amount), 100, color=color)
            table_rows.append(f"<tr><td>{item_name}&nbsp;</td><td>{abs(amount):.0f}&nbsp;</td><td>{bar}&nbsp;</td><td>{price}<br></td></tr>")

    # Building message
    message_parts = [
        "<table><tr><th>Tyyppi&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</th><th>MW&nbsp;&nbsp;&nbsp;</th><th>Pylväskaavio&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</th><th>€/MWh<br></th></tr>",
        "\n".join(table_rows),
        "</table>"
    ]

    html_message = "".join(message_parts)

    # Constructing a simple plain text summary
    summary_parts = [
        f"Sähköntuotanto: {production:.0f} MW",
        f"Sähkönkulutus: {consumption:.0f} MW",
        f"Nykyinen sähkön hinta: {electricity_price:.2f} €/MWh (ilman ALV), {price_with_vat:.2f} €/MWh (sis. ALV 24%)"
    ]

    plain_text_summary = "\n".join(summary_parts)

    return plain_text_summary, html_message

class FingridPlugin(Plugin):
    async def get_electricity_status(self) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(FINGRID_API_URL) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.log.warning(f"Error retrieving electricity status: {response.status}")
                    return {}

    async def get_price_data(self) -> dict:
        current_time = datetime.datetime.now()
        seconds_since_full_hour = current_time.minute * 60 + current_time.second
        previous_full_hour = int(time.time()) - seconds_since_full_hour
        ticks = int(previous_full_hour)

        async with aiohttp.ClientSession() as session:
            async with session.get(PRICE_API_URL + str(ticks) + '000') as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.log.warning(f"Error retrieving price data: {response.status}")
                    return {}

    @command.new("sähkö", help="Hae sähkön tila Fingridin API:sta")
    async def electricity_status_command(self, evt: MessageEvent) -> None:
        status = await self.get_electricity_status()
        price_data = await self.get_price_data()
        summary, html_message = format_status_message(status, price_data)
        content = TextMessageEventContent(msgtype=MessageType.TEXT, body=summary, format=Format.HTML, formatted_body=html_message)
        await self.client.send_message(evt.room_id, content)
