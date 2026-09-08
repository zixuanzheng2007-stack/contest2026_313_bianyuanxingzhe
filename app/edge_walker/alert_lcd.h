/****************************************************************************
 * LCD 提醒显示（郑子轩）
 *
 * 通过 /dev/fb0 整屏填色表示告警档；无 fb 则静默跳过。
 ****************************************************************************/

#ifndef EDGE_WALKER_ALERT_LCD_H
#define EDGE_WALKER_ALERT_LCD_H

#include "alert_output.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 告警刷屏：NONE=黑 / SOFT=黄 / STRONG=橙 / EMERGENCY=红 */
void alert_lcd_show(ew_alert_level_t level, const char *reason);

/* 上电待机：LVGL 开 /dev/lcd0 常驻刷新（EW READY），用于 rcS: ew boot */
void alert_lcd_boot_splash(void);

/* 接线自检：依次红/绿/蓝/黑，每色约 0.5s；返回 0=fb 可用 */
int alert_lcd_selftest(void);

/* 打印 fb0 分辨率等信息到控制台，返回 0=可用 */
int alert_lcd_info(void);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_ALERT_LCD_H */
