#ifndef EDGE_WALKER_ALERT_BUZZER_H
#define EDGE_WALKER_ALERT_BUZZER_H

#ifdef __cplusplus
extern "C" {
#endif

/* 40P 针 23 = PA28，无源模块 IO，需 2~5 kHz 方波。 */
int alert_buzzer_beep(unsigned freq_hz, unsigned duration_ms);
void alert_buzzer_selftest(void);
void alert_buzzer_stop(void);

#ifdef __cplusplus
}
#endif

#endif
