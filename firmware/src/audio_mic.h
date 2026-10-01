#pragma once

#include <Arduino.h>
#include <driver/i2s.h>

class AudioMic {
public:
    AudioMic();
    bool begin();
    // Records specified seconds of audio and returns pointer to WAV buffer and its size
    uint8_t* recordWav(int seconds, size_t& wavSize);

private:
    void generateWavHeader(uint8_t* header, size_t wavDataSize, uint32_t sampleRate, uint16_t numChannels, uint16_t bitsPerSample);
    uint8_t* audioBuffer = nullptr;
};

extern AudioMic mic;
