#!/usr/bin/env python3
import sys
import os.path
from time import time, sleep, localtime, strftime
import logging
import argparse
from configparser import ConfigParser
from collections import OrderedDict

# import sdnotify
from pyLoraRFM9x import LoRa, ModemConfig
import paho.mqtt.client as mqtt
import json
import jsonpickle
import messages

PROJECT_NAME = "Lora2mqtt gateway Client/Daemon"
PROJECT_VERSION = "0.0.1"
PROJECT_URL = "https://github.com/ovenystas/lora2mqtt"

config = None
devices = None
lora = None
discovery_msgs = list()

mqtt_client = mqtt.Client()


class CustomFormatter(logging.Formatter):
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    # format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    format = "%(levelname)s: %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: grey + format + reset,
        logging.INFO: grey + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(CustomFormatter())
logger.addHandler(console_handler)


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
    print(f"{PROJECT_NAME} v{PROJECT_VERSION}")
    print("Source:", PROJECT_URL)


def on_mqtt_connect(client, userdata, flags, rc):
    """
    Eclipse Paho callback on MQTT connection
    http://www.eclipse.org/paho/clients/python/docs/#callbacks
    """
    if rc == 0:
        logger.info("MQTT connection established")
    else:
        logger.error("MQTT connect error")
        os._exit(1)


def on_mqtt_disconnect(client, userdata, rc):
    """
    Eclipse Paho callback on MQTT disconnection
    http://www.eclipse.org/paho/clients/python/docs/#callbacks
    """
    logging.info("MQTT Disconnected with result code: %s", rc)


def on_mqtt_publish(client, userdata, mid):
    """
    Eclipse Paho callback on MQTT publish - http://www.eclipse.org/paho/clients/python/docs/#callbacks
    """
    logger.info("MQTT Data successfully published.")


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
        logger.error(f"Configuration file {config_file_path} not found")
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


def mqtt_connect():
    """
    MQTT connection
    """
    logger.info("Connecting to MQTT broker ...")
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_disconnect = on_mqtt_disconnect
    mqtt_client.on_publish = on_mqtt_publish

    if config["MQTT"].getboolean("tls", False):
        # According to the docs, setting PROTOCOL_SSLv23 "Selects the highest protocol version
        # that both the client and server support. Despite the name, this option can select
        # "TLS" protocols as well as "SSL" - so this seems like a resonable default
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
        sys.exit(1)

    logger.info("Connection established to MQTT broker")


def load_devices(devices_file_path):
    logger.info(f"Loading devices from {devices_file_path} ...")
    global devices
    with open(devices_file_path) as devices_file:
        devices = json.load(devices_file)
    logger.info("...devices loaded")


def mqtt_create_discovery_cover(entity, device):
    payload = OrderedDict()
    entity_name = device["entities"][str(entity["entity_id"])]
    payload["name"] = entity_name
    payload["device_class"] = entity["device_class"]
    payload["device"] = {
        "name": device["name"],
        "identifiers": [f"lora2mqtt_{device['name'].lower()}"],
        "manufacturer": "Ove Nystås",
        "model": "LoRaNodeGarage",
        "via_device": "LoRa2MQTT",
    }
    payload[
        "state_topic"
    ] = f"{config['MQTT'].get('base_topic')}/{device['name'].lower()}/state"

    return payload


def mqtt_create_discovery_binary_sensor(entity, device):
    payload = OrderedDict()
    entity_name = device["entities"][str(entity["entity_id"])]
    payload["name"] = entity_name
    payload["device_class"] = entity["device_class"]
    payload["device"] = {
        "name": device["name"],
        "identifiers": [f"lora2mqtt_{device['name'].lower()}"],
        "manufacturer": "Ove Nystås",
        "model": "LoRaNodeGarage",
        "via_device": "LoRa2MQTT",
    }
    payload[
        "state_topic"
    ] = f"{config['MQTT'].get('base_topic')}/{device['name'].lower()}/state"

    return payload


def mqtt_create_discovery_sensor(entity, device):
    payload = OrderedDict()
    entity_name = device["entities"][str(entity["entity_id"])]
    payload["name"] = entity_name
    payload["device_class"] = entity["device_class"]
    payload["device"] = {
        "name": device["name"],
        "identifiers": [f"lora2mqtt_{device['name'].lower()}"],
        "manufacturer": "Ove Nystås",
        "model": "LoRaNodeGarage",
        "via_device": "LoRa2MQTT",
    }
    payload[
        "state_topic"
    ] = f"{config['MQTT'].get('base_topic')}/{device['name'].lower()}/state"
    payload["unit_of_measurement"] = entity["unit"]
    payload["value_template"] = f"{{{{ value_json.{entity_name.lower()} }}}}"

    return payload


def mqtt_discovery_announce_device(id: int, device):
    """
    Discovery Announcement of one device
    """
    logger.info(
        f"Announcing LoRa device {id}:{device['name']} to MQTT broker for auto-discovery ..."
    )

    discovery_prefix = config["MQTT"].get("discovery_prefix")

    if id == 1:  # Only have discovery messages for id 1 now
        for entity in discovery_msgs:
            entity_name = device["entities"][str(entity["entity_id"])]
            discovery_topic = f"{discovery_prefix}/{entity['component']}/{device['name'].lower()}/{entity_name.lower()}/config"

            payload = None
            if entity["component"] == "cover":
                payload = mqtt_create_discovery_cover(entity, device)
            elif entity["component"] == "binary_sensor":
                payload = mqtt_create_discovery_binary_sensor(entity, device)
            elif entity["component"] == "sensor":
                payload = mqtt_create_discovery_sensor(entity, device)
            else:
                logger.warning(
                    f"Discovery for {entity['component']} is not implemented."
                )

            if payload:
                mqtt_client.publish(discovery_topic, json.dumps(payload), 1, True)
                logger.info(f"Published entity {entity_name} to {discovery_topic}")
            else:
                logger.warning("No discovery payload to publish.")
    else:
        logger.warning(f"Device {id} has no discovery")


def mqtt_discovery_announce_all():
    """
    Discovery Announcement of all devices
    """
    logger.info("Announcing All LoRa devices to MQTT broker for auto-discovery ...")

    for id, device in devices.items():
        mqtt_discovery_announce_device(int(id), device)

    logger.info("All LoRa devices announced to MQTT broker")


def on_lora_receive(payload):
    """
    Callback function that runs when a LoRa message is received
    """
    logger.info(
        f"LoRa msg from {payload.header_from}, RSSI={payload.rssi}, SNR={payload.snr}"
    )
    lora_parse_msg(payload)


def lora_load_discovery():
    file_name = "discovery.json"
    try:
        with open(file_name) as f:
            discovery_msgs.extend(json.load(f))
    except FileNotFoundError as e:
        logger.warning(f"Could not find file {file_name}, will create a new")
    except json.decoder.JSONDecodeError as e:
        logger.warning(
            f"Failed to decode file {file_name}, perform a new discovery to recreate it"
        )


def lora_parse_msg(payload):
    if str(payload.header_from) not in devices.keys():
        logger.warn(f"LoRa msg from unknown device {payload.header_from}")
        logger.debug(bytes.hex(payload.message, " "))
        return

    MSG_TYPE_MASK = 0x0F
    msg_type = payload.header_flags & MSG_TYPE_MASK
    logger.info(f"msg_type: {msg_type}")

    if msg_type == int(messages.MsgType.PING_REQ):
        logger.info("Got a ping request")
        lora_parse_ping_req(payload)
    elif msg_type == int(messages.MsgType.PING_MSG):
        logger.info("Got a ping message")
        lora_parse_ping_msg(payload)
    elif msg_type == int(messages.MsgType.DISCOVERY_REQ):
        logger.info("Got a discovery request")
        lora_parse_discovery_req(payload)
    elif msg_type == int(messages.MsgType.DISCOVERY_MSG):
        logger.info("Got a discovery message")
        lora_parse_discovery_msg(payload)
    elif msg_type == int(messages.MsgType.VALUE_REQ):
        logger.info("Got a value request")
        lora_parse_value_req(payload)
    elif msg_type == int(messages.MsgType.VALUE_MSG):
        logger.info("Got a value message")
        lora_parse_value_msg(payload)
    elif msg_type == int(messages.MsgType.CONFIG_REQ):
        logger.info("Got a config request")
        lora_parse_config_req(payload)
    elif msg_type == int(messages.MsgType.CONFIG_MSG):
        logger.info("Got a config message")
        lora_parse_config_msg(payload)
    elif msg_type == int(messages.MsgType.CONFIG_SET_REQ):
        logger.info("Got a config set request")
        lora_parse_config_set_req(payload)
    elif msg_type == int(messages.MsgType.SERVICE_REQ):
        logger.info("Got a service request")
        lora_parse_servive_req(payload)
    else:
        logger.info(f"Got the unsupported message type {msg_type}")


def lora_parse_ping_req(payload):
    logger.debug(bytes.hex(payload.message, " "))


def lora_parse_ping_msg(payload):
    logger.debug(bytes.hex(payload.message, " "))
    msg_decoded = messages.PingMsg(payload.message)
    logger.debug(jsonpickle.encode(msg_decoded, unpicklable=False))


def lora_parse_discovery_req(payload):
    logger.debug(bytes.hex(payload.message, " "))


def lora_parse_discovery_msg(payload):
    logger.debug(bytes.hex(payload.message, " "))
    msg_decoded = messages.DiscoveryMsg(payload.message)
    logger.debug(jsonpickle.encode(msg_decoded, unpicklable=False))
    msg_decoded_json = jsonpickle.encode(msg_decoded, unpicklable=False)
    msg_decoded_json_dict = json.loads(msg_decoded_json)

    if msg_decoded_json_dict not in discovery_msgs:
        logger.warning(f"Entity {msg_decoded.entity_id} not in discovery_msgs")
        discovery_msgs.append(msg_decoded_json_dict)
        with open("discovery.json", mode="w") as f:
            f.write(jsonpickle.encode(discovery_msgs, unpicklable=False))


def lora_parse_value_req(payload):
    logger.debug(bytes.hex(payload.message, " "))


def lora_parse_value_msg(payload):
    logger.debug(bytes.hex(payload.message, " "))
    msg_decoded = messages.ValueMsg(payload.message)
    logger.debug(jsonpickle.encode(msg_decoded, unpicklable=False))

    values = dict()
    device = devices[str(payload.header_from)]
    for value_item in msg_decoded.value_items:
        found = False
        for disc_item in discovery_msgs:
            if disc_item["entity_id"] == value_item.entity_id:
                found = True

                if disc_item["signed"] and (value_item.value & 0x80000000):
                    value_item.value = -0x100000000 + value_item.value
                if disc_item["precision"] > 0:
                    value_item.value /= 10 ** disc_item["precision"]

                entity_name = device["entities"][str(value_item.entity_id)]
                values[entity_name.lower()] = value_item.value

        if not found:
            logger.warning(
                f"Could not find entity {value_item.entity_id} in discovery_msgs"
            )

    if values:
        state_topic = (
            f"{config['MQTT'].get('base_topic')}/{device['name'].lower()}/state"
        )
        logger.info(f"Publishing to {state_topic} ...")
        msg_info = mqtt_client.publish(
            state_topic, payload=json.dumps(values), qos=1, retain=False
        )
        msg_info.wait_for_publish(timeout=5)
        if msg_info.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("...done")
        elif msg_info.rc == mqtt.MQTT_ERR_NO_CONN:
            logger.error("...no connection")
        elif msg_info.rc == mqtt.MQTT_ERR_QUEUE_SIZE:
            logger.error("...send queue is full")
        else:
            logger.error("...unknown error")


def lora_parse_config_req(payload):
    logger.debug(bytes.hex(payload.message, " "))


def lora_parse_config_msg(payload):
    logger.debug(bytes.hex(payload.message, " "))


def lora_parse_config_set_req(payload):
    logger.debug(bytes.hex(payload.message, " "))


def lora_parse_servive_req(payload):
    logger.debug(bytes.hex(payload.message, " "))


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
        crypto=None,
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
        logger.info("LoRa Hello message sent!")
    else:
        logger.warning("No ack from LoRa recipient")


def lora_send_ping(address):
    """
    Send a ping message to a device with specified address.
    Valid address is 0-255 where 255 is broadcasted to all devices.
    """
    # TODO: Range check
    # message = b"\x01\x02\x03\x04\x05\x06"  # Ping request ID
    message_type = 0  # Ping request
    status = lora.send_to_wait(b"", address, message_type)
    if status is True:
        logger.info("LoRa Ping message sent!")
    else:
        logger.warn("No ack from LoRa recipient")


def main():
    jsonpickle.set_encoder_options("json", indent=2)
    parsed_args = parse_arguments()
    print_intro()

    load_configuration(parsed_args.config)
    check_configuration()

    load_devices(parsed_args.devices)

    lora_load_discovery()
    lora_init()

    mqtt_connect()
    mqtt_discovery_announce_all()

    lora_send_ping(1)

    logger.info("Initialization complete, starting MQTT publish loop")

    mqtt_client.loop_forever()


if __name__ == "__main__":
    main()
