# Copyright 2025 Bram Oosterlynck
#
# weewx driver/service that reads data from the RMI API
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.
#
# See http://www.gnu.org/licenses/
#
# This driver/service will read weather data from an API offered by the Royal
# Meteorological Institute of Belgium (RMI). This will only work for
# locations inside the Benelux.
#
# To use this driver/service, put this file in the weewx user directory, then make
# the following changes to weewx.conf:
#
# [RMI]
#     poll_interval = 2          # number of seconds
#     driver = user.rmi
#     enable = true              # only used by the service
#     binding = loop            # only used by the service
#     latitude = 50.0           # optional, the driver uses the location of
#     longitude = 0.0           # the station by default
#
# If the variables in the file have names different from those in the database
# schema, then create a mapping section called label_map.  This will map the
# variables in the file to variables in the database columns.  For example:
#
# [RMI]
#     ...
#     [[field_map]]
#         extraTemp1 = outTemp

import aiohttp
import asyncio
import logging
import time
import weewx.drivers
import weewx.engine
from irm_kmi_api import IrmKmiApiClientHa
from datetime import datetime
from zoneinfo import ZoneInfo

DRIVER_NAME = "RMI"
DRIVER_VERSION = "0.1"
log = logging.getLogger(__name__)


def _get_as_float(data, key):
    v = None
    if key in data and data.get(key):
        try:
            v = float(data[key])
        except ValueError as e:
            log.error("cannot read value for '%s': %s" % (data[key], e))
    return v


class RMIDataFetcher:
    """Fetches weather data from the RMI API."""

    DEFAULT_FIELD_MAP = {
        "barometer": "pressure",
        "outTemp": "temperature",
        "windSpeed": "wind_speed",
        "windGust": "wind_speed_gust",
        "windDir": "wind_bearing",
        "cloudcover": "condition",
    }

    def __init__(self, **stn_dict):
        self.poll_interval = float(stn_dict.get("poll_interval", 60))
        self.latitude = float(stn_dict.get("latitude"))
        self.longitude = float(stn_dict.get("longitude"))
        obs_map = stn_dict.pop("field_map", None)
        obs_map_ext = stn_dict.pop("field_map_extensions", {})
        if obs_map is None:
            obs_map = self.default_field_map()
        obs_map.update(obs_map_ext)
        self._obs_map = obs_map
        log.info("Polling interval is %s" % self.poll_interval)
        log.info("Latitude is %s" % self.latitude)
        log.info("Longitude is %s" % self.longitude)

    async def get_weather_packet(self):
        session = aiohttp.ClientSession()
        client = IrmKmiApiClientHa(
            session=session, user_agent="boosterl/weewx-rmi driver"
        )
        try:
            await client.refresh_forecasts_coord(
                {"lat": self.latitude, "long": self.longitude}
            )
            await session.close()
        except Exception:
            log.error("Error connecting to RMI api")
            return dict()
        weather = client.get_current_weather(tz=ZoneInfo("Europe/Brussels"))
        packet = dict()
        for weewx_field, rmi_field in self._obs_map.items():
            if rmi_field == "condition":
                packet[weewx_field] = self.get_cloud_cover(weather.get(rmi_field))
                continue
            packet[weewx_field] = weather.get(rmi_field)
        forecasts = client.get_radar_forecast()
        prev = forecasts[0]
        for forecast in forecasts:
            dt_timestamp = datetime.strptime(
                forecast.get("datetime"), "%Y-%m-%dT%H:%M:%S%z"
            ).timestamp()
            if dt_timestamp > time.time():
                packet["rainRate"] = prev.get("native_precipitation") * 6
                break
            prev = forecast
        return packet

    def default_field_map(self):
        return RMIDataFetcher.DEFAULT_FIELD_MAP

    @staticmethod
    def get_cloud_cover(condition):
        if condition in ["sunny", "clear-night"]:
            return 0
        if condition in ["cloudy"]:
            return 50
        return 100


class RMIDriver(weewx.drivers.AbstractDevice):
    """weewx driver that reads data from the RMI API"""

    def __init__(self, engine, **stn_dict):
        self.engine = engine
        stn_dict.setdefault("latitude", self.engine.stn_info.latitude_f)
        stn_dict.setdefault("longitude", self.engine.stn_info.longitude_f)
        self.fetcher = RMIDataFetcher(**stn_dict)

    def genLoopPackets(self):
        while True:
            data = {}
            try:
                data = asyncio.run(self.fetcher.get_weather_packet())
            except Exception as e:
                log.error("read failed: %s" % e)
            _packet = {"dateTime": int(time.time()), "usUnits": weewx.METRIC}
            for vname in data:
                _packet[vname] = _get_as_float(data, vname)
            yield _packet
            time.sleep(self.fetcher.poll_interval)

    @property
    def hardware_name(self):
        return "RMI"


class RMIService(weewx.engine.StdService):
    """weewx service that updates loop/archive records with RMI data"""

    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        config_dict[DRIVER_NAME].setdefault("latitude", self.engine.stn_info.latitude_f)
        config_dict[DRIVER_NAME].setdefault(
            "longitude", self.engine.stn_info.longitude_f
        )
        self.fetcher = RMIDataFetcher(**config_dict[DRIVER_NAME])
        self.binding = config_dict[DRIVER_NAME].get("binding", "loop")
        self.enable = config_dict[DRIVER_NAME].get("enable", True)
        if not self.enable:
            log.info("RMI service not enabled, exiting.")
            return
        if self.binding == "loop":
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)
        elif self.binding == "archive":
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        else:
            raise ValueError(f"Unknown binding: {self.binding}")

    def new_loop_packet(self, event):
        data = asyncio.run(self.fetcher.get_weather_packet())
        data["usUnits"] = weewx.METRIC
        print(data)
        converter = weewx.units.StdUnitConverters[event.packet["usUnits"]]
        converted_data = converter.convertDict(data)
        for vname in converted_data:
            event.packet[vname] = _get_as_float(converted_data, vname)

    def new_archive_record(self, event):
        data = asyncio.run(self.fetcher.get_weather_packet())
        data["usUnits"] = weewx.METRIC
        print(data)
        converter = weewx.units.StdUnitConverters[event.packet["usUnits"]]
        converted_data = converter.convertDict(data)
        for vname in converted_data:
            event.packet[vname] = _get_as_float(converted_data, vname)


def loader(config_dict, engine):
    return RMIDriver(engine, **config_dict[DRIVER_NAME])


# To test this driver, run it directly as follows:
#   PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/rmi.py
if __name__ == "__main__":
    import weeutil.weeutil
    import weeutil.logger
    import weewx

    weewx.debug = 1
    weeutil.logger.setup("rmi")
    driver = RMIDriver()
    for packet in driver.genLoopPackets():
        print(weeutil.weeutil.timestamp_to_string(packet["dateTime"]), packet)
