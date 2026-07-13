/**
 * @file orbital_sentinel.ino
 * @brief ORCA Orbital Sentinel for the Seeed Round Display (XIAO ESP32-S3).
 * @details
 *     The Arduino-specific glue, and nothing else. Everything with any logic in it
 *     - SGP4, the camera, the renderer - lives in platform-free files that the host
 *     preview harness compiles too, so what you see in tools/preview is what the
 *     panel draws.
 *
 *     Boot sequence:
 *       1. Bring up the panel and the off-screen framebuffer.
 *       2. Join Wi-Fi and sync UTC over SNTP (both optional; see below).
 *       3. Resolve element sets: fresh NVS cache -> live CelesTrak -> baked-in.
 *       4. Loop: advance simulated time, propagate, render, push the frame.
 *
 *     With no Wi-Fi it still runs: it falls back to the baked-in element sets and
 *     the on-board RTC, exactly as the desktop degrades to its cache/fallback chain.
 *
 *     Board: Seeed XIAO ESP32-S3. Panel: Seeed Round Display (GC9A01, 240x240).
 */

#include <Arduino.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <sys/time.h>
#include <time.h>

#include "config.h"
#include "render.h"
#include "sgp4.h"
#include "tle_fallback.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#warning "No secrets.h - copy secrets.h.example to secrets.h. Running offline."
#define WIFI_SSID ""
#define WIFI_PASS ""
#endif

// The Round Display's PCF8563 RTC keeps UTC across a power cycle, so the globe is
// roughly right even with no network at boot. It needs the "I2C BM8563 RTC"
// library; leave this at 0 for a dependency-free build that relies on SNTP alone.
#ifndef USE_RTC
#define USE_RTC 0
#endif
#if USE_RTC
#include <I2C_BM8563.h>
static I2C_BM8563 rtc(I2C_BM8563_DEFAULT_ADDRESS, &Wire);
#endif

// --- Globals ----------------------------------------------------------------
static TFT_eSPI tft;
static uint16_t *g_fb = nullptr;   //!< 240x240 RGB565 off-screen framebuffer.
static Canvas g_canvas;

/// One tracked object: its propagator, marker colour, and label.
struct Tracked {
  int norad;
  const char *label;
  uint16_t color;
  Satrec sat;
  bool ready;
};

static Tracked g_tracked[MAX_OBJECTS] = {
  {ISS_NORAD_ID, "ISS", COL_ISS, {}, false},
  {CSS_NORAD_ID, "CSS", COL_CSS, {}, false},
};
static const int G_TRACKED_N = 2;

static Preferences g_prefs;

/// Simulated UTC as a Unix epoch (double: it advances by fractional seconds).
/// Drives the ORBITS only. The clock on screen is real wall time - see loop().
static double g_simEpoch = 0.0;
static float g_azimuth = 0.0f;
static uint32_t g_lastMs = 0;

// --- Time -------------------------------------------------------------------

/// Julian date from a Unix epoch (seconds since 1970-01-01 UTC).
static double julianFromEpoch(double epochSec) {
  return epochSec / 86400.0 + 2440587.5;
}

/// True once the clock looks like a real date rather than 1970.
static bool clockIsSet() {
  return time(nullptr) > 1700000000;   // ~2023-11.
}

/// Uppercase month abbreviations: the 5x7 font only carries A-Z and 0-9.
static const char *MONTHS[12] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                 "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};

// --- Element sets -----------------------------------------------------------

/**
 * @brief Find a NORAD id in TLE text and initialise its propagator.
 * @param text  Raw TLE text (name/line1/line2 triples, or bare line1/line2 pairs).
 * @param norad NORAD catalog id to look for.
 * @param out   Propagator to initialise.
 * @return true if found and successfully initialised.
 */
static bool findTle(const char *text, int norad, Satrec &out) {
  char want[8];
  snprintf(want, sizeof(want), "%5d", norad);

  const char *p = text;
  while (p != nullptr && *p != '\0') {
    // A TLE line 1 starts "1 " followed by the 5-digit catalog number.
    if (p[0] == '1' && p[1] == ' ' && strncmp(p + 2, want, 5) == 0) {
      const char *nl = strchr(p, '\n');
      if (nl == nullptr) {
        return false;
      }
      const char *l2 = nl + 1;
      char line1[80];
      char line2[80];
      size_t len1 = (size_t)(nl - p);
      if (len1 >= sizeof(line1)) {
        return false;
      }
      memcpy(line1, p, len1);
      line1[len1] = '\0';

      const char *nl2 = strchr(l2, '\n');
      size_t len2 = (nl2 != nullptr) ? (size_t)(nl2 - l2) : strlen(l2);
      if (len2 >= sizeof(line2)) {
        return false;
      }
      memcpy(line2, l2, len2);
      line2[len2] = '\0';

      return twoline2rv(line1, line2, out);
    }
    p = strchr(p, '\n');
    if (p != nullptr) {
      p++;
    }
  }
  return false;
}

/// Initialise every tracked object from one blob of TLE text. Returns how many hit.
static int applyTleText(const char *text) {
  int ok = 0;
  for (int i = 0; i < G_TRACKED_N; i++) {
    if (findTle(text, g_tracked[i].norad, g_tracked[i].sat)) {
      g_tracked[i].ready = true;
      ok++;
    }
  }
  return ok;
}

/**
 * @brief Reduce a CelesTrak download to just the lines we track.
 * @details NVS values are capped at a few KB and the "stations" group will only
 *          grow, so we cache the two element sets we actually use (~280 bytes)
 *          rather than the whole download.
 */
static String compactTles(const String &raw) {
  String out;
  int start = 0;
  while (start < (int)raw.length()) {
    int nl = raw.indexOf('\n', start);
    if (nl < 0) {
      nl = raw.length();
    }
    String line = raw.substring(start, nl);
    line.trim();
    if (line.startsWith("1 ") || line.startsWith("2 ")) {
      int id = line.substring(2, 7).toInt();
      for (int i = 0; i < G_TRACKED_N; i++) {
        if (id == g_tracked[i].norad) {
          out += line;
          out += "\n";
          break;
        }
      }
    }
    start = nl + 1;
  }
  return out;
}

/// Download the stations group from CelesTrak. Empty string on any failure.
static String fetchTles() {
  if (WiFi.status() != WL_CONNECTED) {
    return String();
  }
  WiFiClientSecure client;
  // CelesTrak is a public, read-only data source and we ship no CA bundle, so we
  // do not pin a certificate. The worst case for a spoofed response is a wrong
  // dot on a toy globe.
  client.setInsecure();

  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(client, CELESTRAK_URL)) {
    return String();
  }
  int code = http.GET();
  String body;
  if (code == HTTP_CODE_OK) {
    body = http.getString();
  } else {
    Serial.printf("[tle] HTTP %d\n", code);
  }
  http.end();

  // CelesTrak answers a bad query with a short error string, not TLEs.
  if (body.indexOf("1 ") < 0) {
    return String();
  }
  return body;
}

/**
 * @brief Resolve element sets: fresh NVS cache -> live fetch -> stale cache -> baked.
 * @return A short label describing where the data came from (for the serial log).
 */
static const char *loadTles() {
  g_prefs.begin("orca", false);
  uint32_t cachedAt = g_prefs.getUInt("tle_at", 0);
  String cached = g_prefs.getString("tle", "");
  uint32_t nowSec = clockIsSet() ? (uint32_t)time(nullptr) : 0;

  bool fresh = cached.length() > 0 && cachedAt > 0 && nowSec > cachedAt
            && (nowSec - cachedAt) < TLE_REFRESH_S;

  if (fresh && applyTleText(cached.c_str()) == G_TRACKED_N) {
    g_prefs.end();
    return "nvs-cache";
  }

  String live = fetchTles();
  if (live.length() > 0) {
    String compact = compactTles(live);
    if (compact.length() > 0 && applyTleText(compact.c_str()) == G_TRACKED_N) {
      g_prefs.putString("tle", compact);
      g_prefs.putUInt("tle_at", nowSec);
      g_prefs.end();
      return "celestrak";
    }
  }

  // A stale cache still beats a months-old baked-in element set.
  if (cached.length() > 0 && applyTleText(cached.c_str()) == G_TRACKED_N) {
    g_prefs.end();
    return "nvs-cache(stale)";
  }

  g_prefs.end();
  applyTleText(FALLBACK_TLE);
  return "baked-in-fallback";
}

// --- Network ----------------------------------------------------------------

static void connectWifi() {
  if (strlen(WIFI_SSID) == 0) {
    Serial.println("[wifi] no SSID configured; running offline");
    return;
  }
  Serial.printf("[wifi] joining %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  // Bounded wait: a missing network must not stop the globe from drawing.
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[wifi] ok, ip %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("[wifi] failed; running offline");
  }
}

/**
 * @brief Establish UTC from SNTP, falling back to the on-board RTC.
 * @details Must run *before* loadTles(): cache freshness is a wall-clock
 *          comparison, so with no clock every boot would look stale and refetch
 *          from CelesTrak - exactly the polling behaviour they firewall.
 */
static void syncTime() {
  if (WiFi.status() == WL_CONNECTED) {
    configTime(0, 0, SNTP_SERVER_1, SNTP_SERVER_2);   // 0,0 => UTC, no DST.
    for (int i = 0; i < 40 && !clockIsSet(); i++) {
      delay(250);
    }
  }

#if USE_RTC
  Wire.begin();
  rtc.begin();
  if (clockIsSet()) {
    // Network time won: push it into the RTC for the next cold boot.
    time_t now = time(nullptr);
    struct tm t;
    gmtime_r(&now, &t);
    I2C_BM8563_DateTypeDef rtcDate = {(uint16_t)(t.tm_year + 1900),
                                      (uint8_t)(t.tm_mon + 1),
                                      (uint8_t)t.tm_mday};
    I2C_BM8563_TimeTypeDef rtcTime = {(uint8_t)t.tm_hour, (uint8_t)t.tm_min,
                                      (uint8_t)t.tm_sec};
    rtc.setDate(&rtcDate);
    rtc.setTime(&rtcTime);
    Serial.println("[time] SNTP ok; RTC updated");
  } else {
    // No network: trust the RTC.
    I2C_BM8563_DateTypeDef rtcDate;
    I2C_BM8563_TimeTypeDef rtcTime;
    rtc.getDate(&rtcDate);
    rtc.getTime(&rtcTime);
    struct tm t = {};
    t.tm_year = rtcDate.year - 1900;
    t.tm_mon = rtcDate.month - 1;
    t.tm_mday = rtcDate.date;
    t.tm_hour = rtcTime.hours;
    t.tm_min = rtcTime.minutes;
    t.tm_sec = rtcTime.seconds;
    time_t epoch = mktime(&t);           // TZ is UTC here, so mktime is a UTC epoch.
    struct timeval tv = {epoch, 0};
    settimeofday(&tv, nullptr);
    Serial.println("[time] no SNTP; using on-board RTC");
  }
#endif

  if (!clockIsSet()) {
    Serial.println("[time] no SNTP and no RTC; will fall back to the TLE epoch");
  }
}

/**
 * @brief Last-resort clock: start at the element-set epoch.
 * @details Runs after loadTles(). With no network and no RTC there is nothing to
 *          sync from, and propagating from a 1970 clock would put the stations
 *          absurdly far from their element set. Starting *at* the epoch means
 *          SGP4 is at its most accurate, so the globe at least looks right even
 *          though the wall-clock time it shows is not now.
 */
static void fallbackClockFromTle() {
  if (clockIsSet()) {
    return;
  }
  for (int i = 0; i < G_TRACKED_N; i++) {
    if (g_tracked[i].ready) {
      time_t epoch =
          (time_t)((g_tracked[i].sat.jdsatepoch - 2440587.5) * 86400.0);
      struct timeval tv = {epoch, 0};
      settimeofday(&tv, nullptr);
      Serial.println("[time] starting at TLE epoch (clock is not real time)");
      return;
    }
  }
}

// --- Arduino ----------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nORCA Orbital Sentinel - round display build");

  // Local timezone for the on-screen clock. Everything internal - SGP4, SNTP, the
  // RTC - stays in UTC; TZ only affects what localtime_r() hands back for display.
  setenv("TZ", TZ_POSIX, 1);
  tzset();

  tft.init();
  tft.setRotation(0);
  tft.fillScreen(TFT_BLACK);
  tft.setSwapBytes(true);   // Our buffer is native-endian uint16_t RGB565.

  // Backlight. Both pin and active level come from the Seeed_GFX panel setup
  // (D6, active HIGH for combo 501) rather than being hard-coded here.
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);

  // 240*240*2 = 115200 bytes. Prefer PSRAM when the board has it, so the Wi-Fi
  // stack keeps its internal SRAM.
  size_t bytes = (size_t)PANEL_W * PANEL_H * sizeof(uint16_t);
#if defined(BOARD_HAS_PSRAM)
  g_fb = (uint16_t *)ps_malloc(bytes);
#endif
  if (g_fb == nullptr) {
    g_fb = (uint16_t *)malloc(bytes);
  }
  if (g_fb == nullptr) {
    Serial.println("[fb] out of memory - cannot allocate framebuffer");
    tft.setTextColor(TFT_RED);
    tft.drawString("NO MEM", 80, 110, 4);
    while (true) {
      delay(1000);
    }
  }
  g_canvas.px = g_fb;
  g_canvas.w = PANEL_W;
  g_canvas.h = PANEL_H;

  sceneInit();          // Lift the coastline onto the sphere, seed the stars.
  connectWifi();

  // Order matters: the clock must be running before loadTles(), because cache
  // freshness is a wall-clock comparison. Only if nothing set the clock do we fall
  // back to the element-set epoch, which needs the TLEs to already be parsed.
  syncTime();
  const char *src = loadTles();
  fallbackClockFromTle();

  int ready = 0;
  for (int i = 0; i < G_TRACKED_N; i++) {
    if (g_tracked[i].ready) {
      ready++;
    }
  }
  Serial.printf("[tle] source=%s tracked=%d/%d\n", src, ready, G_TRACKED_N);

  g_simEpoch = (double)time(nullptr);
  g_lastMs = millis();
}

void loop() {
  uint32_t now = millis();
  float dt = (float)(now - g_lastMs) / 1000.0f;
  g_lastMs = now;

  // Advance simulated time and spin the camera. The spin is cosmetic and never feeds
  // back into the physics - positions come only from g_simEpoch.
  g_simEpoch += (double)dt * TIME_ACCELERATION;
  g_azimuth = fmodf(g_azimuth + SPIN_DEG_PER_SEC * dt, 360.0f);

  // Orbits run on SIMULATED time; the clock shows REAL time. At the default
  // TIME_ACCELERATION of 1.0 these are the same thing, which is the point: the globe
  // agrees with the clock. Raise the acceleration and the globe runs ahead - but the
  // clock keeps telling the truth, because a clock that lies is useless.
  double jd = julianFromEpoch(g_simEpoch);

  Station stations[MAX_OBJECTS];
  int n = 0;
  for (int i = 0; i < G_TRACKED_N; i++) {
    Station &s = stations[n];
    s.color = g_tracked[i].color;
    s.label = g_tracked[i].label;
    s.valid = g_tracked[i].ready
           && propagateEcef(g_tracked[i].sat, jd, s.ecef);
    n++;
  }

  // Real wall time, converted to the local zone by TZ_POSIX (set in setup()).
  time_t wall = time(nullptr);
  struct tm lt;
  localtime_r(&wall, &lt);

  char timeStr[16];
  char dateStr[20];
  snprintf(timeStr, sizeof(timeStr), "%02d:%02d:%02d",
           lt.tm_hour, lt.tm_min, lt.tm_sec);
  snprintf(dateStr, sizeof(dateStr), "%02d %s %04d",
           lt.tm_mday, MONTHS[lt.tm_mon % 12], lt.tm_year + 1900);

  Scene scene;
  scene.stations = stations;
  scene.nStations = n;
  scene.azimuthDeg = g_azimuth;
  // One ping per HOME_PING_PERIOD_S, phase 0..1. millis() wrapping after ~49 days
  // just restarts the animation mid-cycle; nothing else depends on it.
  scene.homePulse =
      fmodf((float)now / (1000.0f * HOME_PING_PERIOD_S), 1.0f);
  scene.timeStr = timeStr;
  scene.dateStr = dateStr;

  renderFrame(g_canvas, scene);
  tft.pushImage(0, 0, PANEL_W, PANEL_H, g_fb);

  // Frame cap. Rendering ~2.7k coastline dots plus two SGP4 solves leaves plenty of
  // headroom at 30 fps; the SPI push is the real floor. Seeed_GFX clocks the XIAO
  // ESP32-S3 panel at 50 MHz, so a full 115 KB frame costs ~18 ms (~54 fps ceiling).
  uint32_t spent = millis() - now;
  uint32_t budget = 1000 / TARGET_FPS;
  if (spent < budget) {
    delay(budget - spent);
  }
}
