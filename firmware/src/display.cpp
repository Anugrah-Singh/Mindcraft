#include "display.h"
#include "config.h"
#include <math.h>

// Layout grid (128x64): header bar 0-10, body rows from y=12 (4 rows x 10 px), footer rule at y=54.
#define HDR_H        11
#define BODY_TOP     12
#define ROW_H        10
#define BODY_ROWS    4
#define FOOTER_LINE  54
#define SCROLL_X     125

// ---------------------------------------------------------------- bitmaps (MSB-first rows)
static const uint16_t ICON_TASKS[10] = {0x3FF, 0x201, 0x209, 0x219, 0x2B1, 0x2F1, 0x261, 0x221, 0x201, 0x3FF};
static const uint16_t ICON_HABIT[10] = {0x040, 0x060, 0x070, 0x0F2, 0x0FB, 0x1FB, 0x1FF, 0x1FF, 0x0FE, 0x07C};
static const uint16_t ICON_NOTE[10]  = {0x1FE, 0x102, 0x17A, 0x102, 0x17A, 0x102, 0x172, 0x102, 0x102, 0x1FE};
static const uint16_t ICON_MIC[10]   = {0x078, 0x0FC, 0x0FC, 0x2FD, 0x2FD, 0x279, 0x102, 0x0FC, 0x030, 0x078};
static const uint16_t ICON_SPEAKER[10] = {0x008, 0x018, 0x0F8, 0x3F8, 0x3F8, 0x3F8, 0x3F8, 0x0F8, 0x018, 0x008};
static const uint16_t FLAME_5X7[7]   = {0x04, 0x0C, 0x0E, 0x1F, 0x1F, 0x1F, 0x0E};

static const uint16_t* iconFor(const char* name) {
    if (!strcmp(name, "tasks")) return ICON_TASKS;
    if (!strcmp(name, "habit")) return ICON_HABIT;
    if (!strcmp(name, "note"))  return ICON_NOTE;
    return ICON_MIC;
}

MindcraftDisplay::MindcraftDisplay()
    : u8g2(U8G2_R0, OLED_RESET_PIN, OLED_SCL_PIN, OLED_SDA_PIN) {}

void MindcraftDisplay::begin() {
    u8g2.begin();
    u8g2.setBusClock(400000);      // a full-frame update takes ~23 ms instead of ~90 ms
    u8g2.enableUTF8Print();
    showWaiting();
}

// ---------------------------------------------------------------- helpers
static void clippedText(U8G2& u8g2, int x, int y, const char* text, int maxW) {
    char buf[64];
    strncpy(buf, text, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = 0;
    size_t n = strlen(buf);
    if (u8g2.getStrWidth(buf) > maxW) {
        // does not fit: cut and end with ".." so truncation is visible
        while (n > 0 && u8g2.getStrWidth(buf) + u8g2.getStrWidth("..") > maxW) buf[--n] = 0;
        while (n > 0 && buf[n - 1] == ' ') buf[--n] = 0;
        strncat(buf, "..", sizeof(buf) - strlen(buf) - 1);
    }
    u8g2.drawStr(x, y, buf);
}

void MindcraftDisplay::drawBits(int x, int y, const uint16_t* rows, int w, int h, int scale) {
    for (int r = 0; r < h; r++) {
        for (int c = 0; c < w; c++) {
            if ((rows[r] >> (w - 1 - c)) & 1) {
                if (scale == 1) u8g2.drawPixel(x + c, y + r);
                else u8g2.drawBox(x + c * scale, y + r * scale, scale, scale);
            }
        }
    }
}

void MindcraftDisplay::drawFlame(int x, int y) {
    drawBits(x, y, FLAME_5X7, 5, 7);
}

void MindcraftDisplay::drawHeader(const char* title, const char* counter) {
    u8g2.setDrawColor(1);
    u8g2.drawBox(0, 0, 128, HDR_H);
    u8g2.setDrawColor(0);
    u8g2.setFont(u8g2_font_6x10_tf);
    u8g2.drawStr(3, 9, title);

    // Bluetooth rune: shown struck through while the speaker is not connected.
    const int bx = 119, by = 1;
    u8g2.drawLine(bx + 2, by, bx + 2, by + 8);
    u8g2.drawLine(bx + 2, by, bx + 4, by + 2);
    u8g2.drawLine(bx + 4, by + 2, bx, by + 6);
    u8g2.drawLine(bx, by + 2, bx + 4, by + 6);
    u8g2.drawLine(bx + 4, by + 6, bx + 2, by + 8);
    if (!btUp) u8g2.drawLine(bx - 1, by + 9, bx + 5, by - 1);

    if (counter && counter[0]) {
        u8g2.setFont(u8g2_font_4x6_tr);
        u8g2.drawStr(113 - u8g2.getStrWidth(counter), 8, counter);
    }
    u8g2.setDrawColor(1);
}

void MindcraftDisplay::drawFooter(const char* left, const char* right) {
    if ((!left || !left[0]) && (!right || !right[0])) return;   // nothing to show: no rule either
    u8g2.setDrawColor(1);
    u8g2.drawHLine(0, FOOTER_LINE, 128);
    u8g2.setFont(u8g2_font_4x6_tr);
    if (left && left[0]) u8g2.drawStr(2, 62, left);
    if (right && right[0]) u8g2.drawStr(126 - u8g2.getStrWidth(right), 62, right);
}

// pos in [0, posMax] moves the thumb along the track.
void MindcraftDisplay::drawScrollbar(int pos, int posMax, int total, int visible) {
    if (total <= visible) return;
    const int top = BODY_TOP, h = BODY_ROWS * ROW_H;
    for (int y = top; y < top + h; y += 2) u8g2.drawPixel(SCROLL_X + 1, y);   // dotted track
    int th = h * visible / total;
    if (th < 4) th = 4;
    int ty = top + (posMax > 0 ? (h - th) * pos / posMax : 0);
    u8g2.drawBox(SCROLL_X, ty, 3, th);
}

// ---------------------------------------------------------------- views
void MindcraftDisplay::drawMenu(JsonObjectConst s) {
    drawHeader("MINDCRAFT", "");
    int sel = s["sel"] | 0, i = 0;
    for (JsonObjectConst it : s["items"].as<JsonArrayConst>()) {
        if (i >= 4) break;
        const int x0 = 1 + (i % 2) * 63, y0 = 13 + (i / 2) * 20, w = 62, h = 19;
        const bool on = (i == sel);
        u8g2.setDrawColor(1);
        if (on) {
            u8g2.drawRBox(x0, y0, w, h, 3);
            u8g2.setDrawColor(0);
        } else {
            u8g2.drawRFrame(x0, y0, w, h, 3);
        }
        drawBits(x0 + 5, y0 + 4, iconFor(it["icon"] | ""), 10, 10);
        u8g2.setFont(u8g2_font_5x8_tr);
        clippedText(u8g2, x0 + 19, y0 + 9, it["label"] | "", 40);
        u8g2.setFont(u8g2_font_4x6_tr);
        clippedText(u8g2, x0 + 19, y0 + 17, it["sub"] | "", 40);
        u8g2.setDrawColor(1);
        i++;
    }
    drawFooter(s["footer_left"] | "", s["footer_right"] | "");
}

void MindcraftDisplay::drawList(JsonObjectConst s) {
    const char* view = s["view"] | "";
    const int total = s["total"] | 0, sel = s["sel"] | 0, pos = s["pos"] | 0;
    char counter[12] = "";
    if (total > 0) snprintf(counter, sizeof(counter), "%d/%d", pos + 1, total);
    drawHeader(s["title"] | "", counter);

    if (total == 0) {
        u8g2.setFont(u8g2_font_5x8_tr);
        const char* msg = s["empty"] | "Nothing here";
        u8g2.drawStr((128 - u8g2.getStrWidth(msg)) / 2, 34, msg);
    }

    const int rowW = total > BODY_ROWS ? 121 : 123;
    int i = 0;
    for (JsonObjectConst it : s["items"].as<JsonArrayConst>()) {
        if (i >= BODY_ROWS) break;
        const int T = BODY_TOP + i * ROW_H;
        const bool on = (i == sel);
        u8g2.setDrawColor(1);
        if (on) {
            u8g2.drawRBox(0, T, rowW, ROW_H, 1);
            u8g2.setDrawColor(0);       // content is drawn in the inverse colour
        }
        const int fg = on ? 0 : 1, bg = on ? 1 : 0;
        u8g2.setFont(u8g2_font_5x8_tr);

        if (!strcmp(view, "tasks")) {
            u8g2.drawFrame(3, T + 1, 7, 7);
            clippedText(u8g2, 13, T + 7, it["text"] | "", rowW - 13 - 9);
            const char* pri = it["pri"] | "M";
            u8g2.setFont(u8g2_font_4x6_tr);
            u8g2.drawStr(rowW - 7, T + 7, pri);
        } else if (!strcmp(view, "habits")) {
            const bool done = it["done"] | false;
            const int streak = it["streak"] | 0;
            if (done) {
                u8g2.drawBox(3, T + 1, 7, 7);
                u8g2.setDrawColor(bg);   // tick in the opposite colour
                u8g2.drawLine(4, T + 4, 5, T + 6);
                u8g2.drawLine(5, T + 6, 8, T + 2);
                u8g2.setDrawColor(fg);
            } else {
                u8g2.drawFrame(3, T + 1, 7, 7);
            }
            char sbuf[8];
            snprintf(sbuf, sizeof(sbuf), "%dd", streak);
            const int sw = u8g2.getStrWidth(sbuf);
            u8g2.drawStr(rowW - 3 - sw, T + 7, sbuf);
            int nameMax = rowW - 3 - sw - 13 - 3;
            if (streak > 0) {
                drawFlame(rowW - 3 - sw - 7, T + 1);
                nameMax -= 7;
            }
            clippedText(u8g2, 13, T + 7, it["name"] | "", nameMax);
        } else {   // notes
            u8g2.drawFrame(3, T + 1, 6, 8);
            u8g2.drawHLine(5, T + 4, 2);
            u8g2.drawHLine(5, T + 6, 2);
            clippedText(u8g2, 13, T + 7, it["text"] | "", rowW - 13 - (on ? 12 : 3));
            if (on) u8g2.drawTriangle(rowW - 9, T + 1, rowW - 9, T + 8, rowW - 4, T + 4);   // play
        }
        u8g2.setDrawColor(1);
        i++;
    }
    drawScrollbar(pos, total - 1, total, BODY_ROWS);
    drawFooter(s["footer_left"] | "", s["footer_right"] | "");
}

void MindcraftDisplay::drawAi(JsonObjectConst s) {
    drawHeader(s["title"] | "ANSWER", "");
    const char* kind = s["kind"] | "";
    const int total = s["total"] | 0, pos = s["pos"] | 0;
    const bool more = s["more"] | false;

    u8g2.setFont(u8g2_font_helvB08_tr);
    clippedText(u8g2, 3, 23, s["head"] | "", 104);
    if (!strcmp(kind, "TASK") || !strcmp(kind, "TASK_DONE")) drawBits(113, 14, ICON_TASKS, 10, 10);
    else if (!strcmp(kind, "HABIT")) drawBits(113, 14, ICON_HABIT, 10, 10);
    else if (!strcmp(kind, "NOTE")) drawBits(113, 14, ICON_NOTE, 10, 10);
    else if (!strcmp(kind, "CONVERSATION")) drawBits(113, 14, ICON_MIC, 10, 10);

    u8g2.setFont(u8g2_font_5x8_tr);
    int y = 33;
    for (JsonVariantConst line : s["body"].as<JsonArrayConst>()) {
        clippedText(u8g2, 3, y, line.as<const char*>(), 119);
        y += 9;
    }
    // The scrollbar only needs to show when there is more than one page of text.
    if (more || pos > 0) {
        const int visible = 3, posMax = total - visible;
        const int top = 24, h = 27;
        for (int yy = top; yy < top + h; yy += 2) u8g2.drawPixel(SCROLL_X + 1, yy);
        int th = h * visible / (total > 0 ? total : 1);
        if (th < 4) th = 4;
        u8g2.drawBox(SCROLL_X, top + (posMax > 0 ? (h - th) * pos / posMax : 0), 3, th);
    }
    drawFooter(s["footer_left"] | "", s["footer_right"] | "");
}

// Level 0..~30000 (mean absolute amplitude) mapped to 0..16 lit segments on a log scale.
static int segmentsFor(uint16_t level) {
    float v = (log10f((float)level + 10.0f) - 1.5f) / 2.7f;
    if (v < 0) v = 0;
    if (v > 1) v = 1;
    return (int)(v * 16.0f + 0.5f);
}

static uint16_t recLevel = 0;
static bool recSpeaking = false;
static uint32_t recElapsed = 0;

void MindcraftDisplay::drawRecordingBody(uint16_t level, bool speaking, uint32_t elapsedMs, bool full) {
    // Left: microphone, filled while speech is detected.
    u8g2.setDrawColor(speaking ? 1 : 0);
    u8g2.drawRBox(6, 18, 28, 28, 3);
    u8g2.setDrawColor(speaking ? 0 : 1);
    if (!speaking) u8g2.drawRFrame(6, 18, 28, 28, 3);
    drawBits(10, 22, ICON_MIC, 10, 10, 2);
    u8g2.setDrawColor(1);

    // Right panel: clear, then headline, status and the level meter.
    u8g2.setDrawColor(0);
    u8g2.drawBox(40, BODY_TOP, 88, FOOTER_LINE - BODY_TOP);
    u8g2.setDrawColor(1);
    u8g2.setFont(u8g2_font_helvB08_tr);
    u8g2.drawStr(44, 29, speaking ? "Recording" : "Listening");
    u8g2.setFont(u8g2_font_5x8_tr);
    if (speaking) {
        char t[12];
        snprintf(t, sizeof(t), "%u.%us", (unsigned)(elapsedMs / 1000), (unsigned)((elapsedMs / 100) % 10));
        u8g2.drawStr(44, 40, t);
    } else {
        u8g2.drawStr(44, 40, "Speak now");
    }
    const int lit = segmentsFor(level);
    for (int i = 0; i < 16; i++) {
        const int x = 44 + i * 5;
        if (i < lit) u8g2.drawBox(x, 44, 4, 7);
        else u8g2.drawPixel(x + 1, 49);
    }
    (void)full;
}

void MindcraftDisplay::drawStatus(JsonObjectConst s) {
    const char* anim = s["anim"] | "";
    drawHeader(s["title"] | "", "");
    const bool listening = !strcmp(anim, "listening");

    if (listening) {
        drawRecordingBody(recording ? recLevel : (uint16_t)(300 + 2500 * (1 + sinf(animFrame * 0.7f)) / 2),
                          recording && recSpeaking, recElapsed, true);
        drawFooter(s["footer_left"] | "", s["footer_right"] | "");
        return;
    }

    // Left graphic area (x 6..38)
    if (!strcmp(anim, "thinking")) {
        for (int i = 0; i < 3; i++) {
            const int phase = (animFrame + i * 2) % 8;
            const int lift = phase < 4 ? phase : 8 - phase;      // 0..4 px bounce
            u8g2.drawDisc(12 + i * 10, 36 - lift * 2, 2);
        }
    } else if (!strcmp(anim, "playing") || !strcmp(anim, "preparing")) {
        drawBits(8, 24, ICON_SPEAKER, 10, 10, 2);
        const int arcs = (!strcmp(anim, "playing")) ? 1 + (animFrame % 3) : 1;
        for (int a = 0; a < arcs; a++) {
            u8g2.drawCircle(30, 34, 4 + a * 3, U8G2_DRAW_UPPER_RIGHT | U8G2_DRAW_LOWER_RIGHT);
        }
    } else {   // error
        u8g2.drawRFrame(8, 22, 26, 26, 4);
        u8g2.setFont(u8g2_font_helvB14_tr);
        u8g2.drawStr(18, 43, "!");
    }

    // Right: headline + up to two wrapped lines
    u8g2.setFont(u8g2_font_helvB08_tr);
    clippedText(u8g2, 44, 28, s["head"] | "", 82);
    u8g2.setFont(u8g2_font_5x8_tr);
    char sub[40];
    strncpy(sub, s["sub"] | "", sizeof(sub) - 1);
    sub[sizeof(sub) - 1] = 0;
    int len = strlen(sub);
    if (len <= 16) {
        u8g2.drawStr(44, 40, sub);
    } else {
        int cut = 16;
        while (cut > 6 && sub[cut] != ' ') cut--;
        if (sub[cut] != ' ') cut = 16;
        char first[20];
        strncpy(first, sub, cut);
        first[cut] = 0;
        u8g2.drawStr(44, 40, first);
        clippedText(u8g2, 44, 49, sub + cut + (sub[cut] == ' ' ? 1 : 0), 82);
    }
    drawFooter(s["footer_left"] | "", s["footer_right"] | "");
}

void MindcraftDisplay::drawLegacy(JsonObjectConst s) {
    drawHeader(s["title"] | "MINDCRAFT", "");
    u8g2.setFont(u8g2_font_5x8_tr);
    int i = 0;
    for (JsonVariantConst v : s["lines"].as<JsonArrayConst>()) {
        if (i >= BODY_ROWS) break;
        const int T = BODY_TOP + i * ROW_H;
        String line = v.as<String>();
        const bool on = line.startsWith(">") || line.startsWith("*");
        if (on) line = line.substring(line.startsWith("> ") || line.startsWith("* ") ? 2 : 1);
        u8g2.setDrawColor(1);
        if (on) {
            u8g2.drawRBox(0, T, 123, ROW_H, 1);
            u8g2.setDrawColor(0);
        }
        clippedText(u8g2, 4, T + 7, line.c_str(), 118);
        u8g2.setDrawColor(1);
        i++;
    }
    drawFooter(s["footer_left"] | "", s["footer_right"] | "");
}

void MindcraftDisplay::drawWaiting() {
    u8g2.setDrawColor(1);
    u8g2.setFont(u8g2_font_helvB14_tr);
    const char* name = "MINDCRAFT";
    u8g2.drawStr((128 - u8g2.getStrWidth(name)) / 2, 22, name);
    u8g2.setFont(u8g2_font_4x6_tr);
    const char* tag = "VOICE NOTEBOOK";
    u8g2.drawStr((128 - u8g2.getStrWidth(tag)) / 2, 31, tag);
    u8g2.drawHLine(20, 35, 88);

    u8g2.setFont(u8g2_font_5x8_tr);
    u8g2.drawStr(22, 46, "PC link");
    u8g2.drawStr(22, 57, "Speaker");
    for (int r = 0; r < 2; r++) {
        const bool up = (r == 0) ? hubUp : btUp;
        const int cy = (r == 0) ? 43 : 54;
        if (up) u8g2.drawDisc(104, cy, 3);
        else u8g2.drawCircle(104, cy, 3);
    }
}

// ---------------------------------------------------------------- public API
void MindcraftDisplay::redraw() {
    u8g2.clearBuffer();
    if (!haveScreen) {
        drawWaiting();
    } else {
        JsonObjectConst s = lastDoc.as<JsonObjectConst>();
        const char* view = s["view"] | "";
        if (!strcmp(view, "menu")) drawMenu(s);
        else if (!strcmp(view, "tasks") || !strcmp(view, "habits") || !strcmp(view, "notes")) drawList(s);
        else if (!strcmp(view, "ai")) drawAi(s);
        else if (!strcmp(view, "status")) drawStatus(s);
        else drawLegacy(s);
    }
    u8g2.sendBuffer();
    if (mirror && !recording) {
        if (millis() - lastFrame >= 120) {
            lastFrame = millis();
            dumpFrame();
            framePending = false;
        } else {
            framePending = true;      // sent by tick() once the interval has passed
        }
    }
}

// Raw SSD1306 page buffer (8 pages x 128 columns, bit 0 = top pixel of the page) as one hex line.
void MindcraftDisplay::dumpFrame() {
    static char line[2 + 2048 + 2];
    const uint8_t* buf = u8g2.getBufferPtr();
    static const char* hexd = "0123456789abcdef";
    line[0] = '@';
    line[1] = 'F';
    for (int i = 0; i < 1024; i++) {
        line[2 + i * 2] = hexd[buf[i] >> 4];
        line[3 + i * 2] = hexd[buf[i] & 15];
    }
    line[2 + 2048] = 10;
    Serial.write((const uint8_t*)line, 2 + 2048 + 1);
}

void MindcraftDisplay::showScreen(JsonObjectConst screen) {
    lastDoc.set(screen);
    haveScreen = true;
    hubUp = true;
    recording = false;
    animFrame = 0;
    redraw();
}

void MindcraftDisplay::showWaiting() {
    haveScreen = false;
    redraw();
}

void MindcraftDisplay::showProcessing() {
    JsonDocument doc;
    doc["view"] = "status";
    doc["anim"] = "thinking";
    doc["title"] = "THINKING";
    doc["head"] = "Thinking";
    doc["sub"] = "Sending your voice";
    showScreen(doc.as<JsonObjectConst>());
}

void MindcraftDisplay::beginRecording() {
    JsonDocument doc;
    doc["view"] = "status";
    doc["anim"] = "listening";
    doc["title"] = "ASK AI";
    doc["footer_left"] = "";
    doc["footer_right"] = "";
    lastDoc.set(doc.as<JsonObjectConst>());
    haveScreen = true;
    recLevel = 0;
    recSpeaking = false;
    recElapsed = 0;
    recording = true;
    redraw();
}

// Only the changing area is redrawn and sent (~15 ms), so the I2S microphone buffers never overflow.
void MindcraftDisplay::recordLevel(uint16_t level, bool speaking, uint32_t elapsedMs) {
    recLevel = level;
    recSpeaking = speaking;
    recElapsed = elapsedMs;
    drawRecordingBody(level, speaking, elapsedMs, false);
    u8g2.updateDisplayArea(0, 1, 16, 6);
    // Before speech starts nothing binary is on the wire, so the mirror can follow the meter.
    // Once the recording stream has begun, text frames would corrupt it, so they stop.
    if (mirror && !speaking && millis() - lastFrame >= 200) {
        lastFrame = millis();
        dumpFrame();
    }
}

void MindcraftDisplay::setBtConnected(bool connected) {
    if (connected == btUp) return;
    btUp = connected;
    redraw();
}

void MindcraftDisplay::tick() {
    if (mirror && framePending && !recording && millis() - lastFrame >= 120) {
        lastFrame = millis();
        framePending = false;
        dumpFrame();
    }
    if (!haveScreen || recording) return;
    if (millis() - lastAnim < 140) return;
    JsonObjectConst s = lastDoc.as<JsonObjectConst>();
    if (strcmp(s["view"] | "", "status") != 0) return;
    const char* anim = s["anim"] | "";
    if (!strcmp(anim, "error")) return;
    lastAnim = millis();
    animFrame++;
    redraw();
}

MindcraftDisplay display;
