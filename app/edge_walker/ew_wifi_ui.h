/****************************************************************************
 * WiFi 配网页：扫描列表 + 密码输入
 *
 * 由 ew_ui_loop 驱动，三个钩子都必须在 LVGL 主循环线程里调用。
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_WIFI_UI_H
#define EDGE_WALKER_EW_WIFI_UI_H

#ifdef __cplusplus
extern "C" {
#endif

/* 在当前 screen 上建页，并立即发起一次扫描 */
void ew_wifi_ui_build(void);

/* 每帧调用：把后台扫描/连接的结果搬到界面上 */
void ew_wifi_ui_tick(void);

/* 离开本页 */
void ew_wifi_ui_teardown(void);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_WIFI_UI_H */
