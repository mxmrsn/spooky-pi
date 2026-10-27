// The sketch itself (plain C++ so Arduino doesn't generate prototypes). Protocol: spooky_teensy.ino

#include <Arduino.h>
#include <WS2812Serial.h>

const char *VERSION = "4";
const uint32_t FRAME_TIMEOUT_MS = 2000;  // blank a channel if the Pi goes quiet

// Channel 0: the glasses on pin 1. Channel 1: the handpiece on pin 8. Each needs a serial TX
// pin for WS2812Serial; extra pixels past what the Pi sends are kept dark.
const int GLASSES_PIN = 1, GLASSES_MAX = 64;
const int HAND_PIN = 8, HAND_MAX = 32;

byte glassesDrawing[GLASSES_MAX * 3];
DMAMEM byte glassesDisplay[GLASSES_MAX * 12];
byte handDrawing[HAND_MAX * 3];
DMAMEM byte handDisplay[HAND_MAX * 12];

struct Channel {
  WS2812Serial strip;
  int max;
  uint32_t lastFrame;
  bool blanked;
};
Channel channels[] = {
  {WS2812Serial(GLASSES_MAX, glassesDisplay, glassesDrawing, GLASSES_PIN, WS2812_GRB), GLASSES_MAX, 0, true},
  {WS2812Serial(HAND_MAX, handDisplay, handDrawing, HAND_PIN, WS2812_GRB), HAND_MAX, 0, true},
};
const int NUM_CHANNELS = sizeof(channels) / sizeof(channels[0]);

enum State { SYNC1, SYNC2, COUNT, DATA, SUM };
State state = SYNC1;
int channel = 0;
byte frame[GLASSES_MAX * 3];
int frameLen = 0, got = 0;
byte sum = 0;
uint32_t frames = 0, badFrames = 0;  // reported in the hello line, for debugging the link

void hello() {
  Serial.printf("spooky-teensy %s leds=%d hand=%d frames=%lu bad=%lu\n", VERSION, GLASSES_MAX, HAND_MAX,
                frames, badFrames);
}

void showFrame(Channel &c, const byte *rgb, int n) {
  for (int i = 0; i < c.max; i++) {
    if (i < n) c.strip.setPixel(i, rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]);
    else c.strip.setPixel(i, 0, 0, 0);
  }
  c.strip.show();
}

void feed(byte b) {
  switch (state) {
    case SYNC1:
      if (b == 0xA5) state = SYNC2;
      else if (b == '?') hello();
      break;
    case SYNC2:  // 5A = glasses, 5B = handpiece
      if (b == 0x5A || b == 0x5B) { channel = b - 0x5A; state = COUNT; }
      else state = b == 0xA5 ? SYNC2 : SYNC1;
      break;
    case COUNT:
      if (b > channels[channel].max) { state = SYNC1; break; }
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
        Channel &c = channels[channel];
        showFrame(c, frame, frameLen / 3);
        c.lastFrame = millis();
        c.blanked = false;
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
  for (int i = 0; i < GLASSES_MAX * 3; i++) frame[i] = 24;  // power-up flash: dim white for 0.4 s,
  for (int k = 0; k < NUM_CHANNELS; k++) {                  // so the wiring can be checked without the Pi
    channels[k].strip.begin();
    showFrame(channels[k], frame, channels[k].max);
  }
  delay(400);
  for (int k = 0; k < NUM_CHANNELS; k++) showFrame(channels[k], frame, 0);
  Serial.begin(115200);  // USB serial: the baud rate is ignored
  hello();
}

void loop() {
  while (Serial.available()) feed(Serial.read());

  uint32_t now = millis();
  bool anyLive = false;
  for (int k = 0; k < NUM_CHANNELS; k++) {
    Channel &c = channels[k];
    if (!c.blanked && now - c.lastFrame > FRAME_TIMEOUT_MS) {
      showFrame(c, frame, 0);
      c.blanked = true;
    }
    anyLive |= !c.blanked;
  }

  digitalWrite(LED_BUILTIN, (now / (anyLive ? 125 : 500)) % 2);  // heartbeat: slow idle, fast with frames
}
