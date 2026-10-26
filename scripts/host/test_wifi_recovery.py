"""Fault-inject the real AT ownership, setup and probe state transitions."""
from pathlib import Path
import subprocess
import tempfile

from test_wifi_rx_bounds import function

ROOT = Path(__file__).resolve().parents[2]


def main():
    source = (ROOT / "app/edge_walker/ew_wifi_at.c").read_text(encoding="utf-8")
    probe_start = source.index("ew_wifi_state_t ew_wifi_probe(")
    probe_end = source.index("\n}", probe_start) + 2
    harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "ew_wifi_at.h"
#include "ew_net_state.h"
static int g_at_mu, lock_calls, unlock_after, lock_error, sleep_ms;
static int tx_calls, fail_tx, fail_kind, publish_calls, state_errors;
static int fake_mutex_trylock(int *mu) {
  (void)mu; lock_calls++;
  if(lock_error) return lock_error;
  return lock_calls>unlock_after ? 0 : EBUSY;
}
static int fake_usleep(unsigned us) { sleep_ms+=(int)(us/1000); return 0; }
#define pthread_mutex_trylock fake_mutex_trylock
#define usleep fake_usleep
static int at_tx(int fd,const char *cmd,char *out,unsigned size,
                 int idle,int total,int ip) {
  (void)fd;(void)cmd;(void)idle;(void)total;(void)ip; tx_calls++;
  if(tx_calls==fail_tx) {
    snprintf(out,size,"%s",fail_kind==1 ? "ERROR\r\n" : "");
    return fail_kind==2 ? -1 : (int)strlen(out);
  }
  snprintf(out,size,"\r\nOK\r\n");return (int)strlen(out);
}
static int at_begin(void) { errno=EBUSY;return -1; }
static void at_end(int fd) { (void)fd;assert(0); }
static int at_wake_light(int fd) { (void)fd;assert(0);return -1; }
static int query_sta_ip(int fd,char *ip,unsigned n) {
  (void)fd;(void)ip;(void)n;assert(0);return -1;
}
static int inet_probe(int fd) { (void)fd;assert(0);return -1; }
static void ew_net_state_publish_test(ew_net_link_t link,const char *ip) {
  (void)link;(void)ip;publish_calls++;
}
static void ew_net_state_error_test(ew_net_error_t error) {
  assert(error==EW_NET_ERR_AT_BUSY);state_errors++;
}
#define ew_net_state_publish ew_net_state_publish_test
#define ew_net_state_error ew_net_state_error_test
''' + "\n".join(function(source, name) for name in (
        "resp_ok", "resp_fail", "at_lock", "at_station_setup")) + source[probe_start:probe_end] + r'''
int main(void) {
  char ip[24]; int kind;
  assert(resp_ok("OK\r\n") && resp_ok("AT\r\n\r\nOK\r\n"));
  assert(!resp_ok("NOTOK\r\n") && !resp_ok("BROK\r\n"));
  assert(!resp_ok("OK") && !resp_ok(NULL));
  unlock_after=1000;assert(at_lock()==-1 && errno==EBUSY);
  assert(lock_calls==51 && sleep_ms==500);
  lock_calls=sleep_ms=0;unlock_after=3;
  assert(at_lock()==0 && lock_calls==4 && sleep_ms==30);
  lock_calls=sleep_ms=0;lock_error=EINVAL;
  assert(at_lock()==-1 && errno==EINVAL && lock_calls==1 && sleep_ms==0);
  for(kind=1;kind<=2;kind++) {
    fail_kind=kind;fail_tx=1;tx_calls=0;
    assert(at_station_setup(1)==-1 && tx_calls==1);
    fail_tx=2;tx_calls=0;
    assert(at_station_setup(1)==-1 && tx_calls==2);
  }
  tx_calls=fail_tx=0;assert(at_station_setup(1)==0 && tx_calls==2);
  assert(ew_wifi_probe(0,ip,sizeof(ip))==EW_WIFI_DOWN);
  assert(ip[0]==0 && publish_calls==0 && state_errors==1);
  puts("PASS: bounded contention, early lock errors, strict OK, setup rejection, busy preserves link");
  return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="ew_wifi_recovery_") as directory:
        path = Path(directory)
        cfile, exe = path / "recovery.c", path / "recovery.exe"
        cfile.write_text(harness, encoding="utf-8")
        subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                        "-I", str(ROOT / "app/edge_walker"), str(cfile),
                        "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=3)


if __name__ == "__main__":
    main()
