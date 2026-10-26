/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * LVGL snapshot → RGB565 RLE → 串口二进制帧
 *
 * 1Mbps 控制台发送原始全帧约需 2.8s。LVGL 页面大多是纯色区域，使用
 * PackBits 风格的 RGB565 无损 RLE 后通常可缩到原来的几分之一到几十
 * 分之一，同时用 257 字节分片发送，不额外申请一整帧缓存。
 *
 * 原始帧：0x89 'E' 'W' 'F' | w u16 | h u16 | len u32 | RGB565
 * RLE 帧： 0x89 'E' 'W' 'R' | w u16 | h u16 | len u32 | packets
 * packet: control u8；bit7=1 为重复像素，否则为字面像素；长度=(低7位+1)。
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
#define EW_RLE_MAGIC3 'R'

#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)

static int g_mirror_on;
static uint32_t g_last_ms;
static int g_sending;
static ew_mirror_mode_t g_mode = EW_MIRROR_FAST;
static int g_scale = 3;
static uint32_t g_period_ms = 350;
static int g_log_next_frame;
static uint32_t g_lease_ms;

static uint32_t mirror_now_ms(void)
{
  return lv_tick_get();
}

static void mirror_apply_mode(ew_mirror_mode_t mode)
{
  switch (mode) {
    case EW_MIRROR_HD:
      g_scale = 1;
      g_period_ms = 1000;
      break;
    case EW_MIRROR_NORMAL:
      g_scale = 1;
      g_period_ms = 500;
      break;
    case EW_MIRROR_FAST:
    default:
      g_scale = 2;
      g_period_ms = 160;
      break;
  }
  g_mode = mode;
  g_lease_ms = mirror_now_ms();
}

static void downscale_rgb565(const uint8_t *src, int src_w, int src_h, int src_stride,
                             int scale, uint8_t *dst, int dst_w, int dst_h)
{
  int y;
  int x;

  for (y = 0; y < dst_h; y++) {
    const uint8_t *row = src + (y * scale) * src_stride;
    for (x = 0; x < dst_w; x++) {
      const uint8_t *px = row + (x * scale) * 2;
      dst[(y * dst_w + x) * 2] = px[0];
      dst[(y * dst_w + x) * 2 + 1] = px[1];
    }
  }
}

static int pixel_equal565(const uint8_t *data, uint32_t a, uint32_t b)
{
  return data[a * 2u] == data[b * 2u] &&
         data[a * 2u + 1u] == data[b * 2u + 1u];
}

/* 生成一个 RLE packet，最大 1 + 128*2 = 257 字节。 */
static unsigned rle565_next_packet(const uint8_t *data, uint32_t pixels,
                                   uint32_t *pos, uint8_t *out)
{
  uint32_t start;
  uint32_t run;
  uint32_t literal;

  if (data == NULL || pos == NULL || out == NULL || *pos >= pixels) {
    return 0;
  }

  start = *pos;
  run = 1;
  while (run < 128u && start + run < pixels &&
         pixel_equal565(data, start, start + run)) {
    run++;
  }
  if (run >= 3u) {
    out[0] = (uint8_t)(0x80u | (run - 1u));
    out[1] = data[start * 2u];
    out[2] = data[start * 2u + 1u];
    *pos += run;
    return 3;
  }

  literal = run;
  while (literal < 128u && start + literal < pixels) {
    uint32_t next = start + literal;
    uint32_t next_run = 1;

    while (next_run < 3u && next + next_run < pixels &&
           pixel_equal565(data, next, next + next_run)) {
      next_run++;
    }
    if (next_run >= 3u) {
      break;
    }
    literal++;
  }
  out[0] = (uint8_t)(literal - 1u);
  memcpy(out + 1, data + start * 2u, literal * 2u);
  *pos += literal;
  return 1u + literal * 2u;
}

static uint32_t rle565_size(const uint8_t *data, uint32_t pixels)
{
  uint8_t packet[257];
  uint32_t pos = 0;
  uint32_t total = 0;
  unsigned n;

  while ((n = rle565_next_packet(data, pixels, &pos, packet)) != 0) {
    total += n;
  }
  return total;
}

static int mirror_write_all(const uint8_t *data, uint32_t len)
{
  uint32_t off = 0;
  int idle = 0;

  while (off < len) {
    ssize_t n = write(STDOUT_FILENO, data + off, len - off);

    if (n > 0) {
      off += (uint32_t)n;
      idle = 0;
    } else {
      if (++idle > 1000) {
        return -1;
      }
      usleep(1000);
    }
  }
  return 0;
}

static int mirror_send_header(uint8_t magic3, uint16_t w, uint16_t h,
                              uint32_t len)
{
  uint8_t hdr[12];

  if (w == 0 || h == 0 || len == 0) {
    return -1;
  }
  hdr[0] = EW_FB_MAGIC0;
  hdr[1] = EW_FB_MAGIC1;
  hdr[2] = EW_FB_MAGIC2;
  hdr[3] = magic3;
  hdr[4] = (uint8_t)(w & 0xffu);
  hdr[5] = (uint8_t)(w >> 8);
  hdr[6] = (uint8_t)(h & 0xffu);
  hdr[7] = (uint8_t)(h >> 8);
  hdr[8] = (uint8_t)(len & 0xffu);
  hdr[9] = (uint8_t)((len >> 8) & 0xffu);
  hdr[10] = (uint8_t)((len >> 16) & 0xffu);
  hdr[11] = (uint8_t)((len >> 24) & 0xffu);

  if (mirror_write_all(hdr, sizeof(hdr)) != 0) {
    return -1;
  }
  return 0;
}

static int mirror_send_rgb565(const uint8_t *data, uint16_t w, uint16_t h,
                              uint32_t *wire_len, int *compressed)
{
  uint8_t packet[257];
  uint32_t pixels;
  uint32_t raw_len;
  uint32_t encoded_len;
  uint32_t pos = 0;
  unsigned n;
  int rc = 0;

  if (data == NULL || w == 0 || h == 0) {
    return -1;
  }
  pixels = (uint32_t)w * (uint32_t)h;
  raw_len = pixels * 2u;
  encoded_len = rle565_size(data, pixels);
  g_sending = 1;

  if (encoded_len < raw_len) {
    rc = mirror_send_header(EW_RLE_MAGIC3, w, h, encoded_len);
    while (rc == 0 &&
           (n = rle565_next_packet(data, pixels, &pos, packet)) != 0) {
      rc = mirror_write_all(packet, n);
    }
    if (wire_len != NULL) {
      *wire_len = encoded_len;
    }
    if (compressed != NULL) {
      *compressed = 1;
    }
  } else {
    rc = mirror_send_header(EW_FB_MAGIC3, w, h, raw_len);
    if (rc == 0) {
      rc = mirror_write_all(data, raw_len);
    }
    if (wire_len != NULL) {
      *wire_len = raw_len;
    }
    if (compressed != NULL) {
      *compressed = 0;
    }
  }
  g_sending = 0;
  return rc;
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
  uint32_t need;
  uint32_t wire_len = 0;
  int compressed = 0;

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
  dst_w = src_w / g_scale;
  dst_h = src_h / g_scale;
  if (dst_w < 1) {
    dst_w = src_w;
  }
  if (dst_h < 1) {
    dst_h = src_h;
  }

  need = (uint32_t)dst_w * (uint32_t)dst_h * 2u;
  /* Forward downsampling is safe in place: each destination pixel is at or
   * before its source pixel. Also pack padded rows for full-size snapshots.
   */
  if (g_scale > 1 || src_stride != src_w * 2) {
    downscale_rgb565(snap->data, src_w, src_h, src_stride, g_scale,
                     snap->data, dst_w, dst_h);
  }

  if (mirror_send_rgb565(snap->data, (uint16_t)dst_w, (uint16_t)dst_h,
                         &wire_len, &compressed) != 0) {
    lv_draw_buf_destroy(snap);
    printf("[ew-mirror] send fail\n");
    return -1;
  }
  lv_draw_buf_destroy(snap);
  if (g_log_next_frame) {
    printf("[ew-mirror] frame %dx%d raw=%u wire=%u codec=%s mode=%d\n",
           dst_w, dst_h, need, wire_len, compressed ? "rle" : "raw",
           (int)g_mode);
    g_log_next_frame = 0;
  }
  return 0;
}

void ew_mirror_set_mode(ew_mirror_mode_t mode)
{
  if ((unsigned)mode > EW_MIRROR_HD) {
    mode = EW_MIRROR_FAST;
  }
  mirror_apply_mode(mode);
  g_last_ms = 0;
  g_log_next_frame = 1;
  printf("[ew-mirror] mode=%d scale=1/%d period=%ums\n",
         (int)mode, g_scale, (unsigned)g_period_ms);
}

ew_mirror_mode_t ew_mirror_get_mode(void)
{
  return g_mode;
}

void ew_mirror_set_enabled(int on)
{
  g_mirror_on = on ? 1 : 0;
  g_last_ms = 0;
  if (g_mirror_on) {
    mirror_apply_mode(g_mode);
    g_lease_ms = mirror_now_ms();
  }
  g_log_next_frame = 1;
  printf("[ew-mirror] stream %s\n", g_mirror_on ? "ON" : "OFF");
}

int ew_mirror_enabled(void)
{
  return g_mirror_on;
}

void ew_mirror_snap_once(void)
{
  int saved_scale = g_scale;

  /* 单帧调试：始终全分辨率，避免 FAST 1/3 再放大发糊 */
  g_scale = 1;
  g_log_next_frame = 1;
  (void)mirror_capture_send();
  g_scale = saved_scale;
}

void ew_mirror_tick(void)
{
  uint32_t now;

  if (!g_mirror_on || g_sending) {
    return;
  }
  now = mirror_now_ms();
  if (g_lease_ms != 0 && (now - g_lease_ms) > 5000u) {
    g_mirror_on = 0;
    printf("[ew-mirror] stream lease expired\n");
    return;
  }
  if (g_last_ms != 0 && (now - g_last_ms) < g_period_ms) {
    return;
  }
  g_last_ms = now;
  (void)mirror_capture_send();
}

#else

void ew_mirror_set_mode(ew_mirror_mode_t mode)
{
  (void)mode;
}

ew_mirror_mode_t ew_mirror_get_mode(void)
{
  return EW_MIRROR_FAST;
}

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
