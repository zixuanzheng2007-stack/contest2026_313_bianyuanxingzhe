/****************************************************************************
 * LVGL snapshot → 1/2 缩放 RGB565 → 串口二进制帧（约 1fps @ 1Mbps）
 *
 * 帧格式：0x89 'E' 'W' 'F' | w u16 LE | h u16 LE | len u32 LE | RGB565
 ****************************************************************************/

#include "ew_mirror.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#ifdef __NuttX__
#include <nuttx/config.h>
#ifdef CONFIG_LV_USE_NUTTX
#include <lvgl/lvgl.h>
/* openvela LVGL 树：snapshot 在 src/draw/lv_snapshot/ */
#if __has_include(<src/draw/lv_snapshot/lv_snapshot.h>)
#include <src/draw/lv_snapshot/lv_snapshot.h>
#elif __has_include(<lvgl/src/draw/lv_snapshot/lv_snapshot.h>)
#include <lvgl/src/draw/lv_snapshot/lv_snapshot.h>
#else
extern lv_draw_buf_t *lv_snapshot_take(lv_obj_t *obj, lv_color_format_t cf);
extern void lv_draw_buf_destroy(lv_draw_buf_t *draw_buf);
#endif
#endif
#endif

#define EW_FB_MAGIC0 0x89u
#define EW_FB_MAGIC1 'E'
#define EW_FB_MAGIC2 'W'
#define EW_FB_MAGIC3 'F'

#define EW_MIRROR_SCALE  2
#define EW_MIRROR_PERIOD_MS 900u

#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)

static int g_mirror_on;
static uint32_t g_last_ms;
static int g_sending;

static uint32_t mirror_now_ms(void)
{
  return lv_tick_get();
}

static void downscale_rgb565(const uint8_t *src, int src_w, int src_h, int src_stride,
                             uint8_t *dst, int dst_w, int dst_h)
{
  int y;
  int x;

  for (y = 0; y < dst_h; y++) {
    const uint8_t *row =
        src + (y * EW_MIRROR_SCALE) * src_stride;
    for (x = 0; x < dst_w; x++) {
      const uint8_t *px = row + (x * EW_MIRROR_SCALE) * 2;
      dst[(y * dst_w + x) * 2] = px[0];
      dst[(y * dst_w + x) * 2 + 1] = px[1];
    }
  }
}

static int mirror_send_rgb565(const uint8_t *data, uint16_t w, uint16_t h)
{
  uint8_t hdr[12];
  uint32_t len;
  ssize_t n;

  if (data == NULL || w == 0 || h == 0) {
    return -1;
  }
  len = (uint32_t)w * (uint32_t)h * 2u;
  hdr[0] = EW_FB_MAGIC0;
  hdr[1] = EW_FB_MAGIC1;
  hdr[2] = EW_FB_MAGIC2;
  hdr[3] = EW_FB_MAGIC3;
  hdr[4] = (uint8_t)(w & 0xffu);
  hdr[5] = (uint8_t)(w >> 8);
  hdr[6] = (uint8_t)(h & 0xffu);
  hdr[7] = (uint8_t)(h >> 8);
  hdr[8] = (uint8_t)(len & 0xffu);
  hdr[9] = (uint8_t)((len >> 8) & 0xffu);
  hdr[10] = (uint8_t)((len >> 16) & 0xffu);
  hdr[11] = (uint8_t)((len >> 24) & 0xffu);

  g_sending = 1;
  n = write(STDOUT_FILENO, hdr, sizeof(hdr));
  if (n != (ssize_t)sizeof(hdr)) {
    g_sending = 0;
    return -1;
  }
  n = write(STDOUT_FILENO, data, len);
  g_sending = 0;
  if (n != (ssize_t)len) {
    return -1;
  }
  return 0;
}

static int mirror_capture_send(void)
{
  lv_draw_buf_t *snap;
  lv_obj_t *scr;
  int src_w;
  int src_h;
  int dst_w;
  int dst_h;
  int src_stride;
  static uint8_t scratch[200 * 230 * 2];
  uint32_t need;

  if (!lv_is_initialized()) {
    return -1;
  }
  scr = lv_screen_active();
  if (scr == NULL) {
    return -1;
  }

  snap = lv_snapshot_take(scr, LV_COLOR_FORMAT_RGB565);
  if (snap == NULL || snap->data == NULL) {
    printf("[ew-mirror] snapshot fail\n");
    return -1;
  }

  src_w = (int)snap->header.w;
  src_h = (int)snap->header.h;
  src_stride = (int)snap->header.stride;
  dst_w = src_w / EW_MIRROR_SCALE;
  dst_h = src_h / EW_MIRROR_SCALE;
  if (dst_w < 1) {
    dst_w = src_w;
  }
  if (dst_h < 1) {
    dst_h = src_h;
  }

  need = (uint32_t)dst_w * (uint32_t)dst_h * 2u;
  if (need > sizeof(scratch)) {
    lv_draw_buf_destroy(snap);
    printf("[ew-mirror] scratch too small need=%u\n", need);
    return -1;
  }

  if (dst_w == src_w && dst_h == src_h) {
    memcpy(scratch, snap->data, need);
  } else {
    downscale_rgb565(snap->data, src_w, src_h, src_stride, scratch, dst_w, dst_h);
  }
  lv_draw_buf_destroy(snap);

  if (mirror_send_rgb565(scratch, (uint16_t)dst_w, (uint16_t)dst_h) != 0) {
    printf("[ew-mirror] send fail\n");
    return -1;
  }
  printf("[ew-mirror] frame %dx%d %uB\n", dst_w, dst_h, need);
  return 0;
}

void ew_mirror_set_enabled(int on)
{
  g_mirror_on = on ? 1 : 0;
  g_last_ms = 0;
  printf("[ew-mirror] stream %s\n", g_mirror_on ? "ON" : "OFF");
}

int ew_mirror_enabled(void)
{
  return g_mirror_on;
}

void ew_mirror_snap_once(void)
{
  (void)mirror_capture_send();
}

void ew_mirror_tick(void)
{
  uint32_t now;

  if (!g_mirror_on || g_sending) {
    return;
  }
  now = mirror_now_ms();
  if (g_last_ms != 0 && (now - g_last_ms) < EW_MIRROR_PERIOD_MS) {
    return;
  }
  g_last_ms = now;
  (void)mirror_capture_send();
}

#else

void ew_mirror_set_enabled(int on)
{
  (void)on;
}

int ew_mirror_enabled(void)
{
  return 0;
}

void ew_mirror_snap_once(void)
{
}

void ew_mirror_tick(void)
{
}

#endif
