import aiohttp
from typing import Type
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from mautrix.types import MessageType, EventID, Format, TextMessageEventContent
from mautrix.util import markdown
import time
import datetime

FINGRID_API_URL = "https://www.fingrid.fi/api/graph/power-system-state?language=fi"
PRICE_API_URL = "https://www.svk.se/services/controlroom/v2/map/price?ticks="
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

def generate_bar(value: float, segment_size: float, color: str, maxAmount: float=None) -> str:
    filled_segments = int(value / segment_size)
    bar = "|" * filled_segments
    inactive_bar = ""
    if maxAmount is not None:
        max_segments = int(maxAmount / segment_size)
        inactive_bar += "|" * (max_segments - filled_segments)
    return f"<font color='{color}'>{bar}</font><font color='darkgray'>{inactive_bar}</font>"

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("vat-rate")
        helper.copy("electricity-tax-rate")
        helper.copy("max-production-per-type")

class FingridPlugin(Plugin):
    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()

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


    def format_status_message(self, status: dict, price_data: dict) -> str:
        # Extracting values
        consumption =  float(status["Consumption"]) if status.get("Consumption") is not None else 0.0
        production =  float(status["Production"]) if status.get("Production") is not None else 0.0
        net_import_export =  float(status["NetImportExport"]) if status.get("NetImportExport") is not None else 0.0
        hydro_power =  float(status["HydroPower"]) if status.get("HydroPower") is not None else 0.0
        nuclear_power =  float(status["NuclearPower"]) if status.get("NuclearPower") is not None else 0.0
        cogeneration_district_heating =  float(status["CogenerationDistrictHeating"]) if status.get("CogenerationDistrictHeating") is not None else 0.0
        cogeneration_industry =  float(status["CogenerationIndustry"]) if status.get("CogenerationIndustry") is not None else 0.0
        wind_power =  float(status["WindPower"]) if status.get("WindPower") is not None else 0.0
        solar_power =  float(status["SolarPower"]) if status.get("SolarPower") is not None else 0.0
        other_production =  float(status["OtherProduction"]) if status.get("OtherProduction") is not None else 0.0
        peak_load_power =  float(status["PeakLoadPower"]) if status.get("PeakLoadPower") is not None else 0.0
        electricity_price = float(status["ElectricityPriceInFinland"]) if status.get("ElectricityPriceInFinland") is not None else 0.0
        consumption_emission_co2 =  float(status["ConsumptionEmissionCo2"]) if status.get("ConsumptionEmissionCo2") is not None else 0.0
        production_emission_co2 =  float(status["ProductionEmissionCo2"]) if status.get("ProductionEmissionCo2") is not None else 0.0
        price_with_vat = round(electricity_price * (1 + self.config["vat-rate"]), 2)
        price_color_vat_free = price_color(electricity_price)
        price_consumer = round(electricity_price / 10 * (1 + self.config["vat-rate"]) * (1 + self.config["electricity-tax-rate"]), 2)

        # New section for power transfer
        power_transfers = status.get("PowerTransferMap", [])
        price_dict = {data["id"]: data["value"] for data in price_data.get("Data", [])}

        # Calculate weighted average prices for tuonti and vienti
        tuonti_total = vienti_total = tuonti_weighted_price = vienti_weighted_price = 0

        tuonti_transfers = []
        vienti_transfers = []

        for transfer in power_transfers:
            try:
                if not transfer['IsExport'] and abs(transfer['Value']) > 1:
                    tuonti_total += abs(transfer['Value'])
                    tuonti_weighted_price += abs(transfer['Value']) * price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0)
                    tuonti_transfers.append((f"🔁 {transfer['Key']}",
                                            transfer['Value'],
                                            transfer['MaxImport'],
                                            "green",
                                            f"<font color='{price_color(price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0))}'>{price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0):.2f}</font>"))

                elif transfer['IsExport'] and abs(transfer['Value']) > 1:
                    vienti_total += abs(transfer['Value'])
                    vienti_weighted_price += abs(transfer['Value']) * price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0)
                    vienti_transfers.append((f"🔁 {transfer['Key']}",
                                            transfer['Value'],
                                            transfer['MaxExport'],
                                            "red",
                                            f"<font color='{price_color(price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0))}'>{price_dict.get(PRICE_ID_MAP.get(transfer['Key'], transfer['Key']), 0):.2f}</font>"))
            except:
                pass

        tuonti_weighted_price = tuonti_weighted_price / tuonti_total if tuonti_total != 0 else 0
        vienti_weighted_price = vienti_weighted_price / vienti_total if vienti_total != 0 else 0

        net_tuonti = sum(transfer['Value'] for transfer in power_transfers if not transfer['IsExport'] and transfer['Value'] is not None)
        net_vienti = sum(transfer['Value'] for transfer in power_transfers if transfer['IsExport'] and transfer['Value'] is not None)

        transfer_max_import = sum(transfer['MaxImport'] for transfer in power_transfers if not transfer['IsExport'] and transfer['Value'] is not None)
        transfer_max_export = sum(transfer['MaxExport'] for transfer in power_transfers if transfer['IsExport'] and transfer['Value'] is not None)

        # Setting up list for all production types
        production_types = [
            ("☢️ Ydinvoima", nuclear_power, self.config["max-production-per-type"]["nuclear"], "orange"),
            ("🏭 Kaukolämpö", cogeneration_district_heating, self.config["max-production-per-type"]["distict-heating"],  "magenta"),
            ("🏭 Teollisuus", cogeneration_industry, self.config["max-production-per-type"]["cogeneration-industry"], "brown"),
            ("💨 Tuulivoima", wind_power, self.config["max-production-per-type"]["wind"], "green"),
            ("☀️ Aurinkovoima", solar_power, self.config["max-production-per-type"]["solar"], "darkgoldenrod"),
            ("🔮 Muu tuotanto", other_production, self.config["max-production-per-type"]["other"], "purple"),
            ("💧 Vesivoima", hydro_power, self.config["max-production-per-type"]["hydro"], "blue"),
            ("🔋 Tehoreservi", peak_load_power, self.config["max-production-per-type"]["reserve"], "red"),
            ("🔁 Nettotuonti", net_import_export*-1, transfer_max_export if net_import_export >= 0 else transfer_max_import, "red" if net_import_export >= 0 else "green")
        ]

        # Setting up list for energy values
        energy_values = [
            ("💡 Kulutus", consumption, "red", f"<font color='{price_color_vat_free}'>{electricity_price:.2f}</font>"),
            ("⚡ Tuotanto", production, "green", ""),
        ]

        # Sorting production types by amount in descending order
        production_types = sorted(production_types, key=lambda x: x[1], reverse=True)

        vienti_transfers = sorted(vienti_transfers, key=lambda x: x[1], reverse=True)

        # Sorting Tuonti transfers by absolute amount in descending order
        tuonti_transfers.sort(key=lambda x: abs(x[1]), reverse=True)

        # Setting up the groups for Tuonti and Vienti
        groups = [
            ("Tuonti", tuonti_transfers, abs(net_tuonti), tuonti_weighted_price, transfer_max_import),
            ("Vienti", vienti_transfers, net_vienti, vienti_weighted_price, transfer_max_export)
        ]

        # Generating table rows for Tuotanto and Kulutus
        table_rows = []
        for item_name, amount, color, price in energy_values:
            bar = generate_bar(abs(amount), 100, color=color)
            table_rows.append(f"<tr><td><b>{item_name}</b></td><td><b>{amount:.0f}</b></td><td>{bar}</td><td><b>{price}<br></b></td></tr>")

        # Generating table rows for Production types
        for item_name, amount, maxAmount, color in production_types:
            bar = generate_bar(abs(amount), 100, color=color, maxAmount=maxAmount)
            table_rows.append(f"<tr><td>{item_name}</td><td>{amount:.0f}</td><td>{bar}</td><td><br></td></tr>")

        # Generating table rows for each group
        for group_name, items, total, avg_price, maxAmount in groups:
            total_bar = generate_bar(abs(total), 100, color="green" if group_name.startswith("Tuonti") else "red", maxAmount=maxAmount)
            table_rows.append(f"<tr><td><b>{group_name}</b></td><td><b>{total:.0f}</b></td><td>{total_bar}</td><td><b><font color='{price_color(avg_price, 0)}'>{avg_price:.2f}</font><br></b></td></tr>")
            for item_name, amount, maxAmount, color, price in items:
                bar = generate_bar(abs(amount), 100, color=color, maxAmount=maxAmount)
                table_rows.append(f"<tr><td>{item_name}</td><td>{abs(amount):.0f}</td><td>{bar}</td><td>{price}<br></td></tr>")

        # Building message
        message_parts = [
            "<table><tr><td><b>Tyyppi</b></td><td><b>MW</b></td><td><b>Pylväskaavio</b></td><td><b>€/MWh<br></b></td></tr>",
            "\n".join(table_rows),
            "</table>",
            f"<font size='1'>Kuluttajahinta veroineen: {price_consumer} c/kWh</font>"
        ]

        html_message = "".join(message_parts)

        # Constructing a simple plain text summary
        vat = self.config["vat-rate"] * 100
        summary_parts = [
            f"Sähköntuotanto: {production:.0f} MW",
            f"Sähkönkulutus: {consumption:.0f} MW",
            f"Nykyinen sähkön hinta: {electricity_price:.2f} €/MWh (ilman ALV), {price_with_vat:.2f} €/MWh (sis. ALV {vat}%)"
        ]

        plain_text_summary = "\n".join(summary_parts)

        return plain_text_summary, html_message

    @command.new("sähkö", help="Hae sähkön tila Fingridin API:sta")
    async def electricity_status_command(self, evt: MessageEvent) -> None:
        status = await self.get_electricity_status()
        price_data = await self.get_price_data()
        summary, html_message = self.format_status_message(status, price_data)
        content = TextMessageEventContent(msgtype=MessageType.TEXT, body=summary, format=Format.HTML, formatted_body=html_message)
        await self.client.send_message(evt.room_id, content)
