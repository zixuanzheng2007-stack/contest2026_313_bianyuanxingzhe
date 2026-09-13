/****************************************************************************
 * ai_agent 进程侧 Tool approach_alert（IPC 版）
 *
 * ai_agent 与 ew 是不同 NuttX 应用；此处通过 /data/ew_alert.req 通知
 * 常驻 ew boot UI，并打印与 alert_output 一致的日志行供串口验收。
 * 编译进 packages/ai_agent（由 sync_and_build.sh 注入）。
 ****************************************************************************/

#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>

#define EW_ALERT_REQ "/data/ew_alert.req"

static const char *level_name(int level)
{
  switch (level) {
    case 1: return "SOFT";
    case 2: return "STRONG";
    case 3: return "EMERGENCY";
    default: return "NONE";
  }
}

static int level_from_json(const char *input_json, int *level_out,
                           char *reason, unsigned reason_sz)
{
  const char *p;
  char buf[16];

  *level_out = 0;
  if (reason != NULL && reason_sz > 0) {
    reason[0] = '\0';
  }
  if (input_json == NULL) {
    return 0;
  }

  p = strstr(input_json, "\"level\"");
  if (p != NULL) {
    p = strchr(p, ':');
    if (p != NULL) {
      unsigned i = 0;

      p++;
      while (*p == ' ' || *p == '\t') {
        p++;
      }
      if (*p == '"') {
        p++;
        while (*p != '\0' && *p != '"' && i + 1 < sizeof(buf)) {
          buf[i++] = *p++;
        }
        buf[i] = '\0';
        if (strcmp(buf, "soft") == 0 || strcmp(buf, "SOFT") == 0 ||
            strcmp(buf, "1") == 0) {
          *level_out = 1;
        } else if (strcmp(buf, "strong") == 0 || strcmp(buf, "STRONG") == 0 ||
                   strcmp(buf, "2") == 0) {
          *level_out = 2;
        } else if (strcmp(buf, "emergency") == 0 ||
                   strcmp(buf, "EMERGENCY") == 0 ||
                   strcmp(buf, "crit") == 0 || strcmp(buf, "3") == 0) {
          *level_out = 3;
        } else {
          *level_out = 0;
        }
      }
    }
  }

  p = strstr(input_json, "\"reason\"");
  if (p != NULL && reason != NULL && reason_sz > 0) {
    p = strchr(p, ':');
    if (p != NULL) {
      unsigned o = 0;

      p++;
      while (*p == ' ' || *p == '\t') {
        p++;
      }
      if (*p == '"') {
        p++;
        while (*p != '\0' && *p != '"' && o + 1 < reason_sz) {
          if (*p == '\\' && p[1] != '\0') {
            p++;
          }
          reason[o++] = *p++;
        }
        reason[o] = '\0';
      }
    }
  }
  return 0;
}

static void queue_alert(int level, const char *reason)
{
  char line[96];
  int fd;

  snprintf(line, sizeof(line), "%d %s\n", level, reason ? reason : "");
  fd = open(EW_ALERT_REQ, O_WRONLY | O_CREAT | O_TRUNC, 0666);
  if (fd < 0) {
    return;
  }
  (void)write(fd, line, strlen(line));
  close(fd);
}

int tool_approach_alert_execute(const char *input_json, char *output,
                                size_t output_size)
{
  int level = 0;
  char reason[64];

  level_from_json(input_json, &level, reason, sizeof(reason));

  printf("[ai_agent] tool approach_alert level=%s reason=%s\n",
         level_name(level), reason);
  printf("[alert_output] level=%s reason=%s\n", level_name(level), reason);
  fflush(stdout);

  queue_alert(level, reason);

  if (output != NULL && output_size > 0) {
    snprintf(output, output_size,
             "{\"ok\":true,\"tool\":\"approach_alert\",\"level\":\"%s\","
             "\"reason\":\"%s\"}",
             level_name(level), reason);
  }
  return 0;
}
