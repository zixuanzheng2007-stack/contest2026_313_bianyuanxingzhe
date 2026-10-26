/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * 串口 RGB565 镜像（LVGL snapshot → COM7 二进制帧）
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_MIRROR_H
#define EDGE_WALKER_EW_MIRROR_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  EW_MIRROR_FAST = 0,    /* 1/2 分辨率无损 RLE，优先低延迟 */
  EW_MIRROR_NORMAL,      /* 全分辨率无损 RLE，默认交互模式 */
  EW_MIRROR_HD           /* 全分辨率无损 RLE，降低刷新频率 */
} ew_mirror_mode_t;

void ew_mirror_set_mode(ew_mirror_mode_t mode);
ew_mirror_mode_t ew_mirror_get_mode(void);

void ew_mirror_set_enabled(int on);
int ew_mirror_enabled(void);
void ew_mirror_snap_once(void);
void ew_mirror_tick(void);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_MIRROR_H */
