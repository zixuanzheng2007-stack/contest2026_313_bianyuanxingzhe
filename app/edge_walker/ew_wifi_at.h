#ifndef EDGE_WALKER_EW_WIFI_AT_H
#define EDGE_WALKER_EW_WIFI_AT_H

#ifdef __cplusplus
extern "C" {
#endif

#ifndef EW_WIFI_AT_DEV
#define EW_WIFI_AT_DEV "/dev/ttyS2"
#endif

int ew_wifi_at_ping(void);
int ew_wifi_at_cmd(const char *at_line);
/* 开机：测 AT，若已配置 SSID 则 CWJAP。out 写入屏上短状态（无密码）。 */
int ew_wifi_bringup(char *out, unsigned out_sz);

#ifdef __cplusplus
}
#endif

#endif
