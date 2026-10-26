# SPDX-License-Identifier: Apache-2.0
"""Compile the real AT receive loops with controlled UART bytes and clocks."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def function(source: str, name: str) -> str:
    start = source.index("static int " + name + "(")
    brace = source.index("{", start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


PRELUDE = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
static uint32_t now_ms;
static unsigned calls, sleeps, step_ms, packet_index, packet_count;
static int flood, frozen;
static const char *packets[16];
static uint32_t monotonic_ms(void) { return now_ms; }
static int fake_usleep(unsigned micros) {
  sleeps++;
  if(!frozen) now_ms+=micros/1000u;
  return 0;
}
static ssize_t fake_read(int fd,void *out,size_t size) {
  const char *part; size_t n; (void)fd;
  calls++; if(!frozen) now_ms+=step_ms;
  if(flood) {
    memset(out,'X',size);
    /* No received UART payload is allowed to reach drain's console log. */
    if(size>=16) memcpy(out,"tp-DO_NOT_LOG",13);
    return (ssize_t)size;
  }
  if(packet_index>=packet_count) return 0;
  part=packets[packet_index++];
  if(!part) return 0;
  n=strlen(part); assert(n<=size); memcpy(out,part,n); return (ssize_t)n;
}
static void reset(void) {
  now_ms=0; calls=sleeps=packet_index=packet_count=0;
  step_ms=0; flood=frozen=0; memset(packets,0,sizeof(packets));
}
#define read fake_read
#define usleep fake_usleep
'''

CASES = r'''
int main(int argc,char **argv) {
  char out[256]; int n;
  assert(argc==2); reset();
  if(!strcmp(argv[1],"drain_total")) {
    flood=1; step_ms=1; at_drain_rx(1,50);
    assert(calls==50 && now_ms==50 && sleeps==0);
  } else if(!strcmp(argv[1],"command_total")) {
    flood=1; step_ms=1; n=at_read(1,out,32,100,30,0);
    assert(n==31 && out[31]==0 && calls==30 && now_ms==30);
  } else if(!strcmp(argv[1],"scan_total")) {
    flood=1; step_ms=1; n=at_read_scan(1,out,sizeof(out),35);
    assert(n==255 && out[255]==0 && calls==35 && now_ms==35);
  } else if(!strcmp(argv[1],"clock_stalled")) {
    frozen=flood=1; n=at_read(1,out,32,100,300,0);
    assert(n==31 && calls<=EW_AT_RX_READ_LIMIT && calls*64u<=EW_AT_RX_BYTE_LIMIT);
    reset(); frozen=flood=1; at_drain_rx(1,300);
    assert(calls<=EW_AT_RX_READ_LIMIT && calls*128u<=EW_AT_RX_BYTE_LIMIT);
    reset(); frozen=flood=1; n=at_read_scan(1,out,sizeof(out),55000);
    assert(n==255 && calls<=EW_AT_RX_READ_LIMIT && calls*128u<=EW_AT_RX_BYTE_LIMIT);
  } else if(!strcmp(argv[1],"empty_and_wrap")) {
    n=at_read(1,out,sizeof(out),40,200,0);
    assert(n==0 && calls==2 && now_ms==40);
    reset(); at_drain_rx(1,60); assert(calls==3 && now_ms==60);
    reset(); n=at_read_scan(1,out,sizeof(out),55000);
    assert(n==0 && calls==750 && now_ms==15000);
    reset(); flood=1; step_ms=10; now_ms=UINT32_MAX-20u;
    n=at_read(1,out,sizeof(out),100,40,0); assert(n==255 && calls==4);
  } else if(!strcmp(argv[1],"fragmented_responses")) {
    packets[0]="\r\nO"; packets[1]="K\r\n"; packet_count=2;
    n=at_read(1,out,sizeof(out),100,500,0);
    assert(n==6 && calls==2 && resp_ok(out));
    reset(); packets[0]="WIFI GOT "; packets[1]="IP\r\n"; packet_count=2;
    n=at_read(1,out,sizeof(out),100,500,1);
    assert(n==13 && calls==2 && resp_got_ip(out));
    reset(); packets[0]="ERROR\r\n"; packet_count=1;
    n=at_read(1,out,sizeof(out),100,500,0);
    assert(n==7 && calls==1 && resp_fail(out));
  } else if(!strcmp(argv[1],"scan_tail_and_silence")) {
    packets[0]="+CWLAP:(3,\"early\",-40)\r\n";
    packets[1]="\r\nO"; packets[2]="K\r\n";
    packets[3]=NULL; packets[4]=NULL; packets[5]=NULL;
    packets[6]="+CWLAP:(3,\"late\",-50)\r\n"; packet_count=7;
    n=at_read_scan(1,out,sizeof(out),55000);
    assert(n>0 && strstr(out,"early") && strstr(out,"late") && resp_ok(out));
    assert(now_ms==3060 && calls==157);
  } else if(!strcmp(argv[1],"zero_limits")) {
    assert(at_read(1,out,0,10,10,0)==-1 && calls==0);
    assert(at_read_scan(1,out,0,10)==-1 && calls==0);
    at_drain_rx(1,0); assert(calls==0);
    assert(at_read(1,out,sizeof(out),10,0,0)==0 && calls==0);
    assert(at_read_scan(1,out,sizeof(out),0)==0 && calls==0);
  } else { return 3; }
  printf("PASS real AT RX %s\n",argv[1]); return 0;
}
'''


class WifiRxBounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("gcc")
        if not compiler:
            raise RuntimeError("GCC is required for real AT RX regressions")
        cls.temp = tempfile.TemporaryDirectory(prefix="ew_wifi_rx_")
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        source = (ROOT / "app/edge_walker/ew_wifi_at.c").read_text(encoding="utf-8")
        bounded = source[source.index("#define EW_AT_RX_READ_LIMIT"):
                         source.index("static int resp_ok(")]
        receive = source[source.index("static int at_read("):
                         source.index("static int scan_count_markers(const char *buf)\n{")]
        helpers = "".join(function(source, name) for name in ("resp_ok", "resp_fail", "resp_got_ip"))
        cfile = path / "rx_test.c"
        cls.executable = path / "rx_test.exe"
        cfile.write_text(PRELUDE + bounded + helpers + receive + CASES, encoding="utf-8")
        subprocess.run([compiler, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(cfile), "-o", str(cls.executable)], check=True)

    def test_actual_receive_functions(self):
        for case in ("drain_total", "command_total", "scan_total", "clock_stalled",
                     "empty_and_wrap", "fragmented_responses", "scan_tail_and_silence", "zero_limits"):
            with self.subTest(case=case):
                result = subprocess.run([str(self.executable), case], capture_output=True,
                                        text=True, timeout=3)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS real AT RX " + case, result.stdout)
                self.assertNotIn("tp-DO_NOT_LOG", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
