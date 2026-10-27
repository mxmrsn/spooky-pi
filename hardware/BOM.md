# Spooky-pi wiring

The LED glasses connect to a Teensy 4.1 (firmware: [teensy/spooky_teensy](../teensy/spooky_teensy)), which talks to the Pi over one USB cable. There are no pupil LEDs.

```
Pi 4 ══USB (data)══> Teensy 4.1
5V brick ─┬─> Teensy VIN / GND            (VUSB–VIN pad cut)
          └─> rings 5V / GND
Teensy pin 1 ─> left ring DIN ; left DOUT ─> right ring DIN ; Teensy GND ─ ring GND
Teensy pin 8 ─> handpiece strip DIN (8 LEDs) ; its 5V / GND from the brick, GND shared with the Teensy
```

- **Cut the VUSB–VIN pad** on the Teensy's underside. Otherwise the Pi's USB 5 V and the brick are tied together. USB data still works.
- **Data level:** pin 1 drives DIN directly. 3.3 V data into a 5 V ring is marginal but works here; if a ring misbehaves, add a 74AHCT125 buffer (and 330 Ω in series with DIN) between them.
- **Power dips:** a 1000 µF capacitor across the rings' 5 V/GND and short, thick power leads keep the Teensy from resetting when the LEDs jump in brightness.
- **Pin 13's LED** blinks whenever the firmware runs: 1 Hz while waiting, 4 Hz while frames arrive. Steady on or off means it's stuck or not running. The Teensy blanks the glasses if the Pi goes quiet for 2 s.
- **Budget:** the glasses are capped at `[leds] max_current_a = 2.0` and the handpiece at `[handpiece] max_current_a = 0.4`; their looks normally use far less. Lower the glasses' cap if the brick (2.5 A) struggles.
- **Handpiece:** firmware v4 or later (it drives pins 1 and 8). Only the Teensy's serial TX pins work for this: 1, 8, 14, 17, 20, 24, 29, 35, 47, 53.

Flash with `bash scripts/pc/teensy-flash.sh` from your PC (arduino-cli and the Teensy core here; `pi-setup.sh` installs the loader on the Pi). On the Pi the Teensy is `/dev/serial/by-id/usb-Teensyduino_USB_Serial_*`.
