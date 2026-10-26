/* SPDX-License-Identifier: Apache-2.0 */
#include "ew_esp_stream.h"

#include <errno.h>
#include <string.h>

static int fail(ew_esp_stream_t *parser, int error)
{
  parser->error = error;
  return error;
}

static void emit(ew_esp_stream_t *parser, ew_esp_stream_event_t event,
                 int link_id)
{
  parser->buffer[parser->length] = 0;
  parser->callback(parser->context, event, link_id,
                    parser->buffer, parser->length);
  parser->length = 0;
}

/* Parse decimal without strtol, locale, signs or overflow. */
static int decimal(const unsigned char *bytes, size_t length,
                    size_t limit, size_t *value)
{
  size_t index;
  size_t result = 0;

  if (length == 0) {
    return -EPROTO;
  }
  for (index = 0; index < length; index++) {
    unsigned digit;
    if (bytes[index] < '0' || bytes[index] > '9') {
      return -EPROTO;
    }
    digit = (unsigned)(bytes[index] - '0');
    if (digit > limit || result > (limit - digit) / 10u) {
      return -EMSGSIZE;
    }
    result = result * 10u + digit;
  }
  *value = result;
  return 0;
}

static int header(ew_esp_stream_t *parser)
{
  size_t start = 5u; /* +IPD, */
  size_t index = start;
  size_t value;
  int result;

  parser->link_id = -1;
  if (parser->multiple) {
    while (index < parser->length && parser->buffer[index] != ',') {
      index++;
    }
    if (index == parser->length) {
      return fail(parser, -EPROTO);
    }
    result = decimal(parser->buffer + start, index - start,
                       EW_ESP_STREAM_LINK_MAX, &value);
    if (result != 0) {
      return fail(parser, result);
    }
    parser->link_id = (int)value;
    start = index + 1u;
  }
  result = decimal(parser->buffer + start, parser->length - start,
                     EW_ESP_STREAM_DATA_MAX, &value);
  if (result != 0) {
    return fail(parser, result);
  }
  parser->length = 0;
  parser->expected = value;
  if (value == 0) {
    emit(parser, EW_ESP_STREAM_DATA, parser->link_id);
  }
  return 0;
}

int ew_esp_stream_init(ew_esp_stream_t *parser, int multiple,
                        ew_esp_stream_callback_t callback, void *context)
{
  if (parser == NULL || callback == NULL ||
      (multiple != 0 && multiple != 1)) {
    return -EINVAL;
  }
  memset(parser, 0, sizeof(*parser));
  parser->multiple = multiple;
  parser->callback = callback;
  parser->context = context;
  parser->link_id = -1;
  return 0;
}

int ew_esp_stream_feed(ew_esp_stream_t *parser,
                        const void *bytes, size_t length)
{
  const unsigned char *input = bytes;
  size_t index;

  if (parser == NULL || parser->callback == NULL ||
      (bytes == NULL && length != 0)) {
    return -EINVAL;
  }
  if (parser->error != 0) {
    return parser->error;
  }
  for (index = 0; index < length; index++) {
    unsigned char byte = input[index];
    int ipd;
    if (parser->expected != 0) {
      parser->buffer[parser->length++] = byte;
      if (parser->length == parser->expected) {
        parser->expected = 0;
        emit(parser, EW_ESP_STREAM_DATA, parser->link_id);
      }
      continue;
    }
    if (parser->prompt_space) {
      parser->prompt_space = 0;
      if (byte == ' ') {
        continue;
      }
    }
    if (parser->length == 0 && byte == '>') {
      emit(parser, EW_ESP_STREAM_PROMPT, -1);
      parser->prompt_space = 1;
      continue;
    }
    ipd = parser->length >= 5u &&
          memcmp(parser->buffer, "+IPD,", 5u) == 0;
    if (ipd && byte == ':') {
      if (header(parser) != 0) {
        return parser->error;
      }
      continue;
    }
    if (byte == '\n') {
      /* A passive-mode +IPD notice is not an active-mode payload header. */
      if (ipd) {
        return fail(parser, -EPROTO);
      }
      if (parser->length != 0 &&
          parser->buffer[parser->length - 1u] == '\r') {
        parser->length--;
      }
      if (parser->length != 0) {
        emit(parser, EW_ESP_STREAM_LINE, -1);
      }
      continue;
    }
    if (byte == 0) {
      return fail(parser, -EPROTO);
    }
    if (parser->length == EW_ESP_STREAM_LINE_MAX) {
      return fail(parser, -EMSGSIZE);
    }
    parser->buffer[parser->length++] = byte;
  }
  return 0;
}

int ew_esp_stream_expire(ew_esp_stream_t *parser)
{
  if (parser == NULL || parser->callback == NULL) {
    return -EINVAL;
  }
  if (parser->error != 0) {
    return parser->error;
  }
  if (parser->length != 0 || parser->expected != 0) {
    return fail(parser, -ETIMEDOUT);
  }
  return 0;
}
