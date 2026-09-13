/****************************************************************************
 * 边缘行者屏上界面：预警 / 智能体对话 / WiFi 配网 三页共用一个 LVGL 主循环
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_CHAT_H
#define EDGE_WALKER_EW_CHAT_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  EW_PAGE_WARN = 0,
  EW_PAGE_CHAT,
  EW_PAGE_WIFI
} ew_page_t;

/* 三页导航按钮统一尺寸，避免各页面各自维护。 */
#define EW_UI_NAV_BTN_W 120
#define EW_UI_NAV_BTN_H 56

/* 初始化 LVGL 并从对话页进入主循环 */
void ew_chat_run(void);

/* LVGL 已初始化时进入主循环；start_in_chat=1 从对话页起步 */
void ew_ui_loop(int start_in_chat);

/* 请求切页。可从任意页的事件回调调用，下一帧生效。 */
void ew_ui_goto(ew_page_t page);

/* 当前显示的页 */
ew_page_t ew_ui_page(void);

/* 供各页复用的中文字体（lv_font_t *，未加载到 TTF 时为 NULL） */
void *ew_ui_font(void);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_CHAT_H */
