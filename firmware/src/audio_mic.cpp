#include "audio_mic.h"
#include "config.h"

#define I2S_MIC_PORT I2S_NUM_0

AudioMic::AudioMic() {}

bool AudioMic::begin() {
    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate = SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT, // INMP441 works best with 32-bit slot
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 4,
        .dma_buf_len = 1024,
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

void AudioMic::generateWavHeader(uint8_t* header, size_t wavDataSize, uint32_t sampleRate, uint16_t numChannels, uint16_t bitsPerSample) {
    uint32_t totalFileSize = wavDataSize + 44 - 8;
    uint32_t byteRate = sampleRate * numChannels * (bitsPerSample / 8);
    uint16_t blockAlign = numChannels * (bitsPerSample / 8);

    memcpy(header, "RIFF", 4);
    header[4] = (uint8_t)(totalFileSize & 0xFF);
    header[5] = (uint8_t)((totalFileSize >> 8) & 0xFF);
    header[6] = (uint8_t)((totalFileSize >> 16) & 0xFF);
    header[7] = (uint8_t)((totalFileSize >> 24) & 0xFF);
    memcpy(header + 8, "WAVEfmt ", 8);
    header[16] = 16; header[17] = 0; header[18] = 0; header[19] = 0; // Subchunk1Size (16 for PCM)
    header[20] = 1; header[21] = 0; // AudioFormat (1 for PCM)
    header[22] = (uint8_t)(numChannels & 0xFF);
    header[23] = (uint8_t)((numChannels >> 8) & 0xFF);
    header[24] = (uint8_t)(sampleRate & 0xFF);
    header[25] = (uint8_t)((sampleRate >> 8) & 0xFF);
    header[26] = (uint8_t)((sampleRate >> 16) & 0xFF);
    header[27] = (uint8_t)((sampleRate >> 24) & 0xFF);
    header[28] = (uint8_t)(byteRate & 0xFF);
    header[29] = (uint8_t)((byteRate >> 8) & 0xFF);
    header[30] = (uint8_t)((byteRate >> 16) & 0xFF);
    header[31] = (uint8_t)((byteRate >> 24) & 0xFF);
    header[32] = (uint8_t)(blockAlign & 0xFF);
    header[33] = (uint8_t)((blockAlign >> 8) & 0xFF);
    header[34] = (uint8_t)(bitsPerSample & 0xFF);
    header[35] = (uint8_t)((bitsPerSample >> 8) & 0xFF);
    memcpy(header + 36, "data", 4);
    header[40] = (uint8_t)(wavDataSize & 0xFF);
    header[41] = (uint8_t)((wavDataSize >> 8) & 0xFF);
    header[42] = (uint8_t)((wavDataSize >> 16) & 0xFF);
    header[43] = (uint8_t)((wavDataSize >> 24) & 0xFF);
}

uint8_t* AudioMic::recordWav(int seconds, size_t& wavSize) {
    size_t sampleCount = SAMPLE_RATE * seconds;
    size_t pcmBytes = sampleCount * sizeof(int16_t);
    wavSize = 44 + pcmBytes;

    if (ESP.getFreeHeap() < (wavSize + 50000)) {
        Serial.printf("[MIC] Heap constrained (%d free). Skipping local buffer allocation.\n", ESP.getFreeHeap());
        wavSize = 0;
        return nullptr;
    }

    if (audioBuffer) free(audioBuffer);
    audioBuffer = (uint8_t*)malloc(wavSize);
    if (!audioBuffer) return nullptr;

    generateWavHeader(audioBuffer, pcmBytes, SAMPLE_RATE, 1, 16);

    int16_t* pcmSamples = (int16_t*)(audioBuffer + 44);
    size_t samplesRemaining = sampleCount;
    size_t samplesWritten = 0;
    const size_t CHUNK_SIZE = 256;
    int32_t rawChunk[CHUNK_SIZE];

    unsigned long startTime = millis();
    unsigned long maxDuration = (seconds * 1000) + 1500; // Hard timeout watchdog

    while (samplesRemaining > 0 && (millis() - startTime < maxDuration)) {
        size_t toRead = (samplesRemaining < CHUNK_SIZE) ? samplesRemaining : CHUNK_SIZE;
        size_t bytesRead = 0;
        esp_err_t res = i2s_read(I2S_MIC_PORT, rawChunk, toRead * sizeof(int32_t), &bytesRead, pdMS_TO_TICKS(100));
        
        if (res != ESP_OK || bytesRead == 0) {
            delay(5);
            continue;
        }

        size_t count = bytesRead / sizeof(int32_t);
        for (size_t i = 0; i < count; i++) {
            pcmSamples[samplesWritten++] = (int16_t)(rawChunk[i] >> 14);
        }
        samplesRemaining -= count;
    }

    Serial.printf("[MIC] Finished recording. Samples captured: %d\n", samplesWritten);
    return audioBuffer;
}

AudioMic mic;
