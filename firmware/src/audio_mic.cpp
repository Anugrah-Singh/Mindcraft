#include "audio_mic.h"
#include "config.h"
#include "display.h"

#define I2S_MIC_PORT I2S_NUM_0

AudioMic::AudioMic() {}

bool AudioMic::begin() {
    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate = SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT, // INMP441 uses 24-bit in 32-bit slot
        .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,  // Standard 2-channel I2S framing
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 6,
        .dma_buf_len = 256,
        .use_apll = false,
        .tx_desc_auto_clear = false,
        .fixed_mclk = 0
    };

    i2s_pin_config_t pin_config = {
        .bck_io_num = I2S_MIC_SCK_PIN,
        .ws_io_num = I2S_MIC_WS_PIN,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num = I2S_MIC_SD_PIN
    };

    esp_err_t err = i2s_driver_install(I2S_MIC_PORT, &i2s_config, 0, NULL);
    if (err != ESP_OK) return false;

    err = i2s_set_pin(I2S_MIC_PORT, &pin_config);
    return (err == ESP_OK);
}

// ---------------------------------------------------------------------------
// Voice-activity-gated recording.
//
// Listens until speech starts, streams it to the laptop, and stops after the speaker has
// been quiet for VAD_END_SILENCE_MS. Nothing is sent while waiting; a short pre-roll is
// kept so the first syllable is not clipped.
//
// Wire format (the length is not known up front):
//   "@R*\n", then repeated chunks [uint16 LE byte_count][PCM bytes], ended by a zero count.
//   PCM is 16-bit mono at MIC_OUT_RATE. If no speech is heard, only "@R*\n" + zero count.
// No log lines may be printed while a recording is being sent.
// ---------------------------------------------------------------------------
#define VAD_FRAME           441     // 20 ms at 22.05 kHz
#define VAD_PREROLL_FRAMES  25      // 500 ms kept from before speech was detected
#define VAD_CALIB_FRAMES    15      // 300 ms used to measure the room's noise floor
#define VAD_START_FRAMES    5       // 100 ms above threshold = speech has started
#define VAD_END_SILENCE_MS  1200
#define VAD_MAX_WAIT_MS     8000    // give up if nobody speaks
#define VAD_MAX_SPEECH_MS   20000   // hard cap on one recording

static void sendChunk(const int16_t* pcm, size_t samples) {
    uint16_t bytes = (uint16_t)(samples * sizeof(int16_t));
    uint8_t len[2] = { (uint8_t)(bytes & 0xFF), (uint8_t)(bytes >> 8) };
    Serial.write(len, 2);
    Serial.write((const uint8_t*)pcm, bytes);
}

bool AudioMic::recordToSerial() {
    int16_t* preroll = (int16_t*)malloc(VAD_PREROLL_FRAMES * VAD_FRAME * sizeof(int16_t));
    if (!preroll) {
        Serial.println("[MIC] Not enough memory for the pre-roll buffer.");
        return false;
    }

    int32_t rawChunk[256];          // 128 left/right pairs
    int16_t frame[VAD_FRAME];
    size_t frameLen = 0;

    float prevInput = 0.0f, prevOutput = 0.0f;
    const float DC_R = 0.995f;
    const float MIC_GAIN = 8.0f;    // applied after >>16 (24-bit mic data -> 16-bit)
    bool haveHalf = false;
    float half = 0.0f;

    // VAD state
    size_t frameCount = 0;          // frames processed so far
    float minLevel = 1e9f, floorLevel = 0.0f, threshold = 400.0f;
    size_t above = 0, silence = 0, streamedFrames = 0;
    size_t prerollHead = 0, prerollFill = 0;   // circular buffer of frames
    bool streaming = false, headerSent = false, done = false;
    uint32_t sentBytes = 0;

    const size_t maxWaitFrames   = VAD_MAX_WAIT_MS / 20;
    const size_t endSilenceFrames = VAD_END_SILENCE_MS / 20;
    const size_t maxSpeechFrames = VAD_MAX_SPEECH_MS / 20;
    unsigned long startTime = millis();

    while (!done && millis() - startTime < (unsigned long)(VAD_MAX_WAIT_MS + VAD_MAX_SPEECH_MS + 3000)) {
        size_t bytesRead = 0;
        esp_err_t res = i2s_read(I2S_MIC_PORT, rawChunk, sizeof(rawChunk), &bytesRead, pdMS_TO_TICKS(100));
        if (res != ESP_OK || bytesRead == 0) {
            delay(1);
            continue;
        }
        size_t pairs = bytesRead / (2 * sizeof(int32_t));
        for (size_t i = 0; i < pairs && !done; i++) {
            float x = (float)(rawChunk[i * 2] >> 16);  // LEFT slot (L/R pin -> GND)
            float y = x - prevInput + DC_R * prevOutput;
            prevInput = x;
            prevOutput = y;
            float v = y * MIC_GAIN;
            if (v > 32767.0f) v = 32767.0f;
            if (v < -32768.0f) v = -32768.0f;

            // Decimate 44.1 kHz -> 22.05 kHz by averaging sample pairs.
            if (!haveHalf) { half = v; haveHalf = true; continue; }
            haveHalf = false;
            frame[frameLen++] = (int16_t)((half + v) * 0.5f);
            if (frameLen < VAD_FRAME) continue;
            frameLen = 0;

            // ---- one 20 ms frame is complete ----
            float sum = 0;
            for (size_t k = 0; k < VAD_FRAME; k++) sum += (float)abs((int)frame[k]);
            float level = sum / VAD_FRAME;
            frameCount++;
            if (frameCount % 5 == 0) {   // every 100 ms: live level meter on the OLED (partial update)
                display.recordLevel((uint16_t)level, streaming, (uint32_t)streamedFrames * 20);
            }

            if (streaming) {
                sendChunk(frame, VAD_FRAME);
                sentBytes += VAD_FRAME * sizeof(int16_t);
                streamedFrames++;
                silence = (level > threshold) ? 0 : silence + 1;
                if (silence >= endSilenceFrames || streamedFrames >= maxSpeechFrames) done = true;
                continue;
            }

            // keep the most recent frames as pre-roll
            memcpy(preroll + prerollHead * VAD_FRAME, frame, VAD_FRAME * sizeof(int16_t));
            prerollHead = (prerollHead + 1) % VAD_PREROLL_FRAMES;
            if (prerollFill < VAD_PREROLL_FRAMES) prerollFill++;

            if (frameCount <= VAD_CALIB_FRAMES) {
                // Measure the room noise; the quietest frame is used so that speech which
                // starts immediately after the button press does not raise the floor.
                if (level < minLevel) minLevel = level;
                if (frameCount == VAD_CALIB_FRAMES) {
                    floorLevel = minLevel < 800.0f ? minLevel : 800.0f;
                    threshold = floorLevel * 3.0f + 150.0f;
                    if (threshold < 400.0f) threshold = 400.0f;
                }
                continue;
            }

            if (level > threshold) {
                above++;
            } else {
                above = 0;
                floorLevel = 0.98f * floorLevel + 0.02f * level;   // follow slow noise changes
                threshold = floorLevel * 3.0f + 150.0f;
                if (threshold < 400.0f) threshold = 400.0f;
            }

            if (above >= VAD_START_FRAMES) {
                // Speech started: send header, then the pre-roll in chronological order.
                Serial.print("@R*\n");
                headerSent = true;
                size_t first = (prerollHead + VAD_PREROLL_FRAMES - prerollFill) % VAD_PREROLL_FRAMES;
                for (size_t f = 0; f < prerollFill; f++) {
                    sendChunk(preroll + ((first + f) % VAD_PREROLL_FRAMES) * VAD_FRAME, VAD_FRAME);
                    sentBytes += VAD_FRAME * sizeof(int16_t);
                }
                streaming = true;
                silence = 0;
            } else if (frameCount - VAD_CALIB_FRAMES >= maxWaitFrames) {
                done = true;   // nobody spoke
            }
        }
    }

    if (!headerSent) Serial.print("@R*\n");
    uint8_t endMarker[2] = { 0, 0 };
    Serial.write(endMarker, 2);
    Serial.flush();
    free(preroll);

    Serial.printf("[MIC] %s: sent %u bytes (%.1f s), noise floor %.0f, threshold %.0f\n",
                  streaming ? "Speech recorded" : "No speech heard", (unsigned)sentBytes,
                  sentBytes / 2.0f / MIC_OUT_RATE, floorLevel, threshold);
    return streaming;
}

AudioMic mic;
