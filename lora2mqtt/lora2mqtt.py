#!/usr/bin/env python3
import sys
import os.path
from time import time, sleep, localtime, strftime
import logging
import argparse
from configparser import ConfigParser
from collections import OrderedDict
from pyLoraRFM9x import LoRa, ModemConfig
import paho.mqtt.client as mqtt
import json
import jsonpickle
import struct
from messages import DiscoveryMsg, MsgType, PingMsg, ValueMsg, ConfigItem, Cover

PROJECT_NAME = "LoRa2MQTT Gateway Client/Daemon"
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
        prog="LoRa2MQTT Gateway",
        description=PROJECT_NAME,
        epilog="For further details see: " + PROJECT_URL,
    )
    parser.add_argument(
        "-i", "--interactive", help="Interactive mode", action="store_true"
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


def mqtt_create_discovery_cover(device: dict, entity: DiscoveryMsg):
    base_topic = config["MQTT"].get("base_topic")
    device_name = device["name"]
    entity_name = device["entities"][str(entity.entity_id)]
    unique_id = f"{device_name.lower()}_{entity_name.lower()}"

    payload = OrderedDict()
    payload["name"] = entity_name
    payload["device_class"] = entity.device_class
    payload["unique_id"] = unique_id
    payload["object_id"] = unique_id
    payload["device"] = {
        "name": device_name,
        "identifiers": [f"lora2mqtt_{device_name.lower()}"],
        "manufacturer": "Ove Nystas",
        "model": "LoRaNodeGarage",
    }
    payload["state_topic"] = f"{base_topic}/{device_name.lower()}/state"
    payload["command_topic"] = f"{base_topic}/{device_name.lower()}/set"
    payload["value_template"] = f"{{{{ value_json.{entity_name.lower()} }}}}"

    logger.debug(jsonpickle.encode(payload, unpicklable=False))

    return payload


def mqtt_create_discovery_binary_sensor(device: dict, entity: DiscoveryMsg):
    base_topic = config["MQTT"].get("base_topic")
    device_name = device["name"]
    entity_name = device["entities"][str(entity.entity_id)]
    unique_id = f"{device_name.lower()}_{entity_name.lower()}"

    payload = OrderedDict()
    payload["name"] = entity_name
    payload["device_class"] = entity.device_class
    payload["unique_id"] = unique_id
    payload["object_id"] = unique_id
    payload["device"] = {
        "name": device_name,
        "identifiers": [f"lora2mqtt_{device_name.lower()}"],
        "manufacturer": "Ove Nystas",
        "model": "LoRaNodeGarage",
    }
    payload["state_topic"] = f"{base_topic}/{device_name.lower()}/state"
    payload["value_template"] = f"{{{{ value_json.{entity_name.lower()} }}}}"

    return payload


def mqtt_create_discovery_sensor(device: dict, entity: DiscoveryMsg):
    base_topic = config["MQTT"].get("base_topic")
    device_name = device["name"]
    entity_name = device["entities"][str(entity.entity_id)]
    unique_id = f"{device_name.lower()}_{entity_name.lower()}"

    payload = OrderedDict()
    payload["name"] = entity_name
    payload["device_class"] = entity.device_class
    payload["unique_id"] = unique_id
    payload["object_id"] = unique_id
    payload["device"] = {
        "name": device_name,
        "identifiers": [f"lora2mqtt_{device_name.lower()}"],
        "manufacturer": "Ove Nystas",
        "model": "LoRaNodeGarage",
    }
    payload["state_topic"] = f"{base_topic}/{device_name.lower()}/state"
    payload["unit_of_measurement"] = entity.unit
    payload["value_template"] = f"{{{{ value_json.{entity_name.lower()} }}}}"
    payload["suggested_display_precision "] = entity.precision
    payload["state_class"] = "measurement"

    return payload


def mqtt_discovery_announce_entity(device: dict, entity: DiscoveryMsg):
    """
    Discovery Announcement of one entity in one device.
    """
    discovery_prefix = config["MQTT"].get("discovery_prefix")
    entity_name = device["entities"][str(entity.entity_id)]
    discovery_topic = f"{discovery_prefix}/{entity.component}/{device['name'].lower()}/{entity_name.lower()}/config"

    payload = None
    if entity.component == "cover":
        payload = mqtt_create_discovery_cover(device, entity)
    elif entity.component == "binary_sensor":
        payload = mqtt_create_discovery_binary_sensor(device, entity)
    elif entity.component == "sensor":
        payload = mqtt_create_discovery_sensor(device, entity)
    else:
        logger.warning(f"Discovery for {entity.component} is not implemented.")

    if payload:
        mqtt_client.publish(discovery_topic, json.dumps(payload), 1, True)
        logger.info(f"Published entity {entity_name} to {discovery_topic}")
    else:
        logger.warning("No discovery payload to publish.")


def mqtt_discovery_announce_device(id: int, device: dict):
    """
    Discovery Announcement of one device.
    """
    logger.info(
        f"Announcing LoRa device {id}:{device['name']} to MQTT broker for auto-discovery ..."
    )

    if id == 1:  # Only have discovery messages for id 1 now
        for entity in discovery_msgs:
            mqtt_discovery_announce_entity(device, entity)
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
            disc_json = json.load(f)
            for item in disc_json:
                disc_msg = DiscoveryMsg.from_dict(item)
                discovery_msgs.append(disc_msg)
    except FileNotFoundError as e:
        logger.warning(f"Could not find file {file_name}, will create a new")
    except json.decoder.JSONDecodeError as e:
        logger.warning(
            f"Failed to decode file {file_name}, perform a new discovery to recreate it"
        )


def lora_parse_msg(payload):
    if str(payload.header_from) not in devices.keys():
        logger.warning(f"LoRa msg from unknown device {payload.header_from}")
        logger.debug(bytes.hex(payload.message, " "))
        return

    MSG_TYPE_MASK = 0x0F
    msg_type = payload.header_flags & MSG_TYPE_MASK
    logger.info(f"msg_type: {msg_type}")

    if msg_type == int(MsgType.PING_REQ):
        logger.info("Got a ping request")
        lora_parse_ping_req(payload)
    elif msg_type == int(MsgType.PING_MSG):
        logger.info("Got a ping message")
        lora_parse_ping_msg(payload)
    elif msg_type == int(MsgType.DISCOVERY_REQ):
        logger.info("Got a discovery request")
        lora_parse_discovery_req(payload)
    elif msg_type == int(MsgType.DISCOVERY_MSG):
        logger.info("Got a discovery message")
        lora_parse_discovery_msg(payload)
    elif msg_type == int(MsgType.VALUE_REQ):
        logger.info("Got a value request")
        lora_parse_value_req(payload)
    elif msg_type == int(MsgType.VALUE_MSG):
        logger.info("Got a value message")
        lora_parse_value_msg(payload)
    elif msg_type == int(MsgType.CONFIG_REQ):
        logger.info("Got a config request")
        lora_parse_config_req(payload)
    elif msg_type == int(MsgType.CONFIG_MSG):
        logger.info("Got a config message")
        lora_parse_config_msg(payload)
    elif msg_type == int(MsgType.CONFIG_SET_REQ):
        logger.info("Got a config set request")
        lora_parse_config_set_req(payload)
    elif msg_type == int(MsgType.SERVICE_REQ):
        logger.info("Got a service request")
        lora_parse_servive_req(payload)
    else:
        logger.info(f"Got the unsupported message type {msg_type}")


def lora_parse_ping_req(payload):
    logger.debug(bytes.hex(payload.message, " "))
    lora_send_ping_msg(payload.header_from, payload.rssi)


def lora_parse_ping_msg(payload):
    logger.debug(bytes.hex(payload.message, " "))
    msg_decoded = PingMsg(payload.message)
    logger.debug(msg_decoded.to_json())


def lora_parse_discovery_req(payload):
    logger.debug(bytes.hex(payload.message, " "))


def lora_parse_discovery_msg(payload):
    logger.debug(bytes.hex(payload.message, " "))
    msg_decoded = DiscoveryMsg.from_bytes(payload.message)
    logger.debug(jsonpickle.encode(msg_decoded, unpicklable=False))
    msg_decoded_json = msg_decoded.to_json()

    modified = False
    found = False
    for i, item in enumerate(discovery_msgs):
        if item.entity_id == msg_decoded.entity_id:
            found = True
            if item != msg_decoded:
                logger.warning(
                    f"Entity {msg_decoded.entity_id} is different than in discovery_msgs"
                )
                discovery_msgs[i] = msg_decoded
                modified = True
            else:
                logger.debug(
                    f"Entity {msg_decoded.entity_id} is same as in discovery_msgs"
                )

    if not found:
        logger.warning(f"Entity {msg_decoded.entity_id} not in discovery_msgs")
        discovery_msgs.append(msg_decoded)
        modified = True

    if modified:
        with open("discovery.json", mode="w") as f:
            f.write(jsonpickle.encode(discovery_msgs, unpicklable=False))

    mqtt_discovery_announce_entity(devices[str(payload.header_from)], msg_decoded)


def lora_parse_value_req(payload):
    logger.debug(bytes.hex(payload.message, " "))
    logger.warning("Unexpected value request message")


def lora_parse_value_msg(payload):
    logger.debug(bytes.hex(payload.message, " "))
    msg_decoded = ValueMsg(payload.message)
    logger.debug(jsonpickle.encode(msg_decoded, unpicklable=False))

    values = dict()
    device = devices[str(payload.header_from)]
    for value_item in msg_decoded.value_items:
        found = False
        for disc_item in discovery_msgs:
            if disc_item.entity_id == value_item.entity_id:
                found = True
                entity_name = device["entities"][str(value_item.entity_id)].lower()

                if disc_item.component == "cover":
                    values[entity_name] = Cover.state[value_item.value]
                elif disc_item.component == "binary_sensor":
                    values[entity_name] = (
                        "OFF" if Cover.state[value_item.value] == 0 else "ON"
                    )
                else:
                    if disc_item.signed and (value_item.value & 0x80000000):
                        value_item.value = -0x100000000 + value_item.value
                    if disc_item.precision > 0:
                        value_item.value /= 10**disc_item.precision
                    values[entity_name] = value_item.value

        if not found:
            logger.warning(
                f"Could not find entity {value_item.entity_id} in discovery_msgs"
            )

    if values:
        state_topic = (
            f"{config['MQTT'].get('base_topic')}/{device['name'].lower()}/state"
        )
        logger.info(f"Publishing to {state_topic} ...")
        logger.debug(json.dumps(values))

        msg_info = mqtt_client.publish(
            state_topic,
            payload=json.dumps(values, separators=(",", ":")),
            qos=1,
            retain=False,
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
    logger.warning("Unexpected config request message")


def lora_parse_config_msg(payload):
    logger.debug(bytes.hex(payload.message, " "))


def lora_parse_config_set_req(payload):
    logger.debug(bytes.hex(payload.message, " "))
    logger.warning("Unexpected config set request message")


def lora_parse_servive_req(payload):
    logger.debug(bytes.hex(payload.message, " "))
    logger.warning("Unexpected service request message")


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


def lora_send_ping_req(address: int) -> None:
    """
    Send a ping request message to a device with specified address.
    Valid address is 0-255 where 255 is broadcasted to all devices.
    """
    if 0 > address > 255:
        logger.error(f"Address {address} is invalid")
        return

    # message = b"\x01\x02\x03\x04\x05\x06"  # Ping request ID
    if lora.send_to_wait(b"", address, MsgType.PING_REQ):
        logger.info("LoRa Ping request message sent!")
    else:
        logger.warning("No ack from LoRa recipient")


def lora_send_ping_msg(address: int, rssi: int) -> None:
    """
    Send a ping response message to a device with specified address.
    Valid address is 0-254.
    """
    if 0 > address > 255:
        logger.error(f"Address {address} is invalid")
        return
    if -32768 > rssi > 32767:
        logger.error(f"Rssi value {rssi} is invalid")
        return

    if lora.send_to_wait(struct.pack("!h", rssi), address, MsgType.PING_REQ):
        logger.info("LoRa Ping response message sent!")
    else:
        logger.warning("No ack from LoRa recipient")


def lora_send_discovery_req(address: int, entity_id: int) -> None:
    """
    Send a discovery request message to a device with specified address.
    Valid address is 0-255. Where 255 is broadcast to all devices.
    Valid entity_id is 0-255. Where 255 is request values from all entities.
    """
    if 0 > address > 255:
        logger.error(f"Address {address} is invalid")
        return
    if 0 > entity_id > 255:
        logger.error(f"Entity ID {entity_id} is invalid")
        return

    if lora.send_to_wait(struct.pack("!B", entity_id), address, MsgType.DISCOVERY_REQ):
        logger.info("LoRa Discovery request message sent!")
    else:
        logger.warning("No ack from LoRa recipient")


def lora_send_config_req(address: int, entity_id: int) -> None:
    """
    Send a config request message to a device with specified address.
    Valid address is 0-255. Where 255 is broadcast to all devices.
    Valid entity_id is 0-255. Where 255 is request values from all entities.
    """
    if 0 > address > 255:
        logger.error(f"Address {address} is invalid")
        return
    if 0 > entity_id > 255:
        logger.error(f"Entity ID {entity_id} is invalid")
        return

    if lora.send_to_wait(struct.pack("!B", entity_id), address, MsgType.CONFIG_REQ):
        logger.info("LoRa Config request message sent!")
    else:
        logger.warning("No ack from LoRa recipient")


def lora_send_config_set_req(address: int, entity_id: int, config_items: list) -> None:
    """
    Send a config set request message to a device with specified address.
    Valid address is 0-254.
    Valid entity_id is 0-254.
    """
    if 0 > address > 255:
        logger.error(f"Address {address} is invalid")
        return
    if 0 > entity_id > 255:
        logger.error(f"Entity ID {entity_id} is invalid")
        return
    pass


def lora_send_service_req(address: int, entity_id: int, service: int) -> None:
    """
    Send a service request message to a device with specified address.
    Valid address is 0-254.
    Valid entity_id is 0-254.
    Valid service is 0-255.
    """
    if 0 > address > 255:
        logger.error(f"Address {address} is invalid")
        return
    if 0 > entity_id > 255:
        logger.error(f"Entity ID {entity_id} is invalid")
        return
    if 0 > service > 255:
        logger.error(f"Service {service} is invalid")
        return

    if lora.send_to_wait(
        struct.pack("!BB", entity_id, service), address, MsgType.SERVICE_REQ
    ):
        logger.info("LoRa Service request message sent!")
    else:
        logger.warning("No ack from LoRa recipient")


def cmd_parse(line: str):
    line_split = line.split()

    if line == "" or line_split[0] == "h":
        print(
            f"h - Print help\n"
            f"p <address> - Send a ping request to device with address <address>\n"
            f"d <address> <entity id> - Send a discovery request of entity id <entity id> to device with address <address>\n"
            f"c <address> <entity id> - Send a config request of entity id <entity id> to device with address <address>\n"
            f"c <address> <entity id> <TBD> - Send a config set request of entity id <entity id> to device with address <address>\n"
            f"s <address> <entity id> <service> - Send a service request of service <service> and entity id <entity id> to device with address <address>\n"
            f"l <c|e|w|i|d> - Change debug level to c=critical, e=error, w=warning, i=info or d=debug"
        )
    elif line_split[0] == "p":
        if len(line_split) == 2:
            address = int(line_split[1])
            lora_send_ping_req(address)

    elif line_split[0] == "d":
        if len(line_split) == 3:
            address = int(line_split[1])
            entity_id = int(line_split[2])
            lora_send_discovery_req(address, entity_id)

    elif line_split[0] == "c":
        if len(line_split) == 3:
            address = int(line_split[1])
            entity_id = int(line_split[2])
            lora_send_config_req(address, entity_id)
        elif len(line_split) == 4:
            address = int(line_split[1])
            entity_id = int(line_split[2])
            lora_send_config_set_req(address, entity_id, None)

    elif line_split[0] == "c":
        if len(line_split) == 4:
            address = int(line_split[1])
            entity_id = int(line_split[2])
            service = int(line_split[3])
            lora_send_service_req(address, entity_id, service)

    elif line_split[0] == "l":
        if len(line_split) == 2:
            level = line_split[1]
            if level == "c":
                logger.setLevel(logging.CRITICAL)
            elif level == "e":
                logger.setLevel(logging.ERROR)
            elif level == "w":
                logger.setLevel(logging.WARNING)
            elif level == "i":
                logger.setLevel(logging.INFO)
            elif level == "d":
                logger.setLevel(logging.DEBUG)


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

    lora_send_ping_req(1)

    logger.info("Initialization complete, starting MQTT publish loop")

    print(parsed_args)

    if not parsed_args.interactive:
        logger.info("loop_forever()")
        mqtt_client.loop_forever()
    else:
        logger.info("loop_start()")
        mqtt_client.loop_start()
        in_line = ""
        while in_line != "exit":
            in_line = input()
            cmd_parse(in_line)

        mqtt_client.loop_stop()


if __name__ == "__main__":
    main()
