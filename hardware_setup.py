# hardware_setup.py customised for KMRTM28028-SPI 8-Jul-21 ws

# Released under the MIT License (MIT). See LICENSE.
# Copyright (c) 2021 Peter Hinch

# As written, supports:
# ili9341 240x320 displays on Pi Pico
# Initialisation procedure designed to minimise risk of memory fail
# when instantiating the frame buffer. The aim is to do this as early as
# possible before importing other modules.

# WIRING
# Pico      Display
# GPIO Pin
# 5V   na	VCC
# 3v3  36   LED
# IO21 27   RESET 
# IO20 26   D/C
# IO19 25   SD   (AKA MOSI)
# IO18 24   CLK  Hardware SPI0
# GND  23 	GND
# IO17 22   CS
# IO16 21   SDO	 (AKA MISO)
#           Miso is assigned, because SPI0 default pin is used otherwise, not used here

# Pushbuttons are wired between the pin and Gnd 
# remark: using hardware debounce results eliminates (rare) hang ups of RP2040
# Pico pin  Function
# IO11 15   Select next control
# IO12 16   Select previous control
# IO13 17   Select / operate current control
# IO14 19   Increase value of current control
# IO15 20   Decrease value of current control
# n/a  18   Gnd

from machine import Pin, SPI, freq
import gc

from drivers.ili93xx.ili9341 import ILI9341 as SSD
freq(250_000_000)  # RP2 overclock
# Create and export an SSD instance
pdc = Pin(20, Pin.OUT, value=0)  # Arbitrary pins
prst = Pin(21, Pin.OUT, value=1)
pcs = Pin(17, Pin.OUT, value=1)
spi = SPI(0, baudrate=30_000_000, mosi=Pin(19), miso=Pin(16), sck=Pin(18))
gc.collect()  # Precaution before instantiating framebuf
ssd = SSD(spi, pcs, pdc, prst, usd=False)

from gui.core.ugui import Display
# Create and export a Display instance
# Define control buttons
nxt = Pin(11, Pin.IN)  # Move to next control
prev = Pin(12, Pin.IN)  # Move to previous control
sel = Pin(13, Pin.IN)  # Operate current control
increase = Pin(15, Pin.IN)  # Increase control's value
decrease = Pin(14, Pin.IN)  # Decrease control's value
display = Display(ssd, nxt, sel, prev, increase, decrease, encoder=4) # with encoder
#display = Display(ssd, nxt, sel, prev, increase, decrease) # with buttons
