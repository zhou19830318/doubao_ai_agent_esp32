# ESP32-S3 Smart Voice Assistant

This is a smart voice assistant project based on the ESP32-S3 development board, using MicroPython to enable voice interaction with large language models. The project connects to a voice assistant API via WebSocket for functionality.

## Features

- High-quality audio capture and playback using I2S interface for microphone and speaker.
- Supports VAD (Voice Activity Detection) to intelligently detect user speech and silence.
- Real-time communication with cloud-based large language models via WebSocket.
- Supports voice input and output in both Chinese and English.
- Conversation history preservation and contextual understanding.
- Supports conversation interruption feature.

## Hardware Requirements

- ESP32-S3 development board.
- I2S Microphone (INMP441).
- I2S Speaker (max98357).
- Stable WiFi connection.

## Pin Configuration

### Microphone I2S Configuration
- SCK: GPIO9
- WS: GPIO8
- SD: GPIO7

### Speaker I2S Configuration
- SCK: GPIO11
- WS: GPIO12
- SD: GPIO10

## Software Dependencies

- MicroPython firmware (for ESP32-S3).
- Custom aiohttp library (included in the project).

## Usage Instructions

1. Flash the MicroPython firmware onto the ESP32-S3 development board.
2. Modify the WiFi credentials and API key in the `config.py` file:
   ```python
   WIFI_SSID = "Your WiFi Name"
   WIFI_PASSWORD = "Your WiFi Password"
   API_KEY = "Your API Key"
   instructions = '''Your Prompt'''