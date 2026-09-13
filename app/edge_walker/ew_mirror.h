/****************************************************************************
 * 串口 RGB565 镜像（LVGL snapshot → COM7 二进制帧）
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_MIRROR_H
#define EDGE_WALKER_EW_MIRROR_H

#ifdef __cplusplus
extern "C" {
#endif

void ew_mirror_set_enabled(int on);
int ew_mirror_enabled(void);
void ew_mirror_snap_once(void);
void ew_mirror_tick(void);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_MIRROR_H */
