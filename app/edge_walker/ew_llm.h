/* SPDX-License-Identifier: Apache-2.0 */
/* Copyright 2026 Edge Walker Team (contest2026_313_bianyuanxingzhe) */

/****************************************************************************
 * 边缘行者 · 智能体对话（读 /data/ai_agent 配置，HTTPS 调 MiMo）
 ****************************************************************************/

#ifndef EDGE_WALKER_EW_LLM_H
#define EDGE_WALKER_EW_LLM_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
  EW_LLM_OK = 0,
  EW_LLM_ERR_INVALID,
  EW_LLM_ERR_NO_WIFI,
  EW_LLM_ERR_CONFIG,
  EW_LLM_ERR_AUTH,
  EW_LLM_ERR_TLS,
  EW_LLM_ERR_TIMEOUT,
  EW_LLM_ERR_AT_BUSY,
  EW_LLM_ERR_RESPONSE
} ew_llm_result_t;

/* 阻塞调用。reply 写入 out（UTF-8），失败返回可分层的错误码。 */
ew_llm_result_t ew_llm_ask(const char *prompt, char *out, unsigned out_sz);

/* 安全配置 MiMo：仅传入 API key，其余端点使用固件内的官方默认值。 */
int ew_llm_configure_mimo(const char *api_key, char *out, unsigned out_sz);

/* 恢复首次配置前保存的 config.json.bak。 */
int ew_llm_restore_config(char *out, unsigned out_sz);

#ifdef __cplusplus
}
#endif

#endif
