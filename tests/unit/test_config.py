from lora2mqtt import lora2mqtt


def reset_target():
    lora2mqtt.config = None
    lora2mqtt.devices = None


def load_configuration():
    lora2mqtt.load_configuration("tests/unit/fixtures")


def test_load_configuration():
    reset_target()
    load_configuration()
    assert lora2mqtt.config is not None
    assert lora2mqtt.config["MQTT"]["hostname"] == "localhost"
