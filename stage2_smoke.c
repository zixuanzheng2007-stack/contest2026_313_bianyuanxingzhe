/****************************************************************************
 * Host-only Stage 2 smoke test for stable network fault classification.
 *
 * This does not test ESP-AT, NuttX, a development board or real networking.
 ****************************************************************************/

#include "ew_net_status.h"

#include <stdio.h>
#include <string.h>

static int g_fail;

static void expect(int ok, const char *name)
{
  if (ok)
    {
      printf("  PASS %s\n", name);
    }
  else
    {
      printf("FAIL %s\n", name);
      g_fail++;
    }
}

static void test_http(void)
{
  expect(ew_net_http_status("HTTP/1.1 200 OK\r\n") == 200,
         "parse HTTP 200");
  expect(ew_net_http_status("HTTP/1.1 429 Too Many Requests\r\n") == 429,
         "parse HTTP 429");
  expect(ew_net_http_status("not an HTTP response") == -1,
         "reject malformed status");
  expect(ew_net_http_status("HTTP/1.1 2") == -1,
         "reject truncated status");
  expect(ew_net_fault_from_http_status(200) == EW_NET_FAULT_OK,
         "2xx is ready");
  expect(ew_net_fault_from_http_status(401) == EW_NET_FAULT_HTTP_AUTH,
         "401 is auth");
  expect(ew_net_fault_from_http_status(403) == EW_NET_FAULT_HTTP_AUTH,
         "403 is auth");
  expect(ew_net_fault_from_http_status(429) == EW_NET_FAULT_HTTP_RATE_LIMIT,
         "429 is rate limit");
  expect(ew_net_fault_from_http_status(500) == EW_NET_FAULT_HTTP_SERVER,
         "500 is server error");
  expect(ew_net_fault_from_http_status(404) == EW_NET_FAULT_HTTP_BAD,
         "other 4xx is bad request");
}

static void test_join(void)
{
  expect(ew_net_fault_from_join_response("+CWJAP:1\r\nFAIL\r\n") ==
         EW_NET_FAULT_JOIN_TIMEOUT, "+CWJAP:1 is timeout");
  expect(ew_net_fault_from_join_response("+CWJAP:2\r\nFAIL\r\n") ==
         EW_NET_FAULT_BAD_PASSWORD, "+CWJAP:2 is bad password");
  expect(ew_net_fault_from_join_response("+CWJAP:3\r\nFAIL\r\n") ==
         EW_NET_FAULT_AP_NOT_FOUND, "+CWJAP:3 is AP not found");
  expect(ew_net_fault_from_join_response("+CWJAP:4\r\nFAIL\r\n") ==
         EW_NET_FAULT_JOIN_FAILED, "+CWJAP:4 is join failure");
  expect(ew_net_fault_from_join_response("") ==
         EW_NET_FAULT_JOIN_TIMEOUT, "empty join response is timeout");
}

static void test_text_and_redaction(void)
{
  char redacted[96];

  expect(strcmp(ew_net_fault_code(EW_NET_FAULT_BAD_PASSWORD),
                "bad_password") == 0, "stable fault code");
  expect(strcmp(ew_net_fault_text(EW_NET_FAULT_NO_MODEM),
                "NO MODEM: check AT module") == 0,
         "short display text");
  expect(ew_net_redact_secret("Bearer demo-secret-123 end", "demo-secret-123",
                              redacted, sizeof(redacted)) == 0,
         "redaction succeeds");
  expect(strcmp(redacted, "Bearer *** end") == 0,
         "secret is masked");
  expect(strstr(redacted, "demo-secret-123") == NULL,
         "raw secret is absent");
}

int main(void)
{
  printf("edge_walker stage2_smoke\n");
  test_http();
  test_join();
  test_text_and_redaction();
  if (g_fail == 0)
    {
      printf("STAGE2 PASS\n");
      return 0;
    }
  printf("%d FAIL\n", g_fail);
  return 1;
}
