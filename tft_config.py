"""ESP32-S3-LCD-1.28
https://www.waveshare.com/wiki/ESP32-S3-LCD-1.28
Firmware: ESP32_GENERIC/firmware_16MiB.bin
"""

from machine import Pin, SPI
import gc9a01

TFA = 0
BFA = 0
WIDE = 0
TALL = 1

def config(rotation=0, buffer_size=0, options=0):
    spi = SPI(1, baudrate=60000000, sck=Pin(6), mosi=Pin(5))

    return gc9a01.GC9A01(
        spi,
        240,
        240,
        reset=Pin(4, Pin.OUT),
        cs=Pin(2, Pin.OUT),
        dc=Pin(3, Pin.OUT),
        backlight=Pin(1, Pin.OUT),
        rotation=rotation,
        options=options,
        buffer_size= buffer_size)
