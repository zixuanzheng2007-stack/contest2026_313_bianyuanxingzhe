/****************************************************************************
 * 预警页显示（郑子轩）
 *
 * CO5300 只走 LVGL + /dev/lcd0，告警靠改 LVGL 对象颜色/文字。
 * 切页由 ew_ui_goto() 统一处理，本模块不再自己管「要不要去对话页」。
 ****************************************************************************/

#ifndef EDGE_WALKER_ALERT_LCD_H
#define EDGE_WALKER_ALERT_LCD_H

#include "alert_output.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 刷新预警配色与文字；常驻 UI 未起来时改为落盘排队，等它起来再显示。 */
void alert_lcd_show(ew_alert_level_t level, const char *reason);

/* rcS 入口：初始化 LVGL 并进入 UI 主循环，正常情况下不返回。 */
void alert_lcd_boot_splash(void);

/* 以下三个由 ew_ui_loop 驱动，必须在 LVGL 线程调用 */
void alert_lcd_attach_warn_ui(void);
void alert_lcd_warn_tick(void);
void alert_lcd_detach_warn_ui(void);

/* 屏上走一遍红/黄/蓝，确认显示链路通；0 = 成功 */
int alert_lcd_selftest(void);

/* 打印显示后端信息，0 = 显示可用 */
int alert_lcd_info(void);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_ALERT_LCD_H */
