// spooky-pi Teensy 4.1: drives the LED glasses and reads the two PIRs for the Pi,
// over USB serial. The Pi does all the animation, gamma and brightness; this only
// copies bytes onto the LEDs. Build and flash: scripts/teensy-flash.sh
//
// Pi -> Teensy   LED frame: A5 5A <n> <n x R,G,B> <sum of the RGB bytes & 0xFF>
//                '?': send the hello line and the PIR levels
// Teensy -> Pi   "spooky-teensy <version> leds=<max> pirs=<k> frames=<good> bad=<bad>"  at boot and after '?'
//                "S <levels>"  e.g. "S 01", PIR 1 first; on every change and every 0.5 s
//
// Wiring (5 V brick on VIN with the VUSB-VIN pad cut, grounds shared):
//   pin 1  -> 74AHCT125 -> 330 R -> glasses DIN    (WS2812Serial needs a serial TX pin)
//   pin 2  <- PIR 1 OUT (glasses' left, seen from the front)
//   pin 3  <- PIR 2 OUT
//   power-up  all LEDs flash dim white for 0.4 s (checks the wiring without the Pi)
//   pin 13    on-board LED: always blinking while the firmware runs; 1 Hz waiting, 4 Hz with frames
//
// The code is in firmware.cpp; this file only names the sketch.
