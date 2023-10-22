from enum import IntEnum
import struct


class Cover:
    # From https://www.home-assistant.io/integrations/cover/ at 2021-03-21
    deviceClassName = (
        "none",
        "awning",
        "blind",
        "curtain",
        "damper",
        "door",
        "garage",
        "gate",
        "shade",
        "shutter",
        "window",
    )


class BinarySensor:
    # From https://www.home-assistant.io/integrations/binary_sensor/ at 2021-03-21
    deviceClassName = (
        "none",
        "battery",
        "battery_charging",
        "cold",
        "connectivity",
        "door",
        "garage_door",
        "gas",
        "heat",
        "light",
        "lock",
        "moisture",
        "motion",
        "moving",
        "occupancy",
        "opening",
        "plug",
        "power",
        "presence",
        "problem",
        "safety",
        "smoke",
        "sound",
        "vibration",
        "window",
    )


class Sensor:
    # From https://www.home-assistant.io/integrations/sensor/ at 2023-01-17
    deviceClassName = (
        "none",
        "apparent_power",
        "aqi",
        "atmospheric_pressure",
        "battery",
        "carbon_dioxide",
        "carbon_monoxide",
        "current",
        "data_rate",
        "data_size",
        "date",
        "distance",
        "duration",
        "energy",
        "enum_class",
        "frequency",
        "gas",
        "humidity",
        "illuminance",
        "irradiance",
        "moisture",
        "monetary",
        "nitrogen_dioxide",
        "nitrogen_monoxide",
        "nitrous_oxide",
        "ozone",
        "pm1",
        "pm10",
        "pm25",
        "power_factor",
        "power",
        "precipitation",
        "precipitation_intensity",
        "pressure",
        "reactive_power",
        "signal_strength",
        "sound_pressure",
        "speed",
        "sulphur_dioxide",
        "temperature",
        "timestamp",
        "volatile_organic_compounds",
        "voltage",
        "volume",
        "water",
        "weight",
        "wind_speed",
    )


class Component:
    name = ("binary_sensor", "sensor", "cover")


class Unit:
    name = ("", "°C", "°F", "K", "%", "km", "m", "dm", "cm", "mm", "μm", "s", "ms")


class Size:
    value = (1, 2, 4, 0)


class MsgType(IntEnum):
    PING_REQ = 0
    PING_MSG = 1
    DISCOVERY_REQ = 2
    DISCOVERY_MSG = 3
    VALUE_REQ = 4
    VALUE_MSG = 5
    CONFIG_REQ = 6
    CONFIG_MSG = 7
    CONFIG_SET_REQ = 8
    SERVICE_REQ = 9


class PingMsg:
    def __init__(self, msg: bytes) -> None:
        self.rssi = struct.unpack("!Bb", msg)[1]


class ConfigItem:
    def __init__(self, msg: bytes) -> None:
        self.id = msg[0]
        self.unit = Unit.name[msg[1]]
        self.signed = (msg[2] & 0x10) != 0
        self.size = Size.value[(msg[2] & 0x0C) >> 2]
        self.precision = int(msg[2] & 0x03)


class DiscoveryMsg:
    def __init__(self, msg: bytes) -> None:
        self.entity_id = msg[1]
        self.component = Component.name[msg[2]]
        if self.component == Component.name[0]:
            self.device_class = BinarySensor.deviceClassName[msg[3]]
        elif self.component == Component.name[1]:
            self.device_class = Sensor.deviceClassName[msg[3]]
        elif self.component == Component.name[2]:
            self.device_class = Cover.deviceClassName[msg[3]]
        else:
            self.device_class = None
        self.unit = Unit.name[msg[4]]
        self.signed = (msg[5] & 0x10) != 0
        self.size = Size.value[(msg[5] & 0x0C) >> 2]
        self.precision = int(msg[5] & 0x03)
        num_cfg_items = msg[6]
        if num_cfg_items > 0:
            self.config_items = list()
            offset = 7
            for i in range(num_cfg_items):
                self.config_items.append(ConfigItem(msg[offset : offset + 3]))
                offset += 3


class ValueItem:
    def __init__(self, msg: bytes) -> None:
        self.entity_id, self.value = struct.unpack("!BI", msg)


class ValueMsg:
    def __init__(self, msg: bytes) -> None:
        self.num_entities = msg[1]
        self.value_items = list()
        offset = 2
        for i in range(self.num_entities):
            self.value_items.append(ValueItem(msg[offset : offset + 5]))
            offset += 5
