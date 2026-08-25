/****************************************************************************
 * 提醒出口（郑子轩主责；等级枚举与 F 冻结接口对齐）
 *
 * 全队冻结：alert_output(档位, 原因)
 * alert_level: NONE | SOFT | STRONG | EMERGENCY
 ****************************************************************************/

#ifndef EDGE_WALKER_ALERT_OUTPUT_H
#define EDGE_WALKER_ALERT_OUTPUT_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  EW_ALERT_NONE = 0,
  EW_ALERT_SOFT = 1,
  EW_ALERT_STRONG = 2,
  EW_ALERT_EMERGENCY = 3
} ew_alert_level_t;

/* 兼容旧三档命名（逐步淘汰） */
#define EW_ALERT_WARN EW_ALERT_SOFT
#define EW_ALERT_CRIT EW_ALERT_EMERGENCY

/* 档位：0 静音 … 3 紧急。reason 可为 NULL。 */
void alert_output(ew_alert_level_t level, const char *reason);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_ALERT_OUTPUT_H */
