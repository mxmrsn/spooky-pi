// The sketch itself (plain C++ so Arduino doesn't generate prototypes). Protocol: spooky_teensy.ino

#include <Arduino.h>
#include <WS2812Serial.h>

const char *VERSION = "2";
const int LED_PIN = 1;
const int MAX_LEDS = 64;  // the glasses have 34; extra pixels are sent dark
const int PIR_PINS[] = {2, 3};
const int NUM_PIRS = sizeof(PIR_PINS) / sizeof(PIR_PINS[0]);
const uint32_t FRAME_TIMEOUT_MS = 2000;  // blank the LEDs if the Pi goes quiet
const uint32_t STATUS_MS = 500;

byte drawingMemory[MAX_LEDS * 3];
DMAMEM byte displayMemory[MAX_LEDS * 12];
WS2812Serial leds(MAX_LEDS, displayMemory, drawingMemory, LED_PIN, WS2812_GRB);

enum State { SYNC1, SYNC2, COUNT, DATA, SUM };
State state = SYNC1;
byte frame[MAX_LEDS * 3];
int frameLen = 0, got = 0;
byte sum = 0;

uint32_t lastFrame = 0, lastStatus = 0;
uint32_t frames = 0, badFrames = 0;  // reported in the hello line, for debugging the link
bool blanked = true;
int levels[NUM_PIRS];

void hello() {
  Serial.printf("spooky-teensy %s leds=%d pirs=%d frames=%lu bad=%lu\n", VERSION, MAX_LEDS, NUM_PIRS,
                frames, badFrames);
}

void sendLevels() {
  Serial.print("S ");
  for (int i = 0; i < NUM_PIRS; i++) Serial.print(levels[i] ? '1' : '0');
  Serial.print('\n');
  lastStatus = millis();
}

void showFrame(const byte *rgb, int n) {
  for (int i = 0; i < MAX_LEDS; i++) {
    if (i < n) leds.setPixel(i, rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]);
    else leds.setPixel(i, 0, 0, 0);
  }
  leds.show();
}

void feed(byte b) {
  switch (state) {
    case SYNC1:
      if (b == 0xA5) state = SYNC2;
      else if (b == '?') { hello(); sendLevels(); }
      break;
    case SYNC2:
      state = b == 0x5A ? COUNT : (b == 0xA5 ? SYNC2 : SYNC1);
      break;
    case COUNT:
      if (b > MAX_LEDS) { state = SYNC1; break; }
      frameLen = b * 3; got = 0; sum = 0;
      state = frameLen ? DATA : SUM;
      break;
    case DATA:
      frame[got++] = b;
      sum += b;
      if (got == frameLen) state = SUM;
      break;
    case SUM:
      if (b == sum) {
        showFrame(frame, frameLen / 3);
        lastFrame = millis();
        blanked = false;
        frames++;
      } else {
        badFrames++;
      }
      state = SYNC1;
      break;
  }
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  for (int i = 0; i < NUM_PIRS; i++) {
    pinMode(PIR_PINS[i], INPUT_PULLDOWN);  // an unplugged PIR reads quiet
    levels[i] = digitalRead(PIR_PINS[i]);
  }
  leds.begin();
  for (int i = 0; i < MAX_LEDS * 3; i++) frame[i] = 24;  // power-up flash: dim white for 0.4 s,
  showFrame(frame, MAX_LEDS);                              // so the wiring can be checked without the Pi
  delay(400);
  showFrame(frame, 0);
  Serial.begin(115200);  // USB serial: the baud rate is ignored
  hello();
}

void loop() {
  while (Serial.available()) feed(Serial.read());

  uint32_t now = millis();
  if (!blanked && now - lastFrame > FRAME_TIMEOUT_MS) {
    showFrame(frame, 0);
    blanked = true;
  }

  bool changed = false;
  for (int i = 0; i < NUM_PIRS; i++) {
    int v = digitalRead(PIR_PINS[i]);
    if (v != levels[i]) { levels[i] = v; changed = true; }
  }
  if (changed || now - lastStatus >= STATUS_MS) sendLevels();

  digitalWrite(LED_BUILTIN, (now / (blanked ? 500 : 125)) % 2);  // heartbeat: slow idle, fast with frames
}
