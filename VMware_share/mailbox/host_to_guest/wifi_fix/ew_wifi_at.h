/****************************************************************************
 * 外挂 ESP AT 猫（PA24/PA25 → /dev/ttyS2 @115200）
 *
 * 凭证只在运行时保存到 EW_WIFI_CONF，不做编译期硬编码。
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_WIFI_AT_H
#define EDGE_WALKER_EW_WIFI_AT_H

#ifdef __cplusplus
extern "C" {
#endif

#ifndef EW_WIFI_AT_DEV
#define EW_WIFI_AT_DEV "/dev/ttyS2"
#endif

#ifndef EW_WIFI_CONF
#define EW_WIFI_CONF "/data/ew_wifi.conf"
#endif

#define EW_WIFI_SSID_MAX 33
#define EW_WIFI_PASS_MAX 65
#define EW_WIFI_SCAN_MAX 24

/* 短状态串（屏上一行）最小长度 */
#define EW_WIFI_STAT_MAX 40

typedef enum {
  EW_WIFI_DOWN = 0,   /* 模组不回 AT */
  EW_WIFI_IDLE,       /* AT 通，未连 AP */
  EW_WIFI_JOINED,     /* 已连 AP 并拿到 IP */
  EW_WIFI_ONLINE      /* 已连且公网可达 */
} ew_wifi_state_t;

typedef struct {
  char ssid[EW_WIFI_SSID_MAX];
  int rssi;           /* dBm，越大越好 */
  int open;           /* 1 = 无需密码 */
} ew_wifi_ap_t;

/* ---- 基础 AT ---- */

int ew_wifi_at_ping(void);
int ew_wifi_at_cmd(const char *at_line);

/* 打印 CWJAP? / CIFSR 到控制台，返回 0 = 都成功 */
int ew_wifi_at_status(void);

/* ---- 连接管理 ---- */

/* 查询当前状态；ip 可为 NULL。check_inet=1 时额外做一次公网 PING。 */
ew_wifi_state_t ew_wifi_probe(int check_inet, char *ip, unsigned ip_sz);

/* 开机上线：模组自连优先，否则用 EW_WIFI_CONF 的凭证。
 * out 写屏上短状态（WIFI ON / WIFI LAN / NO WIFI / AT FAIL）。
 */
int ew_wifi_bringup(char *out, unsigned out_sz);

/* 扫描周边 AP，按 RSSI 降序去重，返回条数，<0 为失败。约需 5 s。 */
int ew_wifi_scan(ew_wifi_ap_t *aps, int max);

/* 连接 AP；成功则保存凭证。out 写短状态。约需 15 s。 */
int ew_wifi_join(const char *ssid, const char *pass, char *out, unsigned out_sz);

/* 断开并清除已保存的凭证 */
int ew_wifi_forget(void);

/* 读回已保存的凭证，0 = 有。pass 可为 NULL。 */
int ew_wifi_cred_load(char *ssid, unsigned ssid_sz, char *pass, unsigned pass_sz);

/* ---- 应用层 ---- */

/* ESP AT SSL + HTTP POST。resp 为模组回灌（含 HTTP 头）。成功 0。 */
int ew_wifi_http_ssl_post(const char *host, unsigned port, const char *path,
                          const char *bearer, const char *json_body,
                          char *resp, unsigned resp_sz);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_WIFI_AT_H */
