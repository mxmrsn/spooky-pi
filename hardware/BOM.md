# Spooky-pi wiring

The LED glasses connect to a Teensy 4.1 (firmware: [teensy/spooky_teensy](../teensy/spooky_teensy)), which talks to the Pi over one USB cable. There are no pupil LEDs.

```
Pi 4 ══USB (data)══> Teensy 4.1
5V brick ─┬─> Teensy VIN / GND            (VUSB–VIN pad cut)
          └─> rings 5V / GND
Teensy pin 1 ─> left ring DIN ; left DOUT ─> right ring DIN ; Teensy GND ─ ring GND
```

- **Cut the VUSB–VIN pad** on the Teensy's underside. Otherwise the Pi's USB 5 V and the brick are tied together. USB data still works.
- **Data level:** pin 1 drives DIN directly. 3.3 V data into a 5 V ring is marginal but works here; if a ring misbehaves, add a 74AHCT125 buffer (and 330 Ω in series with DIN) between them.
- **Power dips:** a 1000 µF capacitor across the rings' 5 V/GND and short, thick power leads keep the Teensy from resetting when the LEDs jump in brightness.
- **Pin 13's LED** blinks whenever the firmware runs: 1 Hz while waiting, 4 Hz while frames arrive. Steady on or off means it's stuck or not running. The Teensy blanks the glasses if the Pi goes quiet for 2 s.
- **Budget:** 32 LEDs at full white is about 1.9 A; `max_current_a = 2.0` caps the LEDs and leaves room on the 2.5 A brick for the Teensy.

Flash with `bash scripts/pc/teensy-flash.sh` from your PC (arduino-cli and the Teensy core here; `pi-setup.sh` installs the loader on the Pi). On the Pi the Teensy is `/dev/serial/by-id/usb-Teensyduino_USB_Serial_*`.
