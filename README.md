# lora2mqtt

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
[![linting: pylint](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/PyCQA/pylint)

LoRa to MQTT gateway.

## Dependencies

```bash
sudo apt install gcc g++ python3-dev
```

## Development

This repository uses pre-commit git hook management tool.

### Setup environment

Install system dependencies.

```bash
sudo apt install gcc g++ python3.10-dev
```

Use a Python Virtual Environment and install project dependencies in it.

```bash
python3 -m venv .venv --prompt lora2mqtt
python3 -m pip install requirements-dev.txt
```

Activate the Python Virtual Environment.

```bash
source .venv/bin/activate
```

Install pre-commit git hook.

```bash
pre-commit install
```

### Run all pre-commit hooks

```bash
pre-commit run --all-files
```

### Run unit tests

```bash
python3 -m pytest
```

### Run integration tests

```bash
python3 -m pytest
```
