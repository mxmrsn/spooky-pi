# Spooky-pi driver board: parts and connectors

Digi-Key cart upload: [digikey_bom.csv](digikey_bom.csv). Use myLists / BOM Manager, choose **Upload a list**, then map the *Digi-Key Part Number* and *Quantity* columns. Prices and stock were checked on 2026-10-22.

Not on the list because they're already on hand: the 2x17 IDC socket and 1.27 mm ribbon, hook-up wire, WAGO lever connectors, and the Molex crimp tools.

## Architecture

```
Pi 4 (CanaKit case)                              Driver board (Chip Quik SBBTH3040-1)
 pins 1-6  : fan (4 = 5V, 6 = GND), untouched     
 pins 7-40 : 2x17 IDC socket ══ribbon══> J-GPIO 2x17 box header
                                              │
 USB brick ─ Adafruit 3628 ─ WAGO split ─> J-PWR (Mini-Fit Jr 2)   5V/GND bus on the board
                                              ├─ U1 74AHCT125 ─ R2 330Ω ─> J-RING (Mini-Fit Jr 3, single row) ─> 16-LED ring
                                              ├─ Q1 IRLB3813 low side ───> J-AIM  (Mini-Fit Jr 2) ─> aiming LED
                                              ├─ J-PIR1 (PicoBlade 3) ─> PIR 1
                                              └─ J-PIR2 (PicoBlade 3) ─> PIR 2
```

The Pi's 5 V never connects to the board. Its grounds do: the ribbon carries GND on pins 9/14/20/25/30/34/39.

## Connector map

All connectors are **wire-to-wire**. These Molex PCB headers don't fit a 0.1" grid, so the board side of each is a short pigtail soldered to the perfboard and zip-tied through a hole for strain relief.

| Ref | Family | Pins | Board-side half | Cable-side half | Wire |
|---|---|---|---|---|---|
| J-PWR | Mini-Fit Jr 2-ckt (2x1) | 1 = 5V, 2 = GND | **plug** (male pins) | **receptacle** on the brick lead | 20 AWG |
| J-AIM | Mini-Fit Jr 2-ckt (2x1) | 1 = 5V, 2 = LED− (switched) | **receptacle** | **plug** on the LED lead | 20–24 AWG |
| J-RING | Mini-Fit Jr 3-ckt single row | 1 = 5V, 2 = DIN, 3 = GND | receptacle | plug on the ring lead | 22–24 AWG |
| J-PIR1/2 | PicoBlade 3-ckt | 1 = 5V, 2 = OUT, 3 = GND | receptacle | plug on the PIR lead | 26–28 AWG |
| J-GPIO | 2x17 IDC box header | Pi pins 7–40 | box header | IDC socket on the Pi | ribbon |

**Why the genders are swapped on J-PWR and J-AIM:** both use the same 2-circuit housing. Swapping which side gets the plug means the brick lead can't mate with the J-AIM pigtail. The only possible mix-up is plugging the LED straight into the brick lead, which just turns it on. Keep live 5V on sockets (the receptacle) wherever possible.

**Pico-SPOX isn't used** because it's wire-to-board only (no free-hanging plug or male crimp). That's why the ring and aiming LED moved to Mini-Fit Jr.

## Pin map (Pi BCM numbering)

| Function | GPIO | Pi pin | Ribbon conductor (pin 7 = #1) |
|---|---|---|---|
| Aiming LED gate | GPIO17 | 11 | 5 |
| PIR 1 | GPIO23 | 16 | 10 |
| PIR 2 | GPIO24 | 18 | 12 |
| NeoPixel data (SPI MOSI) | GPIO10 | 19 | 13 |
| GND | – | 9, 14, 20, 25, 30, 34, 39 | 3, 8, 14, 19, 24, 28, 33 |

## Build notes

- **U1 74AHCT125 (AHCT, not HC).** Tie the used channel's OE pin to GND, and its VCC to the brick's 5 V. Tie unused OE pins to 5 V and unused inputs to GND. Put C2 (0.1 µF) right across VCC/GND.
- **C1 1000 µF** goes across the ring's 5V/GND near J-RING. Watch the polarity.
- **Q1:** GPIO17 → R1 100 Ω → gate; R3 10 kΩ from gate to GND, so the LED stays off while the Pi boots. Drain to J-AIM pin 2, source to GND.
- **The perfboard has no rails.** Run a bare or 20 AWG bus for 5 V and GND.
- **WAGO 221s** are for the power side only, e.g. at the brick to split 5V/GND. They take about 24–12 AWG, so they're too coarse for the 26 AWG PIR wiring.
- **Check PicoBlade wire fit:** the 50079 sockets need thin-wall 26–28 AWG insulation. Silicone wire is often too thick to fit the insulation grip, so test-crimp your hook-up wire first.
- **Check the IDC socket fit:** the 2x17 socket body sits slightly past its end pins and might hit the fan plug on pins 4/6. Test the fit before crimping, and mark pin 7 on both the socket and the Pi.
- **NeoPixel ring and PIRs:** solder the cable to the ring's pads. The PIRs (Adafruit 189) have a 3-pin 0.1" header, so solder the lead to it or use a 0.1" IDC/Dupont housing.
