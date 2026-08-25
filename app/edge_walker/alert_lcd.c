/****************************************************************************
 * LCD 提醒显示：/dev/fb0 整屏填色（RGB565）
 ****************************************************************************/

#include "alert_lcd.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>

#ifdef __NuttX__
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <nuttx/video/fb.h>
#endif

#define EW_FB_DEV "/dev/fb0"

#ifdef __NuttX__

#define EW_RGB565(r, g, b) \
  ((uint16_t)(((uint16_t)(r)&0xF8u) << 8) | (((uint16_t)(g)&0xFCu) << 3) | ((uint16_t)(b) >> 3))

static uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b)
{
  return EW_RGB565(r, g, b);
}

static int fb_fill_color(uint16_t color, struct fb_videoinfo_s *vinfo_out)
{
  struct fb_videoinfo_s vinfo;
  struct fb_planeinfo_s pinfo;
  int fd;
  int ret;

  fd = open(EW_FB_DEV, O_RDWR);
  if (fd < 0) {
    return -errno;
  }

  ret = ioctl(fd, FBIOGET_VIDEOINFO, (unsigned long)((uintptr_t)&vinfo));
  if (ret < 0) {
    close(fd);
    return -errno;
  }

  ret = ioctl(fd, FBIOGET_PLANEINFO, (unsigned long)((uintptr_t)&pinfo));
  if (ret < 0) {
    close(fd);
    return -errno;
  }

  if (vinfo_out != NULL) {
    *vinfo_out = vinfo;
  }

  if (pinfo.fbmem != NULL && pinfo.fblen > 0) {
    if (pinfo.bpp == 16) {
      uint16_t *p = (uint16_t *)pinfo.fbmem;
      size_t pixels = pinfo.fblen / 2u;
      for (size_t i = 0; i < pixels; i++) {
        p[i] = color;
      }
    } else if (pinfo.bpp == 32) {
      uint32_t c32 = (uint32_t)color;
      c32 |= (c32 << 16);
      uint32_t *p = (uint32_t *)pinfo.fbmem;
      size_t pixels = pinfo.fblen / 4u;
      for (size_t i = 0; i < pixels; i++) {
        p[i] = c32;
      }
    } else {
      memset(pinfo.fbmem, (color >> 8) & 0xFF, pinfo.fblen);
    }
  }

#ifdef CONFIG_FB_UPDATE
  {
    struct fb_area_s area;

    area.x = 0;
    area.y = 0;
    area.w = vinfo.xres;
    area.h = vinfo.yres;
    ioctl(fd, FBIO_UPDATE, (unsigned long)((uintptr_t)&area));
  }
#endif

  close(fd);
  return 0;
}

static uint16_t level_color(ew_alert_level_t level)
{
  if (level == EW_ALERT_EMERGENCY) {
    return rgb565(255, 0, 0);
  }
  if (level == EW_ALERT_STRONG) {
    return rgb565(255, 120, 0);
  }
  if (level == EW_ALERT_SOFT) {
    return rgb565(255, 220, 0);
  }
  return rgb565(0, 0, 0);
}

#endif /* __NuttX__ */

void alert_lcd_show(ew_alert_level_t level, const char *reason)
{
#ifdef __NuttX__
  int ret = fb_fill_color(level_color(level), NULL);
  if (ret == 0) {
    printf("[alert_lcd] level=%d reason=%s color=0x%04x\n",
           (int)level,
           reason ? reason : "",
           (unsigned)level_color(level));
  }
#else
  (void)level;
  (void)reason;
#endif
}

void alert_lcd_boot_splash(void)
{
#ifdef __NuttX__
  /* 待机蓝：上电即亮，表示系统就绪 */
  uint16_t blue = rgb565(0, 80, 200);
  if (fb_fill_color(blue, NULL) == 0) {
    printf("[alert_lcd] boot splash (ready)\n");
  }
#endif
}

int alert_lcd_info(void)
{
#ifdef __NuttX__
  struct fb_videoinfo_s vinfo;
  struct fb_planeinfo_s pinfo;
  int fd;
  int ret;

  fd = open(EW_FB_DEV, O_RDWR);
  if (fd < 0) {
    printf("[alert_lcd] %s open failed: %d\n", EW_FB_DEV, errno);
    return 1;
  }

  ret = ioctl(fd, FBIOGET_VIDEOINFO, (unsigned long)((uintptr_t)&vinfo));
  if (ret < 0) {
    printf("[alert_lcd] FBIOGET_VIDEOINFO failed: %d\n", errno);
    close(fd);
    return 1;
  }

  ret = ioctl(fd, FBIOGET_PLANEINFO, (unsigned long)((uintptr_t)&pinfo));
  if (ret < 0) {
    printf("[alert_lcd] FBIOGET_PLANEINFO failed: %d\n", errno);
    close(fd);
    return 1;
  }

  printf("[alert_lcd] %s ok: %ux%u bpp=%u stride=%u fblen=%lu fbmem=%p\n",
         EW_FB_DEV,
         (unsigned)vinfo.xres,
         (unsigned)vinfo.yres,
         (unsigned)pinfo.bpp,
         (unsigned)pinfo.stride,
         (unsigned long)pinfo.fblen,
         pinfo.fbmem);
  close(fd);
  return 0;
#else
  printf("[alert_lcd] host stub\n");
  return 0;
#endif
}

int alert_lcd_selftest(void)
{
#ifdef __NuttX__
  static const struct {
    const char *name;
    uint16_t color;
  } steps[] = {
    {"RED",   EW_RGB565(255, 0, 0)},
    {"GREEN", EW_RGB565(0, 255, 0)},
    {"BLUE",  EW_RGB565(0, 0, 255)},
    {"BLACK", EW_RGB565(0, 0, 0)},
  };
  struct fb_videoinfo_s vinfo;
  unsigned i;

  if (fb_fill_color(steps[0].color, &vinfo) < 0) {
    printf("[alert_lcd] selftest: %s not available\n", EW_FB_DEV);
    return 1;
  }

  printf("[alert_lcd] selftest %ux%u — watch screen cycle R/G/B/Black\n",
         (unsigned)vinfo.xres, (unsigned)vinfo.yres);

  for (i = 0; i < (sizeof(steps) / sizeof(steps[0])); i++) {
    fb_fill_color(steps[i].color, NULL);
    printf("[alert_lcd]   -> %s\n", steps[i].name);
    usleep(500000);
  }
  return 0;
#else
  printf("[alert_lcd] host stub selftest\n");
  return 0;
#endif
}
