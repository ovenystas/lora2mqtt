#!/usr/bin/env python3
from pyLoraRFM9x import LoRa, ModemConfig
import paho.mqtt.client as mqtt

# Logging function
def print_line(text, error = False, warning=False, sd_notify=False, console=True):
    timestamp = strftime('%Y-%m-%d %H:%M:%S', localtime())
    if console:
        if error:
            print(Fore.RED + Style.BRIGHT + f'[{timestamp}] ' + Style.RESET_ALL + f'{text}' + Style.RESET_ALL, file=sys.stderr)
        elif warning:
            print(Fore.YELLOW + f'[{timestamp}] ' + Style.RESET_ALL + f'{text}' + Style.RESET_ALL)
        else:
            print(Fore.GREEN + f'[{timestamp}] ' + Style.RESET_ALL + f'{text}' + Style.RESET_ALL)
    timestamp_sd = strftime('%b %d %H:%M:%S', localtime())
    if sd_notify:
        sd_notifier.notify(f'STATUS={timestamp_sd} - {unidecode(text)}.'))

# Eclipse Paho callbacks - http://www.eclipse.org/paho/clients/python/docs/#callbacks
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print_line('MQTT connection established', console=True, sd_notify=True)
        print()
    else:
        print_line(f'Connection error with result code {str(rc)} - {mqtt.connack_string(rc)}', error=True)
        #kill main thread
        os._exit(1)

def on_publish(client, userdata, mid):
    print_line('Data successfully published.')
    pass

# MQTT connection
if reporting_mode == 'homeassistant-mqtt':
    print_line('Connecting to MQTT broker ...')
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_publish = on_publish
    if reporting_mode == 'mqtt-json':
        mqtt_client.will_set('{}/$announce'.format(base_topic), payload='{}', retain=True)
    elif reporting_mode == 'mqtt-smarthome':
        mqtt_client.will_set('{}/connected'.format(base_topic), payload='0', retain=True)

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
        print_line('MQTT connection error. Please check your settings in the configuration file "config.ini"', error=True, sd_notify=True)
        sys.exit(1)
    else:
        if reporting_mode == 'mqtt-smarthome':
            mqtt_client.publish('{}/connected'.format(base_topic), payload='1', retain=True)
        if reporting_mode != 'thingsboard-json':
            mqtt_client.loop_start()
            sleep(1.0) # some slack to establish the connection

# Discovery Announcement
if reporting_mode == 'homeassistant-mqtt':
    print_line('Announcing Mi Flora devices to MQTT broker for auto-discovery ...')
    for [flora_name, flora] in flores.items():
        state_topic = f'{base_topic}/sensor/{flora_name.lower()}/state')
        for [sensor, params] in parameters.items():
            discovery_topic = f'homeassistant/sensor/{flora_name.lower()}/{sensor}/config')
            payload = OrderedDict()
            payload['name'] = f"{flora_name} {sensor.title()}")
            payload['unique_id'] = f"{flora['mac'].lower().replace(':', '')}-{sensor}")
            payload['unit_of_measurement'] = params['unit']
            if 'device_class' in params:
                payload['device_class'] = params['device_class']
            payload['state_topic'] = state_topic
            payload['value_template'] = f"{{{{ value_json.{sensor} }}}}"
            payload['device'] = {
                    'identifiers' : [f"MiFlora{flora['mac'].lower().replace(':', '')}"],
                    'connections' : [["mac", flora['mac'].lower()]],
                    'manufacturer' : 'Xiaomi',
                    'name' : flora_name,
                    'model' : 'MiFlora Plant Sensor (HHCCJCY01)',
                    'sw_version': flora['firmware']
            }
            mqtt_client.publish(discovery_topic, json.dumps(payload), 1, True)

print_line('Initialization complete, starting MQTT publish loop', console=False, sd_notify=True)


# This is our callback function that runs when a message is received
def on_recv(payload):
    print("From:", payload.header_from)
    print("RSSI: {}; SNR: {}".format(payload.rssi, payload.snr))

# Use chip select 1. GPIO pin 5 will be used for interrupts and set reset pin to 25
# The address of this device will be set to 2
lora = LoRa(channel=1, interrupt=24, this_address=2, reset_pin=25,
            modem_config=ModemConfig.Bw125Cr45Sf128, freq=868, tx_power=14,
            acks=True)

lora.on_recv = on_recv

# Send a message to a recipient device with address 10
# Retry sending the message twice if we don't get an  acknowledgment from the recipient
message = "Hello there!"
status = lora.send_to_wait(message, 10, retries=0)

if status is True:
    print("Message sent!")
else:
    print("No acknowledgment from recipient")