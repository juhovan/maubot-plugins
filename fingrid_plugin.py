import aiohttp
from maubot import Plugin, MessageEvent
from maubot.handlers import command

FINGRID_API_URL = "https://www.fingrid.fi/api/graph/power-system-state?language=fi"
VAT_RATE = 0.24

def price_color(price: float, min_price: float = 0, max_price: float = 200) -> str:
    ratio = (price - min_price) / (max_price - min_price)
    red = int(255 * ratio)
    green = int(255 * (1 - ratio))
    return f"rgb({red}, {green}, 0)"

class FingridPlugin(Plugin):
    async def get_electricity_status(self) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(FINGRID_API_URL) as response:
                return await response.json()

    @command.new("sähkö", help="Hae sähkön tila Fingridin API:sta")
    async def electricity_status_command(self, evt: MessageEvent) -> None:
        status = await self.get_electricity_status()
        consumption = status.get("Consumption", "N/A")
        production = status.get("Production", "N/A")
        net_import_export = status.get("NetImportExport", "N/A")

        # Tuotanto tyypeittäin
        hydro_power = status.get("HydroPower", "N/A")
        nuclear_power = status.get("NuclearPower", "N/A")
        cogeneration_district_heating = status.get("CogenerationDistrictHeating", "N/A")
        cogeneration_industry = status.get("CogenerationIndustry", "N/A")
        wind_power = status.get("WindPower", "N/A")
        solar_power = status.get("SolarPower", "N/A")
        other_production = status.get("OtherProduction", "N/A")

        # Nykyinen hinta ja CO2-arvot
        electricity_price = status.get("ElectricityPriceInFinland", "N/A")
        consumption_emission_co2 = status.get("ConsumptionEmissionCo2", "N/A")
        production_emission_co2 = status.get("ProductionEmissionCo2", "N/A")
        price_with_vat = round(electricity_price * (1 + VAT_RATE), 2)
        price_color_vat_free = price_color(electricity_price)

        production_types = {
            "Ydinvoima": (nuclear_power, "darkorange"),
            "Kaukolämmön CHP": (cogeneration_district_heating, "gray"),
            "Teollisuuden CHP": (cogeneration_industry, "darkgray"),
            "Tuulivoima": (wind_power, "mediumpurple"),
            "Aurinkovoima": (solar_power, "darkgoldenrod"),
            "Muu tuotanto": (other_production, "purple")
        }

        sorted_production_types = sorted(production_types.items(), key=lambda x: x[1][0], reverse=True)

        message = f"Sähkön tila:<br><br>"
        message += f"Kulutus: {consumption} MW<br>"
        message += f"Tuotanto: {production} MW<br>"
        message += f"Nettotuonti/-vienti: {net_import_export} MW<br><br>"

        message += "Tuotanto tyypeittäin:<br>"
        for production_type, values in sorted_production_types:
            amount, color = values
            message += f"{production_type}: <font color='{color}'>{amount:.0f} MW</font><br>"

        message += f"Nykyinen sähkön hinta: <font color='{price_color_vat_free}'>{electricity_price:.2f} €/MWh (ilman ALV)</font> | <font color='{price_color_vat_free}'>{price_with_vat:.2f} €/MWh (sis. ALV 24%)</font><br>"
        message += f"CO₂ päästöt: {consumption_emission_co2:.2f} g/kWh (kulutus) | {production_emission_co2:.2f} g/kWh (tuotanto)<br>"
        await evt.reply(message, allow_html=True)
