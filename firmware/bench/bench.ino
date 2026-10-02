// Calvin Bench - Teensy 4.1 actuator characterization sketch
//
// Plays torque waveforms uploaded from the host on a 1 kHz timer and streams
// the samples back over USB serial. See ../../PLAN.md (milestones M1, M2, M4).
//
// Left motor:  CAN1 (pins 22/23), ODrive node 1
// Right motor: CAN3 (pins 30/31), ODrive node 2

#include <InstinctusCore.h>
#include "src/WaveformPlayer.h"
#include "src/BenchLink.h"

constexpr uint32_t USB_SERIAL_TIMEOUT_MS = 3000;

void setup() {
    Serial.begin(115200);  // USB serial; the baud rate is ignored
    while (!Serial && millis() < USB_SERIAL_TIMEOUT_MS);
    Serial.println("ok calvin bench");
}

void loop() {
    // TODO (M1): text commands from the host
}
