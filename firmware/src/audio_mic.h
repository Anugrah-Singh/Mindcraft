#pragma once

#include <Arduino.h>
#include <driver/i2s.h>

class AudioMic {
public:
    AudioMic();
    bool begin();

    // Waits for speech, records until the speaker stops talking, and streams the audio to
    // the laptop over USB serial (see audio_mic.cpp for the wire format).
    // Returns true if speech was captured.
    bool recordToSerial();
};

extern AudioMic mic;
