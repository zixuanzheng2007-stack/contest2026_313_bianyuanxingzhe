#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

int tool_approach_alert_execute(const char *input_json, char *output,
                                size_t output_size);

#ifdef __cplusplus
}
#endif
