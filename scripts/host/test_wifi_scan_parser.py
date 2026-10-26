"""Compile the actual firmware scan parser on the host and reproduce scan issues."""
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    source = (ROOT / "app/edge_walker/ew_wifi_at.c").read_text(encoding="utf-8")
    scan = source[source.index("static int scan_insert_ap("):
                  source.index("static int scan_tx_cwlap(")]
    harness = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ew_wifi_at.h"
'''
    cases = r'''
int main(void)
{
  ew_wifi_ap_t aps[EW_WIFI_SCAN_MAX], ap;
  char buf[8192];
  int n = 0, i, pos = 0;
  for (i = 0; i < 24; i++) {
    pos += snprintf(buf + pos, sizeof(buf) - pos,
                    "+CWLAP:(3,\"ap%02d\",-%d)\r\n", i, 30 + i);
  }
  scan_from_buf(buf, aps, EW_WIFI_SCAN_MAX, &n);
  assert(n == 24);
  puts("PASS: 24 distinct SSIDs retained; no three-item limit");
  n = 0;
  scan_from_buf("+CWLAP:(0,\"BUPT-portal\",-66)\r\n"
                "+CWLAP:(0,\"BUPT-portal\",-77)\r\n"
                "+CWLAP:(0,\"BUPT-portal\",-82)\r\n", aps, 24, &n);
  assert(n == 1 && aps[0].rssi == -66);
  puts("PASS: repeated BSSIDs sharing one SSID collapse to one row");
  assert(scan_parse_line("+CWLAP:(3,\"Pura 80 Pro+\",-42)", &ap) == 0);
  assert(strcmp(ap.ssid, "Pura 80 Pro+") == 0 && ap.rssi == -42);
  puts("PASS: Pura name, spaces and plus sign parse correctly");
  assert(scan_parse_line("+CWLAP:(7,\"Pura 80 Pro+\",-42)", &ap) == 0);
  puts("PASS: WPA2/WPA3 scan entry is not filtered by encryption mode");
  assert(scan_parse_line("+CWLAP:(0,\"broken\",oops)", &ap) < 0);
  assert(scan_parse_line("+CWLAP:(0,\"broken\",-42oops)", &ap) < 0);
  puts("PASS: malformed RSSI rejected");
  assert(scan_parse_line("+CWLAP:(0,\"broken\",", &ap) < 0);
  assert(scan_parse_line("+CWLAP:(0,\"broken\",-42,", &ap) < 0);
  puts("PASS: truncated response rejected");
  assert(scan_parse_line("+CWLAP:(3,\"\",-42)", &ap) < 0);
  puts("PASS: hidden SSID omitted from selectable names");
  assert(scan_parse_line("+CWLAP:(3,\"a\\\"b\\,c\\\\d\",-40)", &ap) == 0);
  assert(strcmp(ap.ssid, "a\"b,c\\d") == 0);
  assert(scan_parse_line("+CWLAP:(3,\"12345678901234567890123456789012\",-40)", &ap) == 0);
  assert(scan_parse_line("+CWLAP:(3,\"123456789012345678901234567890123\",-40)", &ap) < 0);
  assert(scan_parse_line("+CWLAP:(0,unquoted,-40)", &ap) < 0);
  assert(scan_parse_line("+CWLAP:(oops,\"bad\",-40)", &ap) < 0);
  puts("PASS: escaped SSIDs, length limit and encryption validation");
  n = 0;
  scan_from_buf("+CWLAP:(0,\"BUPT-portal\",-66)\r\n"
                "+CWLAP:(0,\"BPT-portal\",-65)\r\n"
                "+CWLAP:(0,\"tal\\\"\",oops)\r\n", aps, 24, &n);
  assert(n == 2);
  scan_sort_rssi(aps, n);
  assert(aps[0].rssi == -65);
  puts("PASS: bogus 0 dBm entry rejected; valid-looking corruption still needs UART fix");
  return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="ew_wifi_parser_") as directory:
        path = Path(directory)
        cfile = path / "scan_test.c"
        exe = path / "scan_test.exe"
        cfile.write_text(harness + scan + cases, encoding="utf-8")
        subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                        "-I", str(ROOT / "app/edge_walker"), str(cfile),
                        "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
