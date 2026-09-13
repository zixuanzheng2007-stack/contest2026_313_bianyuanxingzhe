/****************************************************************************
 * UI 运行时串口 @ 远程控制（PC 面板 / 虚拟遥控，无需 NSH 提示符）
 *
 * 行格式：@goto wifi / @fake 10 20 / @join SSID pass / @tap 195 225
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_SERIAL_CTL_H
#define EDGE_WALKER_EW_SERIAL_CTL_H

#ifdef __cplusplus
extern "C" {
#endif

void ew_serial_ctl_start(void);
void ew_serial_ctl_poll(void);

#ifdef __cplusplus
}
#endif

#endif /* EDGE_WALKER_EW_SERIAL_CTL_H */
