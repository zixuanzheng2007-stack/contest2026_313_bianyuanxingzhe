/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * 提醒出口（郑子轩主责；等级枚举与 F 冻结接口对齐）
 *
 * 全队冻结：alert_output(档位, 原因)
 ****************************************************************************/

#ifndef EDGE_WALKER_ALERT_OUTPUT_H
#define EDGE_WALKER_ALERT_OUTPUT_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  EW_ALERT_NONE = 0,
  EW_ALERT_SOFT = 1,
  EW_ALERT_STRONG = 2,
  EW_ALERT_EMERGENCY = 3
} ew_alert_level_t;

/* 档位：NONE 静音 … EMERGENCY 紧急。reason 可为 NULL。 */
void alert_output(ew_alert_level_t level, const char *reason);

/* Correlation for the local proactive chain; zero denotes an untraced call. */
void alert_output_event(ew_alert_level_t level, const char *reason,
                        unsigned long event_id);
/* 0 = UI callback, 1 = queued, negative = delivery failed. None of these
 * statuses proves an acoustic or optical measurement. */
int alert_output_event_checked(ew_alert_level_t level, const char *reason,
                               unsigned long event_id, bool safety_owned);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_ALERT_OUTPUT_H */
