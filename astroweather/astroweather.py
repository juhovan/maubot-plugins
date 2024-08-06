import asyncio
import logging
import time
from datetime import datetime, timedelta
from pyastroweatherio import AstroWeather, AstroWeatherError
from typing import List, Tuple

from skyfield.api import load, Loader, Topos, utc
from skyfield.framelib import ecliptic_frame
from pytz import timezone

import requests

from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import MessageType, EventID, Format, TextMessageEventContent
from mautrix.util import markdown

_LOGGER = logging.getLogger(__name__)


class AstroWeatherBot(Plugin):
    load = Loader('/data/skyfield/')
    eph = load('de421.bsp')
    from skyfield import almanac

    ts = load.timescale()
    t = ts.now()

    zone = timezone('Europe/Helsinki')

    # Set your location (latitude, longitude, and elevation)
    my_location = eph['earth'] + Topos(latitude_degrees=60.2857759, longitude_degrees=24.7530465, elevation_m=12)


    astroweather = AstroWeather(
        latitude=60.2857759,
        longitude=24.7530465,
        elevation=12,
        timezone_info="Europe/Helsinki",
        cloudcover_weight=3,
        seeing_weight=2,
        transparency_weight=1,
    )

    @command.new("moon")
    async def moon_command(self, evt: MessageEvent):
        ts = self.load.timescale()
        t = ts.now()

        sun, moon, earth = self.eph['sun'], self.eph['moon'], self.eph['earth']

        e = earth.at(t)
        _, slon, _ = e.observe(sun).apparent().frame_latlon(ecliptic_frame)
        _, mlon, _ = e.observe(moon).apparent().frame_latlon(ecliptic_frame)
        phase = (mlon.degrees - slon.degrees) % 360.0

        # Adding more emojis for moon phases and selecting the closest phase
        moon_phase_emojis = {
            0: "🌑 New Moon",
            45: "🌒 Waxing Crescent",
            90: "🌓 First Quarter",
            135: "🌔 Waxing Gibbous",
            180: "🌕 Full Moon",
            225: "🌖 Waning Gibbous",
            270: "🌗 Last Quarter",
            315: "🌘 Waning Crescent",
        }

        # Find the closest moon phase
        closest_phase = min(moon_phase_emojis.keys(), key=lambda x: abs(x - phase))
        result_message = "<h1>" + moon_phase_emojis.get(closest_phase, '🌘 Unknown Phase') + "</h1>"

        # Find the next moon phases
        moon_phase_emojis = {
            0: "🌑 New Moon",
            1: "🌓 First Quarter",
            2: "🌕 Full Moon",
            3: "🌗 Last Quarter",
        }

        t0 = t
        t1 = ts.utc(datetime.utcnow().replace(tzinfo=utc) + timedelta(days=30))
        t, y = self.almanac.find_discrete(t0, t1, self.almanac.moon_phases(self.eph))

        result_message += "<table><tr>"
        for phase in y:
            result_message += "<th>" + moon_phase_emojis.get(phase, '🌘 Unknown Phase') + "</th> "

        result_message += "</tr><br><tr>"

        for date in t:
            result_message += "<td>" + date.astimezone(self.zone).strftime("%-d %B") + "</td> &nbsp; &nbsp; &nbsp;"

        result_message += "</tr></table>"

        # Create a reply message with the result_message.
        reply_content = TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            format=Format.HTML,
            formatted_body=result_message,
        )

        # Send the reply message.
        await self.client.send_message(evt.room_id, reply_content)

    @command.new("astro", help="Astro weather forecast")
    async def astro_command(self, evt: MessageEvent):
        # Create a reply message to acknowledge the command.
        reply_content = TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            body=f"Fetching data...",
        )

        # Send the acknowledgment message.
        text_event_id = await self.client.send_message(evt.room_id, reply_content)

        # Create a result message variable to store the output.
        result_message = ""

        try:
            data = await self.astroweather.get_location_data()
            for row in data:
                # Append the data to the result_message variable in the desired format.
                result_message += f"Today: {row.deepsky_forecast_today_plain}\n"
                result_message += f"Tomorrow: {row.deepsky_forecast_tomorrow_plain}"

        except AstroWeatherError as err:
            # Handle errors and append error messages to result_message if necessary.
            result_message += f"Error: {str(err)}\n"

        # Create a reply message with the result_message.
        reply_content = TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            body=result_message,
        )

        # Send the reply message.
        reply_content.set_edit(text_event_id)
        await self.client.send_message(evt.room_id, reply_content)

    @command.new("astro2", help="Astro weather forecast")
    async def astro2_command(self, evt: MessageEvent):
        # Create a reply message to acknowledge the command.
        reply_content = TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            body=f"Fetching data...",
        )

        # Send the acknowledgment message.
        text_event_id = await self.client.send_message(evt.room_id, reply_content)

        # Create a result message variable to store the output.
        result_message = ""

        try:
            data = await self.astroweather.get_location_data()
            result_message += f"Forecast calculated: {data[0].init}\n"
            for row in data:
                result_message += f"Init: {row.init}, Timepoint: {row.timepoint}, Timestamp: {row.timestamp}, Forecast Length: {row.forecast_length}\n"
                result_message += f"Latitude: {row.latitude}, Longitude: {row.longitude}, Elevation: {row.elevation}\n"

                result_message += f"View Condition: {row.condition_percentage}% ({row.condition_plain}), Plain: {row.condition_plain}\n"

                result_message += f"Cloudcover: {row.cloudcover_percentage}%, Cloudless: {row.cloudless_percentage}%, Plain: {row.cloudcover_plain}\n"

                result_message += f"Cloud Area Fraction: {row.cloud_area_fraction_percentage}%, Cloud Area Fraction High: {row.cloud_area_fraction_high_percentage}%, Cloud Area Fraction Low: {row.cloud_area_fraction_low_percentage}%, Cloud Area Fraction Medium: {row.cloud_area_fraction_medium_percentage}\n"

                result_message += f"Seeing: {row.seeing_percentage}%, Plain: {row.seeing_plain}\n"

                result_message += f"Transparency: {row.transparency_percentage}%, Plain: {row.transparency_plain}\n"

                result_message += f"Lifted Index: {row.lifted_index}%, Plain: {row.lifted_index_plain}\n"

                result_message += f"Wind Direction: {row.wind10m_direction}, Speed: {row.wind10m_speed}, Plain: {row.wind10m_speed_plain}\n"

                result_message += f"Temperature: {row.temp2m}, Rel Humidity: {row.rh2m}, Dew Point: {row.dewpoint2m}, Prec Type: {row.prec_type}\n"

                result_message += f"View Condition: {row.condition_percentage}%, Plain: {row.condition_plain}, Weather: {row.weather}, Deep Sky View: {row.deep_sky_view}\n"

                result_message += f"Moon Phase: {row.moon_phase}, Moon Altitude: {row.moon_altitude}, Moon Azimuth: {row.moon_azimuth}\n"

                result_message += f"Sun Altitude: {row.sun_altitude}, Sun Azimuth: {row.sun_azimuth}\n"

                result_message += f"Sun next Rising: {row.sun_next_rising}, Nautical: {row.sun_next_rising_nautical}, Astronomical: {row.sun_next_rising_astro}\n"

                result_message += f"Sun next Setting: {row.sun_next_setting}, Nautical: {row.sun_next_setting_nautical}, Astronomical: {row.sun_next_setting_astro}\n"

                result_message += f"Moon next Rising: {row.moon_next_rising}, Moon next Setting: {row.moon_next_setting}\n"

                result_message += f"Forecast Today: {row.deepsky_forecast_today}, Forecast Today Dayname: {row.deepsky_forecast_today_dayname}, Forecast Today: {row.deepsky_forecast_today_plain}\n"

                result_message += f"Description: {row.deepsky_forecast_today_desc}\n"

                result_message += f"Forecast Tomorrow: {row.deepsky_forecast_tomorrow}, Forecast Tomorrow Dayname: {row.deepsky_forecast_tomorrow_dayname}, Forecast Tomorrow: {row.deepsky_forecast_tomorrow_plain}\n"

                result_message += f"Description: {row.deepsky_forecast_tomorrow_desc}\n"


        except AstroWeatherError as err:
            # Handle errors and append error messages to result_message if necessary.
            result_message += f"Error: {str(err)}\n"

        # Create a reply message with the result_message.
        reply_content = TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            body=result_message,
        )

        # Send the reply message.
        reply_content.set_edit(text_event_id)
        await self.client.send_message(evt.room_id, reply_content)
