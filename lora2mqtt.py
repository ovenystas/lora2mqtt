#!/usr/bin/env python3
import sys
import os.path
from time import time, sleep, localtime, strftime
from colorama import init as colorama_init
from colorama import Fore, Back, Style
import argparse
from configparser import ConfigParser
import sdnotify
from unidecode import unidecode
from pyLoraRFM9x import LoRa, ModemConfig
import paho.mqtt.client as mqtt
import json


project_name = 'Lora2mqtt gateway Client/Daemon'
project_url = 'https://github.com/ovenystas/lora2mqtt'

config = None
devices = None


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
    "window"
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
    "window"
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
    "voltage"
  )


class Component:
  name = [
    "binary_sensor",
    "sensor",
    "cover"
  ]


def parse_arguments():
    parser = argparse.ArgumentParser(description=project_name, epilog='For further details see: ' + project_url)
    parser.add_argument('--config_dir', help='set directory where config.ini is located', default=sys.path[0])
    parsed_args = parser.parse_args()
    return parsed_args


def print_intro():
    print(Fore.GREEN + Style.BRIGHT)
    print(project_name)
    print('Source:', project_url)
    print(Style.RESET_ALL)


class Log:

    def __init__(self):
        self.sd_notifier = sdnotify.SystemdNotifier()


    def print(self, text, error=False, warning=False, sd_notify=False, console=True):
        ''' 
        Logging function
        '''
        local_time = localtime()

        if console:
            timestamp = strftime('%Y-%m-%d %H:%M:%S', local_time)
            if error:
                print(f'{Fore.RED}{Style.BRIGHT}[{timestamp}] {Style.RESET_ALL}{text}{Style.RESET_ALL}', file=sys.stderr)
            elif warning:
                print(f'{Fore.YELLOW}[{timestamp}] {Style.RESET_ALL}{text}{Style.RESET_ALL}')
            else:
                print(f'{Fore.GREEN}[{timestamp}] {Style.RESET_ALL}{text}{Style.RESET_ALL}')

        if sd_notify:
            timestamp_sd = strftime('%b %d %H:%M:%S', local_time)
            self.sd_notifier.notify(f'STATUS={timestamp_sd} - {unidecode(text)}.')


def on_mqtt_connect(client, userdata, flags, rc):
    '''
    Eclipse Paho callback on MQTT connection - http://www.eclipse.org/paho/clients/python/docs/#callbacks
    '''
    if rc == 0:
        log.print('MQTT connection established', console=True, sd_notify=True)
        print()
    else:
        log.print(f'Connection error with result code {str(rc)} - {mqtt.connack_string(rc)}', error=True)
        #kill main thread
        os._exit(1)


def on_mqtt_publish(client, userdata, mid):
    '''
    Eclipse Paho callback on MQTT publish - http://www.eclipse.org/paho/clients/python/docs/#callbacks
    '''
    print_line('Data successfully published.')


def load_configuration(config_dir):
    '''
    Load configuration file
    '''
    global config
    config = ConfigParser(delimiters=('=', ), inline_comment_prefixes=('#'))
    config.optionxform = str
    try:
        with open(os.path.join(config_dir, 'config.ini')) as config_file:
            config.read_file(config_file)
    except IOError:
        log.print('No configuration file "config.ini"', error=True, sd_notify=True)
        sys.exit(1)

    config['Daemon']['enabled'] = config['Daemon'].get('enabled', 'True')
    config['MQTT']['base_topic'] = config['MQTT'].get('base_topic', 'lora2mqtt').lower()
    config['MQTT']['discovery_prefix'] = config['MQTT'].get('discovery_prefix', 'homeassistant').lower()
    config['Daemon']['period'] = config['Daemon'].get('period', '300')


def check_configuration():
    '''
    Check configuration
    '''
    log.print('Configuration accepted', console=False, sd_notify=True)


def mqtt_connect():
    '''
    MQTT connection
    '''
    log.print('Connecting to MQTT broker ...')
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_publish = on_mqtt_publish

    if config['MQTT'].getboolean('tls', False):
        # According to the docs, setting PROTOCOL_SSLv23 "Selects the highest protocol version
        # that both the client and server support. Despite the name, this option can select
        # “TLS” protocols as well as “SSL”" - so this seems like a resonable default
        mqtt_client.tls_set(
            ca_certs=config['MQTT'].get('tls_ca_cert', None),
            keyfile=config['MQTT'].get('tls_keyfile', None),
            certfile=config['MQTT'].get('tls_certfile', None),
            tls_version=ssl.PROTOCOL_SSLv23
        )

    mqtt_username = os.environ.get("MQTT_USERNAME", config['MQTT'].get('username'))
    mqtt_password = os.environ.get("MQTT_PASSWORD", config['MQTT'].get('password', None))

    if mqtt_username:
        mqtt_client.username_pw_set(mqtt_username, mqtt_password)
    try:
        mqtt_client.connect(os.environ.get('MQTT_HOSTNAME', config['MQTT'].get('hostname', 'localhost')),
                            port=int(os.environ.get('MQTT_PORT', config['MQTT'].get('port', '1883'))),
                            keepalive=config['MQTT'].getint('keepalive', 60))
    except:
        log.print('MQTT connection error. Please check your settings in the configuration file "config.ini"',
                   error=True, sd_notify=True)
        sys.exit(1)


def load_devices():
    global devices
    with open('devices.json') as json_file:
        devices = json.load(json_file)


def mqtt_discovery_announce():
    '''
    Discovery Announcement
    '''
    log.print('Announcing LoRa devices to MQTT broker for auto-discovery ...')
    base_topic = config['MQTT'].get('base_topic')
    for node in devices['devices']:
        state_topic = f'{base_topic}/sensor/{node}/state'
        for [sensor, params] in parameters.items():
            discovery_topic = f'{discovery_prefix}/sensor/{flora_name.lower()}/{sensor}/config'
            payload = OrderedDict()
            payload['name'] = f"{flora_name} {sensor.title()}"
            payload['unit_of_measurement'] = params['unit']
            if 'device_class' in params:
                payload['device_class'] = params['device_class']
            payload['state_topic'] = state_topic
            mqtt_client.publish(discovery_topic, json.dumps(payload), 1, True)


def on_lora_receive(payload):
    '''
    Callback function that runs when a LoRa message is received
    '''
    print("From:", payload.header_from)
    print("RSSI: {}; SNR: {}".format(payload.rssi, payload.snr))


def lora_init():
    '''
    Use chip select 1. GPIO pin 5 will be used for interrupts and set reset pin to 25
    The address of this device will be set to 0
    '''
    lora = LoRa(channel=1, interrupt=24, this_address=0, reset_pin=25,
                modem_config=ModemConfig.Bw125Cr45Sf128, freq=868, tx_power=14,
                acks=True)

    lora.on_recv = on_lora_receive


def lora_send_hello():
    '''
    Send a message to a recipient device with address 10
    Retry sending the message twice if we don't get an  acknowledgment from the recipient
    '''
    message = "Hello there!"
    status = lora.send_to_wait(message, 10, retries=0)

    if status is True:
        print("LoRa message sent!")
    else:
        print("No ack from LoRa recipient")


def main():
    parsed_args = parse_arguments()
    colorama_init()
    print_intro()

    load_configuration(parsed_args.config_dir)
    check_configuration()

    reporting_mode = 'homeassistant-mqtt'

    mqtt_connect()
    load_devices()
    mqtt_discovery_announce()

    lora_init()
    lora_send_hello()

    print_line('Initialization complete, starting MQTT publish loop', console=False, sd_notify=True)


if __name__ == "__main__":
    log = Log()
    main()
