/****************************************************************************
 * LD2451 解析 + 端侧 policy（F · 王筠昊）
 *
 * 帧格式对齐 HLK 串口协议 V1.03：
 *   头 F4 F3 F2 F1 | 长度(LE,2B) | 体 | 尾 F8 F7 F6 F5
 * 体：目标数(1) + 报警(1) + N×(角/距/方向/速度/SNR 各 1B)
 *
 * 告警接口（改名须三人同意）：
 *   alert_level: NONE | SOFT | STRONG | EMERGENCY
 ****************************************************************************/

#ifndef EDGE_WALKER_LD2451_H
#define EDGE_WALKER_LD2451_H

#include "alert_output.h"

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EW_LD2451_HDR0 0xF4
#define EW_LD2451_HDR1 0xF3
#define EW_LD2451_HDR2 0xF2
#define EW_LD2451_HDR3 0xF1
#define EW_LD2451_TAIL0 0xF8
#define EW_LD2451_TAIL1 0xF7
#define EW_LD2451_TAIL2 0xF6
#define EW_LD2451_TAIL3 0xF5

#define EW_LD2451_MAX_TARGETS 5

/* 雷达串口，全工程唯一定义 */
#ifndef EW_RADAR_DEV
#define EW_RADAR_DEV "/dev/ttyS1"
#endif

/* 台架初值（可后调） */
#ifndef EW_MIN_SPEED_KMH
#define EW_MIN_SPEED_KMH 5.0f
#endif
#ifndef EW_MIN_SNR
#define EW_MIN_SNR 8.0f
#endif
#ifndef EW_RANGE_SOFT_M
#define EW_RANGE_SOFT_M 25.0f
#endif
#ifndef EW_RANGE_STRONG_M
#define EW_RANGE_STRONG_M 15.0f
#endif
#ifndef EW_RANGE_EMERGENCY_M
#define EW_RANGE_EMERGENCY_M 8.0f
#endif
#ifndef EW_TTC_SOFT_S
#define EW_TTC_SOFT_S 5.0f
#endif
#ifndef EW_TTC_STRONG_S
#define EW_TTC_STRONG_S 3.0f
#endif
#ifndef EW_TTC_EMERGENCY_S
#define EW_TTC_EMERGENCY_S 1.5f
#endif
#ifndef EW_CONFIRM_FRAMES
#define EW_CONFIRM_FRAMES 1
#endif
#ifndef EW_CLEAR_MS
#define EW_CLEAR_MS 1000u
#endif
#ifndef EW_LINK_STALE_MS
#define EW_LINK_STALE_MS 1500u
#endif

/*
 * 方向字节：官方表写 01=靠近 / 00=远离，但 V1.03 示例解析为
 * 00=靠近 / 01=远离。默认跟示例；台架若反了可 -DEW_DIR_APPROACH=0x01。
 */
#ifndef EW_DIR_APPROACH
#define EW_DIR_APPROACH 0x00
#endif
#ifndef EW_DIR_AWAY
#define EW_DIR_AWAY 0x01
#endif

typedef struct {
  float range_m;
  float speed_kmh;
  float azimuth_deg;
  float snr;
  float ttc_s; /* <0 表示无效 */
  bool radar_alarm; /* 帧级报警位：与 HLK 手机 App 同源 */
  bool approaching;
  bool valid;
} ew_track_t;

typedef enum {
  EW_LINK_DEAD = 0,  /* 近期无 UART 字节 */
  EW_LINK_NOISE = 1, /* 有字节但无完整帧 */
  EW_LINK_OK = 2     /* 近期有完整帧 */
} ew_link_t;

typedef struct {
  ew_alert_level_t level;
  float range_m;
  float speed_kmh;
  float azimuth_deg;
  float ttc_s;
  bool approaching;
  const char *reason;
  ew_link_t link;
} ew_decision_t;

typedef struct {
  ew_alert_level_t pending;
  uint8_t pending_hits;
  ew_alert_level_t latched;
  uint32_t last_byte_ms;
  uint32_t last_frame_ms;
  uint32_t last_alert_ms;
  ew_link_t link;
  bool ever_bytes;
  bool ever_frame;
} ew_hold_t;

/* 链路嗅探计数：区分「没接到线」vs「接到了但没靠近目标」。 */
typedef struct {
  uint32_t bytes_in;       /* 读到的原始字节 */
  uint32_t headers;        /* 看到完整帧头 F4 F3 F2 F1 */
  uint32_t frames_ok;      /* 头+体+尾完整 */
  uint32_t frames_bad;     /* 头对上但尾校验失败 */
  uint32_t frames_empty;   /* 完整帧且目标数=0（或无可解析体） */
  uint32_t frames_targets; /* 完整帧且目标数>0 */
  uint32_t approaching;    /* 通过只靠近+最小速度过滤 */
} ew_sniff_stats_t;

/* 喂入原始字节流；凑齐一帧并选出有效目标则返回 true。 */
bool ew_ld2451_feed(const uint8_t *data, unsigned len, ew_track_t *out);

/*
 * 同 feed，并累加 sniff 统计。st / out 均可为 NULL。
 * 有完整帧时 frames_* 会增加；有靠近目标时返回 true 并写 out。
 */
bool ew_ld2451_feed_sniff(const uint8_t *data, unsigned len,
                          ew_sniff_stats_t *st, ew_track_t *out);

/* 重置帧状态机（换源 / 重连时调用）。 */
void ew_ld2451_reset(void);

/* 端侧门限：只靠近 + 最小速度 + SNR + 距离/TTC → 四级告警。不用 LLM。 */
ew_decision_t ew_decide(const ew_track_t *track);

/* 跨帧保持：连续确认才上告警，空场超时回 NONE。now_ms 用单调时钟。 */
void ew_hold_reset(ew_hold_t *h);
ew_decision_t ew_hold_update(ew_hold_t *h, uint32_t now_ms,
                             bool had_bytes, bool had_frame,
                             const ew_track_t *track);

/* 等级名，供日志 / 主机冒烟。 */
const char *ew_alert_level_name(ew_alert_level_t level);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_LD2451_H */
