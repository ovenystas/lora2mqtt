#!/usr/bin/env python3
import sys
import os.path
from time import time, sleep, localtime, strftime
import logging
from colorama import init as colorama_init
from colorama import Fore, Style
import argparse
from configparser import ConfigParser

# import sdnotify
from unidecode import unidecode
from pyLoraRFM9x import LoRa, ModemConfig
import paho.mqtt.client as mqtt
import json
from enum import Enum

PROJECT_NAME = "Lora2mqtt gateway Client/Daemon"
PROJECT_URL = "https://github.com/ovenystas/lora2mqtt"

config = None
devices = None
lora = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)


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
    # From https://www.home-assistant.io/integrations/sensor/ at 2021-03-21
    deviceClassName = (
        "none",
        "battery",
        "current",
        "energy",
        "humidity",
        "illuminance",
        "signal_strength",
        "temperature",
        "power",
        "power_factor",
        "pressure",
        "timestamp",
        "voltage",
    )


class Component:
    name = ["binary_sensor", "sensor", "cover"]


class MsgType(Enum):
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


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=PROJECT_NAME, epilog="For further details see: " + PROJECT_URL
    )
    parser.add_argument(
        "--config",
        help="Specify a config.ini file",
        default="config.ini",
    )
    parser.add_argument(
        "--devices",
        help="Specify a devices.json file",
        default="devices.json",
    )
    parsed_args = parser.parse_args()
    return parsed_args


def print_intro():
    print(Fore.GREEN + Style.BRIGHT)
    print(PROJECT_NAME)
    print("Source:", PROJECT_URL)
    print(Style.RESET_ALL)


def on_mqtt_connect(client, userdata, flags, rc):
    """
    Eclipse Paho callback on MQTT connection - http://www.eclipse.org/paho/clients/python/docs/#callbacks
    """
    if rc == 0:
        logger.info("MQTT connection established")
        # log.print("MQTT connection established", console=True, sd_notify=True)
        # print()
    else:
        logger.error(
            f"Connection error with result code {str(rc)} - {mqtt.connack_string(rc)}"
        )
        # log.print(
        #     f"Connection error with result code {str(rc)} - {mqtt.connack_string(rc)}",
        #     error=True,
        # )
        # kill main thread
        os._exit(1)


def on_mqtt_publish(client, userdata, mid):
    """
    Eclipse Paho callback on MQTT publish - http://www.eclipse.org/paho/clients/python/docs/#callbacks
    """
    print_line("Data successfully published.")


def load_configuration(config_file_path):
    """
    Load configuration file
    """
    global config
    config = ConfigParser(delimiters=("=",), inline_comment_prefixes=("#"))
    config.optionxform = str
    try:
        with open(config_file_path) as config_file:
            config.read_file(config_file)
    except OSError:
        logger.error(f'No configuration file "{config_file_path}" found')
        # log.print(f'No configuration file "{config_file_path}" found', error=True, sd_notify=True)
        sys.exit(1)

    config["Daemon"]["enabled"] = config["Daemon"].get("enabled", "True")
    config["MQTT"]["base_topic"] = config["MQTT"].get("base_topic", "lora2mqtt").lower()
    config["MQTT"]["discovery_prefix"] = (
        config["MQTT"].get("discovery_prefix", "homeassistant").lower()
    )
    config["Daemon"]["period"] = config["Daemon"].get("period", "300")


def check_configuration():
    """
    Check configuration
    """
    logger.info("Configuration accepted")
    # log.print("Configuration accepted", console=False, sd_notify=True)


def mqtt_connect():
    """
    MQTT connection
    """
    logger.info("Connecting to MQTT broker ...")
    # log.print("Connecting to MQTT broker ...")
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_publish = on_mqtt_publish

    if config["MQTT"].getboolean("tls", False):
        # According to the docs, setting PROTOCOL_SSLv23 "Selects the highest protocol version
        # that both the client and server support. Despite the name, this option can select
        # “TLS” protocols as well as “SSL”" - so this seems like a resonable default
        mqtt_client.tls_set(
            ca_certs=config["MQTT"].get("tls_ca_cert", None),
            keyfile=config["MQTT"].get("tls_keyfile", None),
            certfile=config["MQTT"].get("tls_certfile", None),
            tls_version=ssl.PROTOCOL_SSLv23,
        )

    mqtt_username = os.environ.get("MQTT_USERNAME", config["MQTT"].get("username"))
    mqtt_password = os.environ.get(
        "MQTT_PASSWORD", config["MQTT"].get("password", None)
    )

    if mqtt_username:
        mqtt_client.username_pw_set(mqtt_username, mqtt_password)
    try:
        mqtt_client.connect(
            os.environ.get(
                "MQTT_HOSTNAME", config["MQTT"].get("hostname", "localhost")
            ),
            port=int(os.environ.get("MQTT_PORT", config["MQTT"].get("port", "1883"))),
            keepalive=config["MQTT"].getint("keepalive", 60),
        )
    except:
        logger.error(
            'MQTT connection error. Please check your settings in the configuration file "config.ini"'
        )
        # log.print(
        #     'MQTT connection error. Please check your settings in the configuration file "config.ini"',
        #     error=True,
        #     sd_notify=True,
        # )
        sys.exit(1)

    logger.info("Connection established to MQTT broker")


def load_devices(devices_file_path):
    logger.info(f"Loading devices from {devices_file_path} ...")
    global devices
    with open(devices_file_path) as devices_file:
        devices = json.load(devices_file)
    logger.info("Devices loaded")


def mqtt_discovery_announce():
    """
    Discovery Announcement
    """
    logger.info("Announcing LoRa devices to MQTT broker for auto-discovery ...")
    # log.print("Announcing LoRa devices to MQTT broker for auto-discovery ...")

    base_topic = config["MQTT"].get("base_topic")
    discovery_prefix = config["MQTT"].get("discovery_prefix")

    for node in devices["devices"]:
        state_topic = f"{base_topic}/sensor/{node.nodeId}/state"
        for [sensor, params] in parameters.items():
            discovery_topic = (
                f"{discovery_prefix}/sensor/{flora_name.lower()}/{sensor}/config"
            )
            payload = OrderedDict()
            payload["name"] = f"{flora_name} {sensor.title()}"
            payload["unit_of_measurement"] = params["unit"]
            if "device_class" in params:
                payload["device_class"] = params["device_class"]
            payload["state_topic"] = state_topic
            mqtt_client.publish(discovery_topic, json.dumps(payload), 1, True)

    logger.info("All LoRa devices announced to MQTT broker")


def on_lora_receive(payload):
    """
    Callback function that runs when a LoRa message is received
    """
    print("From:", payload.header_from)
    print("RSSI: {}; SNR: {}".format(payload.rssi, payload.snr))

    lora_parse_msg(payload)


def lora_parse_msg(payload):
    MSG_TYPE_MASK = 0x0F
    msg_type = payload.flags & MSG_TYPE_MASK


#   switch (msg_type) {
#     case MsgType::ping_req:
#       sendPing(rxMsg.header.src, rxMsg.rssi);
#       break;

#     case MsgType::discovery_req:
#       if (mOnDiscoveryReqMsgFunc) {
#         uint8_t entityId = rxMsg.payload[0];
#         mOnDiscoveryReqMsgFunc(entityId);
#       }
#       break;

#     case MsgType::value_req:
#       if (mOnValueReqMsgFunc) {
#         uint8_t entityId = rxMsg.payload[0];
#         mOnValueReqMsgFunc(entityId);
#       }
#       break;

#     case MsgType::config_req:
#       if (mOnConfigReqMsgFunc) {
#         uint8_t entityId = rxMsg.payload[0];
#         mOnConfigReqMsgFunc(entityId);
#       }
#       break;

#     case MsgType::configSet_req:
#       if (mOnConfigSetReqMsgFunc) {
#         LoRaConfigValuePayloadT* payload =
#             reinterpret_cast<LoRaConfigValuePayloadT*>(rxMsg.payload);
#         mOnConfigSetReqMsgFunc(*payload);
#       }
#       break;

#     case MsgType::service_req:
#       if (mOnServiceReqMsgFunc) {
#         if (rxMsg.header.len == sizeof(LoRaServiceItemT)) {
#           LoRaServiceItemT* item =
#               reinterpret_cast<LoRaServiceItemT*>(rxMsg.payload);
#           mOnServiceReqMsgFunc(*item);
#         }
#       }
#       break;

#     default:
#       return -1;
#   }
#   return 0;
# }


def lora_init():
    """
    Use chip select 1. GPIO pin 5 will be used for interrupts and set reset pin to 25
    The address of this device will be set to 0
    """
    global lora
    lora = LoRa(
        channel=1,
        interrupt=24,
        this_address=0,
        reset_pin=25,
        modem_config=ModemConfig.Bw125Cr45Sf128,
        freq=868,
        tx_power=14,
        acks=True,
    )

    lora.on_recv = on_lora_receive


def lora_send_hello():
    """
    Send a message to a recipient device with address 10
    Retry sending the message twice if we don't get an  acknowledgment from the recipient
    """
    message = "Hello there!"
    status = lora.send_to_wait(message, 10, retries=0)

    if status is True:
        print("LoRa message sent!")
    else:
        print("No ack from LoRa recipient")


def lora_send_ping(address):
    """
    Send a ping message to a device with specified address.
    Valid address is 0-255 where 255 is broadcasted to all devices.
    """
    # TODO: Range check
    message = b"\x01"  # Ping request ID
    status = lora.send_to_wait(message, address)
    if status is True:
        print("LoRa message sent!")
    else:
        print("No ack from LoRa recipient")


def main():
    parsed_args = parse_arguments()
    colorama_init()
    print_intro()

    load_configuration(parsed_args.config)
    check_configuration()

    reporting_mode = "homeassistant-mqtt"

    mqtt_connect()
    load_devices(parsed_args.devices)
    mqtt_discovery_announce()

    lora_init()
    lora_send_hello()

    print_line(
        "Initialization complete, starting MQTT publish loop",
        console=False,
        sd_notify=True,
    )


if __name__ == "__main__":
    main()
