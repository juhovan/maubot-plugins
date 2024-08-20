# Space - A maubot plugin to show stuff related to astrophotography.
# Copyright (C) 2020 Juho Vanhanen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
import asyncio
from typing import Type

from mautrix.types import (StateEvent, EventType, MessageType,
                           RoomID, EventID, TextMessageEventContent, Format, MediaMessageEventContent, ImageInfo)
from maubot import Plugin, MessageEvent
from maubot.handlers import command, event
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper

try:
    import magic
except ImportError:
    magic = None

import requests
from bs4 import BeautifulSoup
import datetime

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("aurora_channel_id")
        helper.copy("aurora_notify_kp")
        helper.copy("aurora_poll_interval")

class SpaceBot(Plugin):
    poll_task: asyncio.Future

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()
        self.poll_task = asyncio.ensure_future(self.poll_json_data(), loop=self.loop)

    async def stop(self) -> None:
        await super().stop()
        self.poll_task.cancel()

    async def poll_json_data(self) -> None:
        self.log.debug("Polling started")
        try:
            await self._poll_json_data()
        except asyncio.CancelledError:
            self.log.debug("Polling stopped")
        except Exception:
            self.log.exception("Fatal error while polling")

    async def _poll_json_data(self):
        self.log.debug("Polling started2")
        while True:
            # Define the URL of the JSON data
            url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"

            # Send an HTTP GET request to the URL
            response = requests.get(url)

            result_message = ""

            self.log.info(f"Fetching Kp forecast")

            # Check if the request was successful (status code 200)
            if response.status_code == 200:
                # Parse the JSON data
                data = response.json()
                self.log.info(f"Kp forecast: {data}")
                current_month = datetime.datetime.now().month
                # Iterate through the data and look for predicted values of 5 or greater in the second field
                for entry in data:
                    if entry[2] == 'predicted' and float(entry[1]) >= float(self.config["aurora_notify_kp"][current_month - 1]):
                        result_message += f"{entry[0]}Z predicted Kp-index: {entry[1]}\n"
            else:
                result_message += f"Failed to retrieve data from the URL. Status code: {response.status_code}"

            if (len(result_message)):
                # Create a reply message with the result_message.
                reply_content = TextMessageEventContent(
                    msgtype=MessageType.NOTICE,
                    body=result_message,
                )
                # Send the reply message.
                if self.config["aurora_channel_id"]:
                    await self.client.send_message(self.config["aurora_channel_id"], reply_content)
            await asyncio.sleep(self.config["aurora_poll_interval"])

    async def _download_image(self, image_url: str) -> None:
        try:
            resp = await self.http.get(image_url)

            if resp.status == 200:
                data = await resp.read()
                return data

            else:
                return False

        except:
            return False

    async def _get_media_content(self, image_data: str, external_url: str) -> TextMessageEventContent:
        mime_type = None
        if magic is not None:
            mime_type = magic.from_buffer(image_data, mime=True)

        uri = await self.client.upload_media(image_data, mime_type=mime_type)

        content = MediaMessageEventContent(url=uri,
                                           msgtype=MessageType.IMAGE,
                                           external_url=external_url,
                                           info=ImageInfo(
                                               mimetype=mime_type,
                                           ),)

        return content

    async def post_picture(self, evt: MessageEvent, image_url: str, external_url: str, interval: int = 60):
        if interval:
            image_data = await self._download_image(image_url)
            content = await self._get_media_content(image_data, external_url)
            image_event_id = await self.client.send_message(evt.room_id, content)
            content = TextMessageEventContent(body=f"▶️ {external_url}",
                                              formatted_body=f"▶️ <a href=\" {external_url}\">{external_url}</a>",
                                              format=Format.HTML,
                                              msgtype=MessageType.TEXT)
            text_event_id = await self.client.send_message(evt.room_id, content)

            i = 0
            for i in range(int(20*60/interval)):
                await asyncio.sleep(interval)
                previous_image_data = image_data
                image_data = await self._download_image(image_url)
                if image_data == previous_image_data:
                    continue
                if image_data == False:
                    content = TextMessageEventContent(body=f"Failed to fetch image from {image_url}!",
                                                      msgtype=MessageType.TEXT)
                else:
                    content = await self._get_media_content(image_data, external_url)
                content.set_edit(image_event_id)
                await self.client.send_message(evt.room_id, content)

        image_data = await self._download_image(image_url)
        content = await self._get_media_content(image_data, external_url)
        try:
            content.set_edit(image_event_id)
        except:
            pass
        content = TextMessageEventContent(body=f"⏹️ {external_url}",
                                          formatted_body=f"⏹️ <a href=\" {external_url}\">{external_url}</a>",
                                          format=Format.HTML,
                                          msgtype=MessageType.TEXT)
        content.set_edit(text_event_id)
        await self.client.send_message(evt.room_id, content)

    @command.new("clouds",
                 help="Sääsatelliittien kuvat", require_subcommand=True)
    async def clouds(self) -> None:
        pass

    @clouds.subcommand("sat24", help="Sat24")
    async def sat24(self, evt: MessageEvent) -> None:
        await self.post_picture(evt, "http://meteocentre.com/satellite/europe/europe_ir.gif", "http://meteocentre.com/satellite/imagery.php?lang=en&area=eur&map=bw_ir")

    @clouds.subcommand("eumetsat", help="Eumetsat")
    async def eumetsat(self, evt: MessageEvent) -> None:
        self.post_picture(evt, "https://eumetview.eumetsat.int/static-images/latestImages/EUMETSAT_MSG_IR039_CentralEurope.jpg",
                          "http://oiswww.eumetsat.org/imagegallery/MSG/IMAGERY/")
        self.post_picture(evt, "https://eumetview.eumetsat.int/static-images/latestImages/EUMETSAT_MSGIODC_IR039_Europe.jpg",
                          "http://oiswww.eumetsat.org/imagegallery/MSG/IMAGERY/")

    @command.new("sky",
                 help="Taivaskameroiden kuvat", require_subcommand=True)
    async def sky(self) -> None:
        pass

    @sky.subcommand("metsähovi", aliases=["aalto", "helsinki", "hki", "kirkkonummi"], help="[aalto, helsinki, hki, kirkkonummi] Metsähovin radiotutkimusasema")
    async def helsinki(self, evt: MessageEvent) -> None:
        await self.post_picture(evt, "https://aurorasnow.fmi.fi/public_service/images/latest_HOV.jpg", "https://aurorasnow.fmi.fi/public_service/")

    @sky.subcommand("murtoinen", aliases=["hankasalmi"], help="[hankasalmi] Murtoisten observatorio")
    async def hankasalmi(self, evt: MessageEvent) -> None:
        await self.post_picture(evt, "https://aurorasnow.fmi.fi/public_service/images/latest_SIR_AllSky.jpg", "https://aurorasnow.fmi.fi/public_service/")

    @sky.subcommand("nyrölä", aliases=["jyväskylä"], help="[jyväskylä] Nyrölän observatorio")
    async def nyrola(self, evt: MessageEvent) -> None:
        await self.post_picture(evt, "https://aurorasnow.fmi.fi/public_service/images/latest_SIR.jpg", "https://aurorasnow.fmi.fi/public_service/")

    @sky.subcommand("kevo", help="Lapin tutkimuslaitos Kevo")
    async def kevo(self, evt: MessageEvent) -> None:
        await self.post_picture(evt, "https://aurorasnow.fmi.fi/public_service/images/latest_KEV.jpg", "https://aurorasnow.fmi.fi/public_service/")

    @sky.subcommand("muonio", help="Revontuliasema Muonio")
    async def muonio(self, evt: MessageEvent) -> None:
        await self.post_picture(evt, "https://aurorasnow.fmi.fi/public_service/images/latest_MUO.jpg", "https://aurorasnow.fmi.fi/public_service/")

    @command.new("aurora",
                 help="Revontulet", require_subcommand=True)
    async def aurora(self) -> None:
        pass

    @aurora.subcommand("1h", help="Lyhyen aikavälin revontuliennuste")
    async def auroraforecast(self, evt: MessageEvent) -> None:
        await self.post_picture(evt, "https://services.swpc.noaa.gov/images/animations/ovation/north/latest.jpg", "https://www.swpc.noaa.gov/products/aurora-30-minute-forecast")

    @aurora.subcommand("forecast", help="Pitkän aikavälin revontuliennuste")
    async def auroralongforecast(self, evt: MessageEvent):
        # Define the URL of the JSON data
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"

        # Send an HTTP GET request to the URL
        response = requests.get(url)

        result_message = ""

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            # Parse the JSON data
            data = response.json()
            self.log.info(f"Kp forecast: {data}")
            # Iterate through the data and look for predicted values of 5 or greater in the second field
            for entry in data:
                if entry[2] == 'predicted' or entry[2] == 'estimated':
                    result_message += f"{entry[0]}Z predicted Kp-index: {entry[1]}\n"
        else:
            result_message += f"Failed to retrieve data from the URL. Status code: {response.status_code}"

        # Create a reply message with the result_message.
        reply_content = TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            body=result_message,
        )

        # Send the reply message.
        await self.client.send_message(evt.room_id, reply_content)

    @aurora.subcommand("now", help="Geomagneettinen aktiivisuus")
    async def auroranow(self, evt: MessageEvent) -> None:
        await self.post_picture(evt, "https://cdn.fmi.fi/weather-observations/products/magnetic-disturbance-observations/map-fi.png",
                                "https://www.ilmatieteenlaitos.fi/revontulet-ja-avaruussaa")


    @command.new("spaceweather", help="Fetch space weather forecast")
    async def spaceweather(self, evt: MessageEvent) -> None:
        url = "https://www.ilmatieteenlaitos.fi/revontulet-ja-avaruussaa"
        space_weather_forecast = await self.fetch_space_weather_forecast(url)
        if space_weather_forecast:
            content = TextMessageEventContent(
                body=space_weather_forecast,
                msgtype=MessageType.TEXT
            )
            await self.client.send_message(evt.room_id, content)
        else:
            content = TextMessageEventContent(
                body="Failed to fetch space weather forecast!",
                msgtype=MessageType.TEXT
            )
            await self.client.send_message(evt.room_id, content)


    async def fetch_space_weather_forecast(self, url: str) -> str:
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
            forecast_div = soup.find("div", {"class": "en"})
            forecast_paragraphs = forecast_div.find_all("p")
            forecast_text = "\n".join([p.text for p in forecast_paragraphs])
            return forecast_text
        except Exception as e:
            self.log.exception(
                "Error fetching space weather forecast:", exc_info=e)
            return None
