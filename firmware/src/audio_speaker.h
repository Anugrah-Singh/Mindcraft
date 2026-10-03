#pragma once

#include <Arduino.h>
#include "BluetoothA2DPSource.h"

class AudioSpeaker {
public:
    AudioSpeaker();
    void begin();
    void loop();
    void stop();
    bool isConnected();
    bool isAudioStarted();
    bool isPlaying();
    String getStatusString();

    // Clip playback: the host streams 16-bit mono 22.05 kHz PCM over USB.
    void clipBegin();                                   // reset buffer, hold until pre-buffered
    size_t freeSamples();                               // room left in the ring buffer
    void pushSamples(const int16_t* samples, size_t n); // append source samples
    void clipEnd();                                     // no more data coming; play out the tail

    static void queueStartupBeep();

private:
    static int32_t a2dpDataCallback(Frame *frame, int32_t frame_count);
    static void btConnectionStateCallback(esp_a2d_connection_state_t state, void *ptr);
    static void btAudioStateCallback(esp_a2d_audio_state_t state, void *ptr);
};

extern AudioSpeaker speaker;
