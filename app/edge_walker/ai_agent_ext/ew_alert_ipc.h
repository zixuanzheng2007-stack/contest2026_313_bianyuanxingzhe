/* SPDX-License-Identifier: Apache-2.0 */
/* Shared, nonblocking single-slot alert transport and strict Tool input. */
#ifndef EW_ALERT_IPC_H
#define EW_ALERT_IPC_H

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef _WIN32
#include <direct.h>
#endif

#ifndef EW_ALERT_REQ
#define EW_ALERT_REQ "/data/ew_alert.req"
#endif
#define EW_ALERT_SLOT EW_ALERT_REQ ".lock"
#define EW_ALERT_MUTEX EW_ALERT_REQ ".mutex"
#define EW_ALERT_STAGING EW_ALERT_SLOT "/staging"
#define EW_ALERT_PROCESSING EW_ALERT_SLOT "/processing"
#define EW_ALERT_CONSUMER EW_ALERT_SLOT "/consumer"
#define EW_ALERT_ACK_TMP EW_ALERT_SLOT "/ack.tmp"
#define EW_ALERT_ACK EW_ALERT_REQ ".ack"
#define EW_ALERT_RESULT_TMP EW_ALERT_SLOT "/result.tmp"
#define EW_ALERT_RESULT EW_ALERT_REQ ".result"
#define EW_ALERT_REASON_SIZE 96
#define EW_ALERT_WIRE_SIZE 256

typedef struct {
  unsigned long event_id;
  int level;
  char reason[EW_ALERT_REASON_SIZE];
} ew_alert_request_t;

static inline int ew_alert_json_escape(const char *src, char *dst, size_t size)
{
  static const char hex[] = "0123456789abcdef";
  size_t n = 0;
  const unsigned char *p = (const unsigned char *)(src ? src : "");
  if (dst == NULL || size == 0) return -EMSGSIZE;
  for (; *p; p++) {
    size_t needed = *p < 32 ? 6 : (*p == '"' || *p == '\\' ? 2 : 1);
    if (n + needed >= size) { dst[0] = '\0'; return -EMSGSIZE; }
    if (*p < 32) {
      dst[n++] = '\\'; dst[n++] = 'u'; dst[n++] = '0'; dst[n++] = '0';
      dst[n++] = hex[*p >> 4]; dst[n++] = hex[*p & 15];
    } else {
      if (*p == '"' || *p == '\\') dst[n++] = '\\';
      dst[n++] = (char)*p;
    }
  }
  dst[n] = '\0';
  return 0;
}

static inline void ew_alert_json_space(const char **p)
{
  while (**p == ' ' || **p == '\t' || **p == '\r' || **p == '\n') ++*p;
}

static inline int ew_alert_hex(char c)
{
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static inline int ew_alert_json_u16(const char **p, unsigned *value)
{
  int i, h;
  *value = 0;
  for (i = 0; i < 4; i++) {
    h = ew_alert_hex(**p);
    if (h < 0) return -EINVAL;
    *value = (*value << 4) | (unsigned)h;
    ++*p;
  }
  return 0;
}

static inline int ew_alert_json_string(const char **p, char *out, size_t size)
{
  size_t n = 0;
  unsigned cp;
  if (*(*p)++ != '"') return -EINVAL;
  while (**p && **p != '"') {
    unsigned char bytes[4];
    size_t count = 1, i;
    cp = (unsigned char)*(*p)++;
    if (cp < 32) return -EINVAL;
    if (cp == '\\') {
      char escaped = **p;
      if (escaped == '\0') return -EINVAL;
      ++*p;
      switch (escaped) {
        case '"': case '\\': case '/': cp = (unsigned char)escaped; break;
        case 'b': cp = 8; break; case 'f': cp = 12; break;
        case 'n': cp = 10; break; case 'r': cp = 13; break;
        case 't': cp = 9; break;
        case 'u': {
          unsigned low;
          if (ew_alert_json_u16(p, &cp) < 0 || cp == 0) return -EINVAL;
          if (cp >= 0xd800 && cp <= 0xdbff) {
            if (**p != '\\' || (*p)[1] != 'u') return -EINVAL;
            *p += 2;
            if (ew_alert_json_u16(p, &low) < 0 || low < 0xdc00 || low > 0xdfff)
              return -EINVAL;
            cp = 0x10000 + ((cp - 0xd800) << 10) + low - 0xdc00;
          } else if (cp >= 0xdc00 && cp <= 0xdfff) return -EINVAL;
          break;
        }
        default: return -EINVAL;
      }
      if (cp >= 0x10000) {
        count = 4; bytes[0] = (unsigned char)(0xf0 | (cp >> 18));
        bytes[1] = (unsigned char)(0x80 | ((cp >> 12) & 63));
        bytes[2] = (unsigned char)(0x80 | ((cp >> 6) & 63));
        bytes[3] = (unsigned char)(0x80 | (cp & 63));
      } else if (cp >= 0x800) {
        count = 3; bytes[0] = (unsigned char)(0xe0 | (cp >> 12));
        bytes[1] = (unsigned char)(0x80 | ((cp >> 6) & 63));
        bytes[2] = (unsigned char)(0x80 | (cp & 63));
      } else if (cp >= 0x80) {
        count = 2; bytes[0] = (unsigned char)(0xc0 | (cp >> 6));
        bytes[1] = (unsigned char)(0x80 | (cp & 63));
      } else bytes[0] = (unsigned char)cp;
    } else bytes[0] = (unsigned char)cp;
    if (n + count >= size) return -EMSGSIZE;
    for (i = 0; i < count; i++) out[n++] = (char)bytes[i];
  }
  if (**p != '"') return -EINVAL;
  ++*p;
  out[n] = '\0';
  return 0;
}

static inline int ew_alert_json_ulong(const char **p, unsigned long *value)
{
  const char *start = *p;
  unsigned long n = 0;
  if (**p < '0' || **p > '9') return -EINVAL;
  do {
    unsigned digit = (unsigned)(**p - '0');
    if (n > (ULONG_MAX - digit) / 10) return -EINVAL;
    n = n * 10 + digit;
    ++*p;
  } while (**p >= '0' && **p <= '9');
  if (*p - start > 1 && *start == '0') return -EINVAL;
  *value = n;
  return 0;
}

static inline int ew_alert_request_parse_json(const char *json,
                                             ew_alert_request_t *request)
{
  const char *p = json;
  unsigned seen = 0;
  if (json == NULL || request == NULL) return -EINVAL;
  memset(request, 0, sizeof(*request));
  ew_alert_json_space(&p);
  if (*p++ != '{') return -EINVAL;
  ew_alert_json_space(&p);
  while (*p && *p != '}') {
    char key[24], value[24];
    unsigned bit;
    unsigned long number;
    int ret = ew_alert_json_string(&p, key, sizeof(key));
    if (ret < 0) return ret;
    bit = strcmp(key, "level") == 0 ? 1u :
          strcmp(key, "reason") == 0 ? 2u :
          strcmp(key, "event_id") == 0 ? 4u : 0u;
    if (!bit || (seen & bit)) return -EINVAL;
    seen |= bit;
    ew_alert_json_space(&p);
    if (*p++ != ':') return -EINVAL;
    ew_alert_json_space(&p);
    if (bit == 2u) {
      ret = ew_alert_json_string(&p, request->reason, sizeof(request->reason));
    } else if (*p == '"') {
      ret = ew_alert_json_string(&p, value, sizeof(value));
      if (ret < 0) return ret;
      if (bit == 4u) {
        const char *v = value;
        ret = ew_alert_json_ulong(&v, &number);
        if (ret < 0 || *v) return -EINVAL;
        request->event_id = number;
      } else if (!strcmp(value, "none") || !strcmp(value, "NONE") || !strcmp(value, "0")) request->level = 0;
      else if (!strcmp(value, "soft") || !strcmp(value, "SOFT") || !strcmp(value, "1")) request->level = 1;
      else if (!strcmp(value, "strong") || !strcmp(value, "STRONG") || !strcmp(value, "2")) request->level = 2;
      else if (!strcmp(value, "emergency") || !strcmp(value, "EMERGENCY") || !strcmp(value, "crit") || !strcmp(value, "CRIT") || !strcmp(value, "3")) request->level = 3;
      else return -EINVAL;
    } else {
      ret = ew_alert_json_ulong(&p, &number);
      if (ret < 0) return ret;
      if (bit == 1u) {
        if (number > 3) return -EINVAL;
        request->level = (int)number;
      } else request->event_id = number;
    }
    if (ret < 0) return ret;
    ew_alert_json_space(&p);
    if (*p == '}') break;
    if (*p++ != ',') return -EINVAL;
    ew_alert_json_space(&p);
    if (*p == '}') return -EINVAL;
  }
  if (*p++ != '}' || !(seen & 1u)) return -EINVAL;
  ew_alert_json_space(&p);
  return *p ? -EINVAL : 0;
}

/* Never expire locks by age: an unrecorded consumer may still have applied its
 * request. A completed-result marker permits ACK/cleanup retries without apply.
 * A crash before that marker is written (or while holding the mutex) remains
 * fail-closed: stop ew/ai_agent before manual recovery. File operations are not
 * a transaction with a hardware actuator; power-loss exactly-once is not claimed. */
static inline int ew_alert_ipc_mkdir(const char *path)
{
#ifdef _WIN32
  return _mkdir(path);
#else
  return mkdir(path, 0770);
#endif
}

#ifndef EW_ALERT_IPC_WRITE
#define EW_ALERT_IPC_WRITE write
#endif
#ifndef EW_ALERT_IPC_OPEN
#define EW_ALERT_IPC_OPEN open
#endif
#ifndef EW_ALERT_IPC_UNLINK
#define EW_ALERT_IPC_UNLINK unlink
#endif

static inline int ew_alert_ipc_write_file(const char *path,
                                         const char *data, size_t size)
{
  int fd = EW_ALERT_IPC_OPEN(path, O_WRONLY | O_CREAT | O_EXCL, 0660);
  int ret = 0;
  ssize_t n;
  if (fd < 0) return -errno;
  do { n = EW_ALERT_IPC_WRITE(fd, data, size); } while (n < 0 && errno == EINTR);
  if (n < 0) ret = -errno;
  else if ((size_t)n != size) ret = -EIO;
  if (close(fd) < 0 && ret == 0) ret = -errno;
  if (ret < 0) unlink(path);
  return ret;
}

static inline int ew_alert_ipc_encode(const ew_alert_request_t *request,
                                     char *wire, size_t size)
{
  static const char hex[] = "0123456789abcdef";
  size_t i, n, len;
  int written;
  if (request == NULL || request->level < 0 || request->level > 3)
    return -EINVAL;
  for (len = 0; len < sizeof(request->reason) && request->reason[len]; len++);
  if (len == sizeof(request->reason)) return -EMSGSIZE;
  written = snprintf(wire, size, "EWA1 %lu %d ", request->event_id, request->level);
  if (written < 0 || (size_t)written >= size) return -EMSGSIZE;
  n = (size_t)written;
  if (n + len * 2 + 2 > size) return -EMSGSIZE;
  for (i = 0; i < len; i++) {
    unsigned char c = (unsigned char)request->reason[i];
    wire[n++] = hex[c >> 4]; wire[n++] = hex[c & 15];
  }
  wire[n++] = '\n'; wire[n] = '\0';
  return (int)n;
}

static inline int ew_alert_ipc_decode(const char *wire, size_t size,
                                     ew_alert_request_t *request)
{
  const char *p = wire;
  unsigned long level;
  size_t n = 0;
  int a, b;
  memset(request, 0, sizeof(*request));
  if (size < 10 || wire[size - 1] != '\n' ||
      memchr(wire, '\0', size) != NULL || strncmp(p, "EWA1 ", 5))
    return -EINVAL;
  p += 5;
  if (ew_alert_json_ulong(&p, &request->event_id) < 0 || *p++ != ' ' ||
      ew_alert_json_ulong(&p, &level) < 0 || level > 3 || *p++ != ' ')
    return -EINVAL;
  request->level = (int)level;
  while (p < wire + size - 1) {
    if (p + 1 >= wire + size - 1 || n + 1 >= sizeof(request->reason))
      return -EINVAL;
    a = ew_alert_hex(*p++); b = ew_alert_hex(*p++);
    if (a < 0 || b < 0 || (a == 0 && b == 0)) return -EINVAL;
    request->reason[n++] = (char)((a << 4) | b);
  }
  request->reason[n] = '\0';
  return 0;
}

static inline int ew_alert_ipc_publish(const ew_alert_request_t *request)
{
  char wire[EW_ALERT_WIRE_SIZE];
  int ret = ew_alert_ipc_encode(request, wire, sizeof(wire));
  if (ret < 0) return ret;
  if (ew_alert_ipc_mkdir(EW_ALERT_MUTEX) < 0)
    return errno == EEXIST ? -EBUSY : -errno;
  if (ew_alert_ipc_mkdir(EW_ALERT_SLOT) < 0) {
    ret = errno == EEXIST ? -EBUSY : -errno;
    rmdir(EW_ALERT_MUTEX);
    return ret;
  }
  /* An old request without its lock is never silently overwritten. */
  {
    struct stat info;
    if (stat(EW_ALERT_RESULT, &info) == 0) ret = -EBUSY;
    else if (errno != ENOENT) ret = -errno;
    else if (stat(EW_ALERT_REQ, &info) == 0) ret = -EBUSY;
    else if (errno != ENOENT) ret = -errno;
    else if (unlink(EW_ALERT_ACK) < 0 && errno != ENOENT) ret = -errno;
    else ret = ew_alert_ipc_write_file(EW_ALERT_STAGING, wire, (size_t)ret);
  }
  if (ret == 0 && rename(EW_ALERT_STAGING, EW_ALERT_REQ) < 0) ret = -errno;
  if (ret < 0) {
    unlink(EW_ALERT_STAGING);
    rmdir(EW_ALERT_SLOT);
  }
  if (rmdir(EW_ALERT_MUTEX) < 0 && ret == 0) ret = -errno;
  return ret;
}

typedef int (*ew_alert_ipc_apply_fn)(const ew_alert_request_t *, void *);

static inline int ew_alert_ipc_read_file(const char *path, char *data,
                                        size_t capacity)
{
  size_t used = 0;
  ssize_t n;
  int ret = 0;
  int fd = EW_ALERT_IPC_OPEN(path, O_RDONLY);
  if (fd < 0) return -errno;
  do {
    n = read(fd, data + used, capacity - 1 - used);
    if (n > 0) used += (size_t)n;
  } while ((n > 0 && used < capacity - 1) || (n < 0 && errno == EINTR));
  if (n < 0) ret = -errno;
  else if (used >= capacity - 1) ret = -EMSGSIZE;
  if (close(fd) < 0 && ret == 0) ret = -errno;
  data[used] = '\0';
  return ret < 0 ? ret : (int)used;
}

/* The internal completion record is independent of the unchanged EWA1 wire.
 * It stays outside the slot until every slot cleanup step has succeeded. */
static inline int ew_alert_ipc_read_result(unsigned long *event_id, int *result)
{
  char data[96], *end;
  const char *p;
  long number;
  int len = ew_alert_ipc_read_file(EW_ALERT_RESULT, data, sizeof(data));
  if (len < 0) return len;
  if (len < 9 || memchr(data, '\0', (size_t)len) != NULL ||
      strncmp(data, "EWR1 ", 5)) return -EINVAL;
  p = data + 5;
  if (ew_alert_json_ulong(&p, event_id) < 0 || *p++ != ' ')
    return -EINVAL;
  errno = 0;
  number = strtol(p, &end, 10);
  if (errno == ERANGE || end == p || number < INT_MIN || number > 0 ||
      end != data + len - 1 || *end != '\n') return -EINVAL;
  *result = (int)number;
  return 0;
}

static inline int ew_alert_ipc_record_result(unsigned long event_id, int result)
{
  char data[96];
  int len = snprintf(data, sizeof(data), "EWR1 %lu %d\n", event_id, result);
  int ret;
  if (EW_ALERT_IPC_UNLINK(EW_ALERT_RESULT_TMP) < 0 && errno != ENOENT)
    return -errno;
  ret = ew_alert_ipc_write_file(EW_ALERT_RESULT_TMP, data, (size_t)len);
  if (ret == 0 && rename(EW_ALERT_RESULT_TMP, EW_ALERT_RESULT) < 0)
    ret = -errno;
  return ret;
}

/* Returns 1 after apply (possibly in an earlier call) and ACK, 0 if no
 * claimable request, or -errno. A recorded result is only finalized, never
 * applied again. Unknown consumer ownership without a result is not stolen.
 * The file mutex serializes threads/processes; it is released on retryable
 * finalization errors. A missing result after apply can only be retried by
 * this live consumer, whose pending state proves ownership of that result. */
static inline int ew_alert_ipc_consume(ew_alert_ipc_apply_fn apply, void *context,
                                      ew_alert_request_t *request)
{
  static struct {
    int active, durable, result;
    unsigned long event_id;
  } pending;
  char wire[EW_ALERT_WIRE_SIZE], ack[96], previous_ack[96];
  int ret, result, len, ack_len;
  unsigned long event_id;
  if (apply == NULL || request == NULL) return -EINVAL;
  memset(request, 0, sizeof(*request));
  if (ew_alert_ipc_mkdir(EW_ALERT_MUTEX) < 0)
    return errno == EEXIST ? 0 : -errno;

  ret = ew_alert_ipc_read_result(&event_id, &result);
  if (ret == 0) {
    /* A durable record authorizes any consumer to finish, including after
     * another consumer exits between apply and ACK. No callback is replayed. */
    pending.active = 0;
    request->event_id = event_id;
    goto finalize;
  }
  if (ret != -ENOENT) goto release;
  if (pending.active && pending.durable) {
    /* Another consumer already completed our recorded result. A subsequent
     * publication must not be mistaken for the old pending request. */
    pending.active = 0;
  }
  if (pending.active) {
    struct stat info;
    if (stat(EW_ALERT_CONSUMER, &info) < 0 ||
        stat(EW_ALERT_PROCESSING, &info) < 0) {
      ret = -errno;
      goto release;
    }
    event_id = pending.event_id;
    result = pending.result;
    request->event_id = event_id;
    goto record;
  }
  if (ew_alert_ipc_mkdir(EW_ALERT_CONSUMER) < 0) {
    ret = errno == ENOENT || errno == EEXIST ? 0 : -errno;
    goto release;
  }
  if (rename(EW_ALERT_REQ, EW_ALERT_PROCESSING) < 0) {
    ret = errno == ENOENT ? 0 : -errno;
    rmdir(EW_ALERT_CONSUMER);
    goto release;
  }
  len = ew_alert_ipc_read_file(EW_ALERT_PROCESSING, wire, sizeof(wire));
  ret = len < 0 ? len : ew_alert_ipc_decode(wire, (size_t)len, request);
  result = ret == 0 ? apply(request, context) : ret;
  /* Callbacks return 0 or -errno; a positive failure must not become success. */
  if (result > 0) result = -EIO;
  event_id = request->event_id;
  pending.active = 1;
  pending.durable = 0;
  pending.event_id = event_id;
  pending.result = result;
record:
  ret = ew_alert_ipc_record_result(event_id, result);
  if (ret < 0) goto release;
  pending.durable = 1;
finalize:
  ack_len = snprintf(ack, sizeof(ack), "EWA1 %lu %s %d\n", request->event_id,
                     result == 0 ? "applied" : "rejected", result);
  /* Slot may have been removed before a previous final cleanup failed. */
  if (ew_alert_ipc_mkdir(EW_ALERT_SLOT) < 0 && errno != EEXIST) {
    ret = -errno;
    goto release;
  }
  len = ew_alert_ipc_read_file(EW_ALERT_ACK, previous_ack, sizeof(previous_ack));
  if (len >= 0) {
    if (len != ack_len || memcmp(previous_ack, ack, (size_t)ack_len)) {
      ret = -EEXIST;
      goto release;
    }
  } else {
    if (len != -ENOENT) { ret = len; goto release; }
    if (EW_ALERT_IPC_UNLINK(EW_ALERT_ACK_TMP) < 0 && errno != ENOENT) {
      ret = -errno;
      goto release;
    }
    ret = ew_alert_ipc_write_file(EW_ALERT_ACK_TMP, ack, (size_t)ack_len);
    if (ret == 0 && rename(EW_ALERT_ACK_TMP, EW_ALERT_ACK) < 0) ret = -errno;
    if (ret < 0) goto release;
  }
  if ((EW_ALERT_IPC_UNLINK(EW_ALERT_PROCESSING) < 0 && errno != ENOENT) ||
      (rmdir(EW_ALERT_CONSUMER) < 0 && errno != ENOENT) ||
      (rmdir(EW_ALERT_SLOT) < 0 && errno != ENOENT) ||
      EW_ALERT_IPC_UNLINK(EW_ALERT_RESULT) < 0) {
    ret = -errno;
    goto release;
  }
  pending.active = 0;
  ret = result < 0 ? result : 1;
release:
  if (rmdir(EW_ALERT_MUTEX) < 0) return -errno;
  return ret;
}

#endif /* EW_ALERT_IPC_H */
