/****************************************************************************
 * LVGL 智能体对话：点按快捷句 + 中/英键盘（无语音）
 ****************************************************************************/

#include "ew_chat.h"
#include "ew_serial_ctl.h"
#include "ew_mirror.h"
#include "ew_agent.h"
#include "ew_llm.h"
#include "alert_lcd.h"
#include "ew_pinyin.h"
#include "ew_wifi_ui.h"

#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <ctype.h>

#ifdef __NuttX__
#include <pthread.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/boardctl.h>
#include <nuttx/config.h>
#include <nuttx/input/keyboard.h>
#include <nuttx/input/kbd_codec.h>
#include <nuttx/input/virtio-input-event-codes.h>
#ifdef CONFIG_LV_USE_NUTTX
#include <lvgl/lvgl.h>
#if LV_USE_FREETYPE
#include <lvgl/src/libs/freetype/lv_freetype.h>
#endif
#endif
#endif

#define EW_CHAT_MAX_BUBBLE 12
#define EW_CHAT_TEXT_MAX 512

/* 每帧最长休眠：预警变色要跟得上雷达，别让 LVGL 一觉睡过头 */
#define EW_UI_FRAME_MS 8

/* 建页后忽略切页请求的时间，躲开上一页松手时的触摸抖动 */
#define EW_UI_GATE_MS 400

#ifdef __NuttX__
#ifdef CONFIG_LV_USE_NUTTX

static lv_obj_t *g_scr;
static lv_obj_t *g_status;
static lv_obj_t *g_list;
static lv_obj_t *g_ta;
static lv_obj_t *g_kb;
static lv_obj_t *g_ime_bar;
static lv_obj_t *g_py_lab;
static lv_obj_t *g_cands[5];
static lv_obj_t *g_more_btn;
static char g_cand_zh[5][20];
static unsigned g_cand_eat[5];
static int g_ime_page;
static lv_obj_t *g_lang_btn;
static lv_obj_t *g_wait_bubble;
static lv_font_t *g_font;
static volatile int g_busy;
static char g_pending[256];
static char g_reply[EW_CHAT_TEXT_MAX];
static volatile int g_reply_ready;
static bool g_zh;
static char g_py[32];
static int g_kbd_fd = -1;
static int g_shift;

/* 当前页与待切换页。g_page_pending 可被事件回调改写，主循环下一帧生效。 */
static ew_page_t g_page = EW_PAGE_WARN;
static volatile ew_page_t g_page_pending = EW_PAGE_WARN;

static void hide_kb_event(lv_event_t *e);

/* CJK 字体整段只在 FreeType 打开时才有意义，关掉时界面退回英文 */
#if LV_USE_FREETYPE

static const char *g_font_paths[] = {
  "/data/font/MiSans-Regular.ttf",
  "/data/MiSans-Regular.ttf",
  NULL
};

/* TTF 可能正被 adb push 写入，太小就当它还没到齐 */
static int font_ready(const char *path)
{
  struct stat st;

  if (path == NULL || access(path, R_OK) != 0) {
    return 0;
  }
  return (stat(path, &st) == 0 && st.st_size >= 200000);
}

static lv_font_t *try_cjk_font(uint32_t size)
{
  int i;

  /* lv_init 可能已经 init 过；失败也继续 create */
  (void)lv_freetype_init(256);
  for (i = 0; g_font_paths[i] != NULL; i++) {
    lv_font_t *f;

    if (!font_ready(g_font_paths[i])) {
      continue;
    }
    f = lv_freetype_font_create(g_font_paths[i],
                                LV_FREETYPE_FONT_RENDER_MODE_BITMAP,
                                size, LV_FREETYPE_FONT_STYLE_NORMAL);
    if (f != NULL) {
      printf("[ew-chat] font %s @%u\n", g_font_paths[i], (unsigned)size);
      return f;
    }
    printf("[ew-chat] FT create fail %s\n", g_font_paths[i]);
  }
  printf("[ew-chat] CJK font not loaded\n");
  return NULL;
}

#endif /* LV_USE_FREETYPE */

static void apply_font(lv_obj_t *obj)
{
  if (g_font != NULL) {
    lv_obj_set_style_text_font(obj, g_font, 0);
  }
}

static void hide_kb(void)
{
  if (g_kb != NULL) {
    lv_obj_add_flag(g_kb, LV_OBJ_FLAG_HIDDEN);
  }
  if (g_ime_bar != NULL) {
    lv_obj_add_flag(g_ime_bar, LV_OBJ_FLAG_HIDDEN);
  }
}

static void show_kb(void)
{
  if (g_kb != NULL) {
    lv_obj_clear_flag(g_kb, LV_OBJ_FLAG_HIDDEN);
  }
  if (g_zh && g_ime_bar != NULL) {
    lv_obj_clear_flag(g_ime_bar, LV_OBJ_FLAG_HIDDEN);
  }
}

static void add_bubble(const char *text, bool user)
{
  lv_obj_t *row;
  lv_obj_t *lab;
  lv_color_t bg;

  if (g_list == NULL || text == NULL) {
    return;
  }

  while (lv_obj_get_child_count(g_list) >= EW_CHAT_MAX_BUBBLE) {
    lv_obj_t *old = lv_obj_get_child(g_list, 0);
    if (old != NULL) {
      if (old == g_wait_bubble) {
        g_wait_bubble = NULL;
      }
      lv_obj_delete(old);
    } else {
      break;
    }
  }

  row = lv_obj_create(g_list);
  lv_obj_set_width(row, lv_pct(user ? 88 : 92));
  lv_obj_set_height(row, LV_SIZE_CONTENT);
  lv_obj_set_style_radius(row, 12, 0);
  lv_obj_set_style_border_width(row, 0, 0);
  lv_obj_set_style_pad_all(row, 10, 0);
  bg = user ? lv_color_hex(0x1E5AA8) : lv_color_hex(0x2A2F4A);
  lv_obj_set_style_bg_color(row, bg, 0);
  lv_obj_set_style_bg_opa(row, LV_OPA_COVER, 0);
  if (user) {
    lv_obj_set_style_margin_left(row, 40, 0);
  }

  lab = lv_label_create(row);
  apply_font(lab);
  lv_label_set_long_mode(lab, LV_LABEL_LONG_WRAP);
  lv_obj_set_width(lab, lv_pct(100));
  lv_label_set_text(lab, text);
  lv_obj_set_style_text_color(lab, lv_color_white(), 0);
  lv_obj_add_flag(row, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_flag(row, LV_OBJ_FLAG_EVENT_BUBBLE);
  lv_obj_add_flag(lab, LV_OBJ_FLAG_EVENT_BUBBLE);
  lv_obj_add_event_cb(row, hide_kb_event, LV_EVENT_CLICKED, NULL);
  lv_obj_scroll_to_view(row, LV_ANIM_ON);
}

static int has_cjk(const char *s)
{
  const unsigned char *p = (const unsigned char *)s;

  if (p == NULL) {
    return 0;
  }
  while (*p != '\0') {
    if (*p >= 0xE0) {
      return 1;
    }
    p++;
  }
  return 0;
}

static const char *local_reply(const char *q)
{
  int zh;

  if (q == NULL) {
    return NULL;
  }
  zh = has_cjk(q);
  if (strstr(q, "Who are you") || strstr(q, "你是谁") || strstr(q, "介绍")) {
    return zh ? "我是边缘行者智能体：本地雷达近距预警 + 云端问答。开发板没有麦克风，请点快捷句或用键盘。"
              : "I am Edge Walker: local radar warning plus cloud Q&A. No mic — tap a chip or type.";
  }
  if (strstr(q, "alert") || strstr(q, "告警") || strstr(q, "How does") ||
      strstr(q, "怎么工作") || strstr(q, "预警")) {
    return zh ? "雷达走 UART2。目标近且快：WARN 橙色、CRIT 红色。安全环不依赖云端，断网也能告警。"
              : "Radar on UART2. Near+fast -> WARN orange / CRIT red. Safety loop works offline.";
  }
  if (strstr(q, "EW READY") || strstr(q, "READY") || strstr(q, "状态")) {
    return zh ? "EW READY 表示空闲、无靠近告警。橙色 WARN，红色 CRIT。"
              : "EW READY = idle, no approach alert. Orange WARN, red CRIT.";
  }
  if (strcmp(q, "Hello") == 0 || strcmp(q, "你好") == 0 || strstr(q, "hello") ||
      strstr(q, "Hello")) {
    return zh ? "你好。点快捷句，或点输入框用 ZH 拼音 / EN 键盘。点对话区可收起键盘。"
              : "Hello. Tap a chip, or the box for ZH pinyin / EN keys. Tap the chat area to hide the keyboard.";
  }
  return NULL;
}

/* 去掉 emoji（4 字节 UTF-8），保留中文 */
static void sanitize_reply(char *s)
{
  unsigned char *r;
  unsigned char *w;
  int n;

  if (s == NULL) {
    return;
  }
  r = (unsigned char *)s;
  w = r;
  while (*r != '\0') {
    if (*r < 0x80) {
      *w++ = *r++;
    } else if (*r >= 0xF0) {
      n = (*r >= 0xF8) ? 5 : 4;
      while (n-- > 0 && *r != '\0') {
        r++;
      }
    } else if (*r >= 0xE0) {
      n = 3;
      while (n-- > 0 && *r != '\0') {
        *w++ = *r++;
      }
    } else {
      n = 2;
      while (n-- > 0 && *r != '\0') {
        *w++ = *r++;
      }
    }
  }
  *w = '\0';
}

static void *ask_thread(void *arg)
{
  (void)arg;
  g_reply[0] = '\0';
  if (ew_llm_ask(g_pending, g_reply, sizeof(g_reply)) != 0) {
    const char *fb = local_reply(g_pending);
    if (fb != NULL) {
      snprintf(g_reply, sizeof(g_reply), "%s", fb);
    } else {
      snprintf(g_reply, sizeof(g_reply),
               "网络问答暂时不可用。可点快捷句，或稍后再问。");
    }
  }
  g_reply_ready = 1;
  return NULL;
}

static void start_ask(const char *text)
{
  pthread_t th;
  pthread_attr_t attr;
  const char *p;

  if (text == NULL || g_busy) {
    return;
  }
  while (*text == ' ') {
    text++;
  }
  if (text[0] == '\0') {
    return;
  }

  strncpy(g_pending, text, sizeof(g_pending) - 1);
  g_pending[sizeof(g_pending) - 1] = '\0';
  add_bubble(g_pending, true);
  add_bubble("...", false);
  g_wait_bubble = lv_obj_get_child(g_list,
                                  (int32_t)(lv_obj_get_child_count(g_list) - 1));
  g_busy = 1;
  g_reply_ready = 0;
  if (g_status != NULL) {
    lv_label_set_text(g_status, "thinking... (AT + MiMo)");
  }
  hide_kb();

  p = local_reply(g_pending);
  if (p != NULL) {
    snprintf(g_reply, sizeof(g_reply), "%s", p);
    g_reply_ready = 1;
    return;
  }

  pthread_attr_init(&attr);
  pthread_attr_setstacksize(&attr, 65536);
  if (pthread_create(&th, &attr, ask_thread, NULL) != 0) {
    if (ew_llm_ask(g_pending, g_reply, sizeof(g_reply)) != 0) {
      snprintf(g_reply, sizeof(g_reply), "网络问答暂时不可用，请再试一次或点快捷句。");
    }
    g_reply_ready = 1;
  } else {
    pthread_detach(th);
  }
  pthread_attr_destroy(&attr);
}

static void send_from_ta(void)
{
  const char *t;

  if (g_ta == NULL) {
    return;
  }
  t = lv_textarea_get_text(g_ta);
  start_ask(t);
  lv_textarea_set_text(g_ta, "");
  g_py[0] = '\0';
}

static void refresh_cands(void)
{
  int n;
  int i;
  int extra;

  if (g_py_lab != NULL) {
    lv_label_set_text_fmt(g_py_lab, "py: %s", g_py[0] ? g_py : "_");
  }
  for (i = 0; i < 5; i++) {
    g_cand_zh[i][0] = '\0';
    g_cand_eat[i] = 0;
    if (g_cands[i] != NULL) {
      lv_obj_add_flag(g_cands[i], LV_OBJ_FLAG_HIDDEN);
    }
  }
  if (g_more_btn != NULL) {
    lv_obj_add_flag(g_more_btn, LV_OBJ_FLAG_HIDDEN);
  }
  if (g_py[0] == '\0') {
    g_ime_page = 0;
    return;
  }
  n = ew_pinyin_lookup(g_py, g_ime_page * 5, g_cand_zh, g_cand_eat, 5);
  for (i = 0; i < n; i++) {
    lv_obj_t *lab = lv_obj_get_child(g_cands[i], 0);
    if (lab != NULL) {
      lv_label_set_text(lab, g_cand_zh[i]);
    }
    lv_obj_clear_flag(g_cands[i], LV_OBJ_FLAG_HIDDEN);
  }
  {
    char peek[1][20];
    unsigned peate[1];

    extra = ew_pinyin_lookup(g_py, (g_ime_page + 1) * 5, peek, peate, 1);
  }
  if (extra > 0 && g_more_btn != NULL) {
    lv_obj_clear_flag(g_more_btn, LV_OBJ_FLAG_HIDDEN);
  }
}

static void commit_zh_idx(int idx)
{
  unsigned eat;
  size_t n;

  if (g_ta == NULL || idx < 0 || idx >= 5 || g_cand_zh[idx][0] == '\0') {
    return;
  }
  lv_textarea_add_text(g_ta, g_cand_zh[idx]);
  eat = g_cand_eat[idx];
  n = strlen(g_py);
  if (eat == 0 || eat >= n) {
    g_py[0] = '\0';
  } else {
    memmove(g_py, g_py + eat, n - eat + 1);
  }
  g_ime_page = 0;
  refresh_cands();
}

static void cand_clicked(lv_event_t *e)
{
  lv_obj_t *btn = lv_event_get_target(e);
  int i;

  for (i = 0; i < 5; i++) {
    if (btn == g_cands[i]) {
      commit_zh_idx(i);
      return;
    }
  }
}

static void more_clicked(lv_event_t *e)
{
  (void)e;
  g_ime_page++;
  refresh_cands();
  if (g_cands[0] != NULL && lv_obj_has_flag(g_cands[0], LV_OBJ_FLAG_HIDDEN)) {
    g_ime_page = 0;
    refresh_cands();
  }
}

static void handle_zh_key(const char *txt)
{
  size_t n;

  if (txt == NULL || txt[0] == '\0') {
    return;
  }
  if (strcmp(txt, LV_SYMBOL_BACKSPACE) == 0 || strcmp(txt, "Del") == 0) {
    n = strlen(g_py);
    if (n > 0) {
      g_py[n - 1] = '\0';
      g_ime_page = 0;
      refresh_cands();
    } else if (g_ta != NULL) {
      lv_textarea_delete_char(g_ta);
    }
    return;
  }
  if (strcmp(txt, " ") == 0 || strcmp(txt, LV_SYMBOL_NEW_LINE) == 0) {
    if (g_cands[0] != NULL && !lv_obj_has_flag(g_cands[0], LV_OBJ_FLAG_HIDDEN)) {
      commit_zh_idx(0);
    } else if (g_py[0] != '\0') {
      lv_textarea_add_text(g_ta, g_py);
      g_py[0] = '\0';
      refresh_cands();
    }
    return;
  }
  if (strcmp(txt, LV_SYMBOL_OK) == 0 || strcmp(txt, "Enter") == 0) {
    if (g_py[0] != '\0' && g_cands[0] != NULL &&
        !lv_obj_has_flag(g_cands[0], LV_OBJ_FLAG_HIDDEN)) {
      commit_zh_idx(0);
    }
    send_from_ta();
    return;
  }
  if (txt[0] >= 'a' && txt[0] <= 'z' && txt[1] == '\0') {
    n = strlen(g_py);
    if (n + 1 < sizeof(g_py)) {
      g_py[n] = txt[0];
      g_py[n + 1] = '\0';
      g_ime_page = 0;
      refresh_cands();
    }
    return;
  }
  if (txt[0] >= 'A' && txt[0] <= 'Z' && txt[1] == '\0') {
    n = strlen(g_py);
    if (n + 1 < sizeof(g_py)) {
      g_py[n] = (char)tolower((int)txt[0]);
      g_py[n + 1] = '\0';
      g_ime_page = 0;
      refresh_cands();
    }
    return;
  }
}

static void kb_event(lv_event_t *e)
{
  lv_event_code_t code = lv_event_get_code(e);
  uint32_t id;
  const char *txt;

  if (code == LV_EVENT_READY || code == LV_EVENT_CANCEL) {
    hide_kb();
    return;
  }
  if (code != LV_EVENT_VALUE_CHANGED || !g_zh) {
    return;
  }
  id = lv_buttonmatrix_get_selected_button(g_kb);
  txt = lv_buttonmatrix_get_button_text(g_kb, id);
  handle_zh_key(txt);
}

static void send_clicked(lv_event_t *e)
{
  (void)e;
  send_from_ta();
}

static void chip_clicked(lv_event_t *e)
{
  start_ask((const char *)lv_event_get_user_data(e));
}

static void ta_clicked(lv_event_t *e)
{
  (void)e;
  show_kb();
}

static void hide_kb_event(lv_event_t *e)
{
  (void)e;
  hide_kb();
}

static void go_warn_clicked(lv_event_t *e)
{
  (void)e;
  hide_kb();
  ew_ui_goto(EW_PAGE_WARN);
}

static void lang_clicked(lv_event_t *e)
{
  lv_obj_t *lab;

  (void)e;
  g_zh = !g_zh;
  g_py[0] = '\0';
  lab = lv_obj_get_child(g_lang_btn, 0);
  if (lab != NULL) {
    lv_label_set_text(lab, g_zh ? "ZH" : "EN");
  }
  if (g_zh) {
    lv_keyboard_set_textarea(g_kb, NULL);
    if (g_ime_bar != NULL) {
      lv_obj_clear_flag(g_ime_bar, LV_OBJ_FLAG_HIDDEN);
    }
    refresh_cands();
  } else {
    lv_keyboard_set_textarea(g_kb, g_ta);
    if (g_ime_bar != NULL) {
      lv_obj_add_flag(g_ime_bar, LV_OBJ_FLAG_HIDDEN);
    }
  }
  show_kb();
}

typedef struct {
  uint16_t code;
  char plain;
  char shift;
} ew_key_t;

static char hw_key_char(uint32_t code)
{
  static const ew_key_t map[] = {
    {KEY_A, 'a', 'A'}, {KEY_B, 'b', 'B'}, {KEY_C, 'c', 'C'},
    {KEY_D, 'd', 'D'}, {KEY_E, 'e', 'E'}, {KEY_F, 'f', 'F'},
    {KEY_G, 'g', 'G'}, {KEY_H, 'h', 'H'}, {KEY_I, 'i', 'I'},
    {KEY_J, 'j', 'J'}, {KEY_K, 'k', 'K'}, {KEY_L, 'l', 'L'},
    {KEY_M, 'm', 'M'}, {KEY_N, 'n', 'N'}, {KEY_O, 'o', 'O'},
    {KEY_P, 'p', 'P'}, {KEY_Q, 'q', 'Q'}, {KEY_R, 'r', 'R'},
    {KEY_S, 's', 'S'}, {KEY_T, 't', 'T'}, {KEY_U, 'u', 'U'},
    {KEY_V, 'v', 'V'}, {KEY_W, 'w', 'W'}, {KEY_X, 'x', 'X'},
    {KEY_Y, 'y', 'Y'}, {KEY_Z, 'z', 'Z'},
    {KEY_1, '1', '!'}, {KEY_2, '2', '@'}, {KEY_3, '3', '#'},
    {KEY_4, '4', '$'}, {KEY_5, '5', '%'}, {KEY_6, '6', '^'},
    {KEY_7, '7', '&'}, {KEY_8, '8', '*'}, {KEY_9, '9', '('},
    {KEY_0, '0', ')'},
    {KEY_MINUS, '-', '_'}, {KEY_EQUAL, '=', '+'},
    {KEY_LEFTBRACE, '[', '{'}, {KEY_RIGHTBRACE, ']', '}'},
    {KEY_SEMICOLON, ';', ':'}, {KEY_APOSTROPHE, '\'', '"'},
    {KEY_GRAVE, '`', '~'}, {KEY_BACKSLASH, '\\', '|'},
    {KEY_COMMA, ',', '<'}, {KEY_DOT, '.', '>'},
    {KEY_SLASH, '/', '?'}, {KEY_SPACE, ' ', ' '},
    {0, 0, 0}
  };
  int i;

  for (i = 0; map[i].code != 0; i++) {
    if (map[i].code == code) {
      return g_shift ? map[i].shift : map[i].plain;
    }
  }
  return 0;
}

static void hw_kbd_open(void)
{
  if (g_kbd_fd >= 0) {
    return;
  }
  g_kbd_fd = open("/dev/kbd0", O_RDONLY | O_NONBLOCK);
  if (g_kbd_fd < 0) {
    printf("[ew-chat] no /dev/kbd0 (PC keyboard off)\n");
  } else {
    printf("[ew-chat] PC keyboard /dev/kbd0\n");
  }
}

static void hw_kbd_press_chat(uint32_t code)
{
  char ch;
  char one[2];

  if (code == KEY_LEFTSHIFT || code == KEY_RIGHTSHIFT) {
    g_shift = 1;
    return;
  }
  if (code == KEYCODE_BACKDEL || code == KEY_BACKSPACE ||
      code == KEYCODE_FWDDEL) {
    if (g_zh) {
      handle_zh_key(LV_SYMBOL_BACKSPACE);
    } else if (g_ta != NULL) {
      lv_textarea_delete_char(g_ta);
    }
    return;
  }
  if (code == KEYCODE_ENTER || code == KEY_ENTER) {
    if (g_zh) {
      handle_zh_key(LV_SYMBOL_OK);
    } else {
      send_from_ta();
    }
    return;
  }
  if (code == KEY_ESC) {
    hide_kb();
    ew_ui_goto(EW_PAGE_WARN);
    return;
  }
  if (code == KEY_TAB) {
    g_zh = !g_zh;
    g_py[0] = '\0';
    if (g_lang_btn != NULL) {
      lv_obj_t *lab = lv_obj_get_child(g_lang_btn, 0);
      if (lab != NULL) {
        lv_label_set_text(lab, g_zh ? "ZH" : "EN");
      }
    }
    if (g_zh) {
      if (g_kb != NULL) {
        lv_keyboard_set_textarea(g_kb, NULL);
      }
      if (g_ime_bar != NULL) {
        lv_obj_clear_flag(g_ime_bar, LV_OBJ_FLAG_HIDDEN);
      }
      refresh_cands();
    } else {
      if (g_kb != NULL) {
        lv_keyboard_set_textarea(g_kb, g_ta);
      }
      if (g_ime_bar != NULL) {
        lv_obj_add_flag(g_ime_bar, LV_OBJ_FLAG_HIDDEN);
      }
    }
    hide_kb();
    if (g_zh && g_ime_bar != NULL) {
      lv_obj_clear_flag(g_ime_bar, LV_OBJ_FLAG_HIDDEN);
    }
    return;
  }
  if (g_zh && code >= KEY_1 && code <= KEY_5) {
    int idx = (int)(code - KEY_1);
    if (g_cands[idx] != NULL &&
        !lv_obj_has_flag(g_cands[idx], LV_OBJ_FLAG_HIDDEN)) {
      commit_zh_idx(idx);
      return;
    }
  }
  if (code == KEY_F2) {
    more_clicked(NULL);
    return;
  }

  ch = hw_key_char(code);
  if (ch == 0) {
    return;
  }
  if (g_zh && g_ime_bar != NULL) {
    lv_obj_clear_flag(g_ime_bar, LV_OBJ_FLAG_HIDDEN);
  }
  if (g_zh) {
    one[0] = ch;
    one[1] = '\0';
    handle_zh_key(one);
  } else if (g_ta != NULL) {
    one[0] = ch;
    one[1] = '\0';
    lv_textarea_add_text(g_ta, one);
  }
}

static void hw_kbd_poll(void)
{
  struct keyboard_event_s ev;
  ssize_t n;

  if (g_kbd_fd < 0) {
    return;
  }
  for (;;) {
    n = read(g_kbd_fd, &ev, sizeof(ev));
    if (n != (ssize_t)sizeof(ev)) {
      break;
    }
    if (ev.type == KEYBOARD_RELEASE) {
      if (ev.code == KEY_LEFTSHIFT || ev.code == KEY_RIGHTSHIFT) {
        g_shift = 0;
      }
      continue;
    }
    if (ev.type != KEYBOARD_PRESS) {
      continue;
    }
    if (g_page == EW_PAGE_CHAT) {
      hw_kbd_press_chat(ev.code);
    }
  }
}

static void add_chip(lv_obj_t *row, const char *label)
{
  lv_obj_t *btn = lv_button_create(row);
  lv_obj_t *lab = lv_label_create(btn);

  apply_font(lab);
  lv_label_set_text(lab, label);
  lv_obj_center(lab);
  lv_obj_set_style_bg_color(btn, lv_color_hex(0x3D4F7C), 0);
  lv_obj_add_event_cb(btn, chip_clicked, LV_EVENT_CLICKED, (void *)label);
}

static void build_ui(void)
{
  lv_obj_t *title;
  lv_obj_t *chips;
  lv_obj_t *bar;
  lv_obj_t *send;
  lv_obj_t *send_lab;
  lv_obj_t *lang_lab;
  int i;

  g_scr = lv_screen_active();
  lv_obj_set_style_bg_color(g_scr, lv_color_hex(0x082060), 0);
  lv_obj_set_style_bg_opa(g_scr, LV_OPA_COVER, 0);
  lv_obj_set_flex_flow(g_scr, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_all(g_scr, 10, 0);
  lv_obj_set_style_pad_row(g_scr, 6, 0);

  {
    lv_obj_t *head = lv_obj_create(g_scr);
    lv_obj_t *back;
    lv_obj_t *back_lab;

    lv_obj_set_width(head, lv_pct(100));
    lv_obj_set_height(head, LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(head, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(head, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_bg_opa(head, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(head, 0, 0);
    lv_obj_set_style_pad_all(head, 0, 0);

    back = lv_button_create(head);
    lv_obj_set_size(back, EW_UI_NAV_BTN_W, EW_UI_NAV_BTN_H);
    back_lab = lv_label_create(back);
    apply_font(back_lab);
    lv_label_set_text(back_lab, g_font != NULL ? "预警" : "Warn");
    lv_obj_center(back_lab);
    lv_obj_set_style_bg_color(back, lv_color_hex(0xC45C26), 0);
    lv_obj_add_event_cb(back, go_warn_clicked, LV_EVENT_CLICKED, NULL);

    title = lv_label_create(head);
    apply_font(title);
    lv_label_set_text(title, "Edge Walker  /  Agent");
    lv_obj_set_style_text_color(title, lv_color_white(), 0);
    lv_obj_add_flag(title, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(title, hide_kb_event, LV_EVENT_CLICKED, NULL);
  }

  g_status = lv_label_create(g_scr);
  apply_font(g_status);
  lv_label_set_text(g_status,
                    g_font != NULL
                      ? "PC键盘输入+回车发送 | Tab中英 | Esc预警 | 1-5选字"
                      : "PC keys + Enter | Tab ZH/EN | Esc=Warn");
  lv_obj_set_style_text_color(g_status, lv_color_hex(0xB8C8E8), 0);
  lv_obj_add_flag(g_status, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(g_status, hide_kb_event, LV_EVENT_CLICKED, NULL);

  g_list = lv_obj_create(g_scr);
  lv_obj_set_width(g_list, lv_pct(100));
  lv_obj_set_flex_grow(g_list, 1);
  lv_obj_set_flex_flow(g_list, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_bg_color(g_list, lv_color_hex(0x06143A), 0);
  lv_obj_set_style_border_width(g_list, 0, 0);
  lv_obj_set_style_pad_row(g_list, 8, 0);
  lv_obj_set_scroll_dir(g_list, LV_DIR_VER);
  lv_obj_add_flag(g_list, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(g_list, hide_kb_event, LV_EVENT_CLICKED, NULL);

  add_bubble(g_font != NULL
               ? "点模拟器窗口后用电脑键盘打字，回车发送。Tab 切中/英。Esc 回预警。无语音。"
               : "Focus the emulator, type on the PC keyboard, Enter to send. Tab=ZH/EN. Esc=Warn.",
             false);

  chips = lv_obj_create(g_scr);
  lv_obj_set_width(chips, lv_pct(100));
  lv_obj_set_height(chips, LV_SIZE_CONTENT);
  lv_obj_set_flex_flow(chips, LV_FLEX_FLOW_ROW_WRAP);
  lv_obj_set_style_bg_opa(chips, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(chips, 0, 0);
  lv_obj_set_style_pad_all(chips, 0, 0);
  if (g_font != NULL) {
    add_chip(chips, "你是谁");
    add_chip(chips, "告警怎么工作");
    add_chip(chips, "你好");
  }
  add_chip(chips, "Who are you?");
  add_chip(chips, "How does alert work?");
  add_chip(chips, "Hello");

  bar = lv_obj_create(g_scr);
  lv_obj_set_width(bar, lv_pct(100));
  lv_obj_set_height(bar, LV_SIZE_CONTENT);
  lv_obj_set_flex_flow(bar, LV_FLEX_FLOW_ROW);
  lv_obj_set_style_bg_opa(bar, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(bar, 0, 0);
  lv_obj_set_style_pad_all(bar, 0, 0);

  g_lang_btn = lv_button_create(bar);
  lang_lab = lv_label_create(g_lang_btn);
  apply_font(lang_lab);
  lv_label_set_text(lang_lab, "EN");
  lv_obj_center(lang_lab);
  lv_obj_set_style_bg_color(g_lang_btn, lv_color_hex(0x5A3D7C), 0);
  lv_obj_add_event_cb(g_lang_btn, lang_clicked, LV_EVENT_CLICKED, NULL);

  g_ta = lv_textarea_create(bar);
  apply_font(g_ta);
  lv_obj_set_flex_grow(g_ta, 1);
  lv_textarea_set_one_line(g_ta, true);
  lv_textarea_set_placeholder_text(g_ta, "tap here to type");
  lv_textarea_set_max_length(g_ta, 200);
  lv_obj_add_event_cb(g_ta, ta_clicked, LV_EVENT_CLICKED, NULL);
  lv_obj_add_event_cb(g_ta, send_clicked, LV_EVENT_READY, NULL);

  send = lv_button_create(bar);
  send_lab = lv_label_create(send);
  apply_font(send_lab);
  lv_label_set_text(send_lab, "Send");
  lv_obj_center(send_lab);
  lv_obj_set_style_bg_color(send, lv_color_hex(0x2B7DE9), 0);
  lv_obj_add_event_cb(send, send_clicked, LV_EVENT_CLICKED, NULL);

  g_ime_bar = lv_obj_create(g_scr);
  lv_obj_set_width(g_ime_bar, lv_pct(100));
  lv_obj_set_height(g_ime_bar, LV_SIZE_CONTENT);
  lv_obj_set_flex_flow(g_ime_bar, LV_FLEX_FLOW_ROW);
  lv_obj_set_style_bg_color(g_ime_bar, lv_color_hex(0x1A2040), 0);
  lv_obj_set_style_border_width(g_ime_bar, 0, 0);
  lv_obj_set_style_pad_all(g_ime_bar, 4, 0);
  g_py_lab = lv_label_create(g_ime_bar);
  apply_font(g_py_lab);
  lv_label_set_text(g_py_lab, "py: _");
  lv_obj_set_style_text_color(g_py_lab, lv_color_hex(0xC8D8F0), 0);
  for (i = 0; i < 5; i++) {
    g_cands[i] = lv_button_create(g_ime_bar);
    apply_font(lv_label_create(g_cands[i]));
    lv_label_set_text(lv_obj_get_child(g_cands[i], 0), "");
    lv_obj_add_event_cb(g_cands[i], cand_clicked, LV_EVENT_CLICKED, NULL);
    lv_obj_add_flag(g_cands[i], LV_OBJ_FLAG_HIDDEN);
  }
  g_more_btn = lv_button_create(g_ime_bar);
  apply_font(lv_label_create(g_more_btn));
  lv_label_set_text(lv_obj_get_child(g_more_btn, 0), ">");
  lv_obj_add_event_cb(g_more_btn, more_clicked, LV_EVENT_CLICKED, NULL);
  lv_obj_add_flag(g_more_btn, LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_flag(g_ime_bar, LV_OBJ_FLAG_HIDDEN);

  g_kb = lv_keyboard_create(g_scr);
  lv_obj_set_style_pad_left(g_kb, 12, 0);
  lv_obj_set_style_pad_right(g_kb, 12, 0);
  lv_obj_set_style_pad_bottom(g_kb, 8, 0);
  lv_obj_remove_flag(g_kb, LV_OBJ_FLAG_SCROLLABLE);
  lv_keyboard_set_textarea(g_kb, g_ta);
  lv_obj_add_event_cb(g_kb, kb_event, LV_EVENT_ALL, NULL);
  if (g_font != NULL) {
    g_zh = true;
    if (lang_lab != NULL) {
      lv_label_set_text(lang_lab, "ZH");
    }
    lv_keyboard_set_textarea(g_kb, NULL);
  }
  hide_kb();
}

static void poll_reply(void)
{
  if (!g_reply_ready) {
    return;
  }
  g_reply_ready = 0;
  g_busy = 0;
  sanitize_reply(g_reply);
  if (g_wait_bubble != NULL) {
    lv_obj_delete(g_wait_bubble);
    g_wait_bubble = NULL;
  }
  add_bubble(g_reply[0] != '\0' ? g_reply : "(empty)", false);
  if (g_status != NULL) {
    lv_label_set_text(g_status,
                      g_font != NULL
                        ? "PC键盘输入+回车发送 | Tab中英 | Esc预警 | 1-5选字"
                        : "PC keys + Enter | Tab ZH/EN | Esc=Warn");
  }
}

#endif
#endif

void ew_chat_run(void)
{
#ifdef __NuttX__
#ifdef CONFIG_LV_USE_NUTTX
  lv_nuttx_dsc_t info;
  lv_nuttx_result_t result;

  printf("[ew-chat] enter\n");
  fflush(stdout);
  if (lv_is_initialized()) {
    printf("[ew-chat] LVGL already initialized, abort\n");
    return;
  }

  boardctl(BOARDIOC_INIT, 0);
  usleep(200000);
  lv_init();
  lv_nuttx_dsc_init(&info);
#ifdef CONFIG_LV_USE_NUTTX_LCD
  info.fb_path = "/dev/lcd0";
#endif
#ifdef CONFIG_INPUT_TOUCHSCREEN
  info.input_path = "/dev/input0";
#endif
  lv_nuttx_init(&info, &result);
  if (result.disp == NULL) {
    printf("[ew-chat] lv_nuttx_init failed\n");
    return;
  }

  printf("[ew-chat] UI ready, warn/chat loop\n");
  fflush(stdout);
  ew_ui_loop(1);
#else
  printf("[ew-chat] CONFIG_LV_USE_NUTTX not set\n");
#endif
#else
  printf("[ew-chat] host stub\n");
#endif
}

void ew_ui_goto(ew_page_t page)
{
#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)
  g_page_pending = page;
#else
  (void)page;
#endif
}

ew_page_t ew_ui_page(void)
{
#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)
  return g_page;
#else
  return EW_PAGE_WARN;
#endif
}

void *ew_ui_font(void)
{
#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)
  return g_font;
#else
  return NULL;
#endif
}

#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)

/* 三个页面共用一份 CJK 字体，从 boot 和 `ew chat` 进来都要先走这里 */
static void ui_font_init(void)
{
#if LV_USE_FREETYPE
  int w;

  if (g_font != NULL) {
    return;
  }
  /* rcS 可能早于 adb push 完整 TTF，等一会儿，但别把开机拖太久 */
  for (w = 0; w < 10 && !font_ready(g_font_paths[0]); w++) {
    usleep(500000);
  }
  g_font = try_cjk_font(18);
#endif
}

static void chat_page_build(void)
{
  g_scr = NULL;
  g_status = NULL;
  g_list = NULL;
  g_ta = NULL;
  g_kb = NULL;
  g_ime_bar = NULL;
  g_more_btn = NULL;
  g_ime_page = 0;
  g_wait_bubble = NULL;
  g_busy = 0;
  g_reply_ready = 0;
  build_ui();
}

static void page_build(ew_page_t page)
{
  switch (page) {
    case EW_PAGE_CHAT:
      chat_page_build();
      break;
    case EW_PAGE_WIFI:
      ew_wifi_ui_build();
      break;
    default:
      alert_lcd_attach_warn_ui();
      break;
  }
}

static void page_tick(ew_page_t page)
{
  switch (page) {
    case EW_PAGE_CHAT:
      poll_reply();
      break;
    case EW_PAGE_WIFI:
      ew_wifi_ui_tick();
      break;
    default:
      alert_lcd_warn_tick();
      break;
  }
}

static void page_teardown(ew_page_t page)
{
  switch (page) {
    case EW_PAGE_CHAT:
      hide_kb();
      break;
    case EW_PAGE_WIFI:
      ew_wifi_ui_teardown();
      break;
    default:
      alert_lcd_detach_warn_ui();
      break;
  }
}

/* 一帧：喂硬件按键、跑当前页逻辑、刷 LVGL */
static void page_pump(void)
{
  uint32_t idle;

  hw_kbd_poll();
  ew_serial_ctl_poll();
  ew_mirror_tick();
  page_tick(g_page);
  idle = lv_timer_handler();
  if (idle == 0 || idle > EW_UI_FRAME_MS) {
    idle = EW_UI_FRAME_MS;
  }
  usleep(idle * 1000);
}

#endif /* __NuttX__ && CONFIG_LV_USE_NUTTX */

void ew_ui_loop(int start_in_chat)
{
#if defined(__NuttX__) && defined(CONFIG_LV_USE_NUTTX)
  if (!lv_is_initialized()) {
    printf("[ew-ui] LVGL not initialized\n");
    return;
  }
  ui_font_init();
  ew_agent_init();
  ew_serial_ctl_start();
  hw_kbd_open();
  g_page = start_in_chat ? EW_PAGE_CHAT : EW_PAGE_WARN;

  for (;;) {
    uint32_t gate;

    lv_obj_clean(lv_screen_active());
    page_build(g_page);
    lv_indev_reset(NULL, NULL);
    printf("[ew-ui] page=%d\n", (int)g_page);
    fflush(stdout);

    gate = lv_tick_get();
    g_page_pending = g_page;
    while (lv_tick_elaps(gate) < EW_UI_GATE_MS) {
      page_pump();
    }

    /* 门限期内的误触不算数，从这里才开始接受切页 */
    g_page_pending = g_page;
    while (g_page_pending == g_page) {
      page_pump();
    }

    page_teardown(g_page);
    g_page = g_page_pending;
  }
#else
  (void)start_in_chat;
#endif
}
