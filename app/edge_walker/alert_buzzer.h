/****************************************************************************
 * 蜂鸣器 PA28（40P 针 23）
 *
 * 无源模块要 2~5 kHz 方波，所以预警音由后台 worker 持续输出，
 * 调用方只负责换挡，不要在 UI 线程里死等。
 ****************************************************************************/

#ifndef EDGE_WALKER_ALERT_BUZZER_H
#define EDGE_WALKER_ALERT_BUZZER_H

#include "alert_output.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 同步响一声，用于命令行点测 */
int alert_buzzer_beep(unsigned freq_hz, unsigned duration_ms);

/* 预警换挡：按等级选频率并交给后台 worker；EW_ALERT_NONE 立即停。 */
void alert_buzzer_level(ew_alert_level_t level);

/* 直接指定频率的后台连续鸣叫；freq_hz=0 停止。 */
void alert_buzzer_set_alert(unsigned freq_hz);

void alert_buzzer_selftest(void);
void alert_buzzer_stop(void);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_ALERT_BUZZER_H */
