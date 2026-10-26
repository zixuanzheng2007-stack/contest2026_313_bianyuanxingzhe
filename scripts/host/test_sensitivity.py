"""Verify real policy presets and the device console acknowledgement."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'app/edge_walker'


class SensitivityTests(unittest.TestCase):
    def test_policy_and_actual_console_handler(self):
        serial = (SRC / 'ew_serial_ctl.c').read_text(encoding='utf-8')
        helpers = serial[serial.index('static void skip_spaces('):serial.index('#if defined(__NuttX__)')]
        start = serial.index('  if (strcmp(verb, "sensitivity") == 0)')
        block = serial[start:serial.index('  if (strcmp(verb, "snapshot") == 0)', start)]
        c = r'''
#include "ew_ld2451.h"
#include <assert.h>
#include <ctype.h>
#include <stdio.h>
#include <string.h>
''' + helpers + r'''
static void dispatch(const char *line) {
  const char *p=line; char verb[32];parse_token(&p,verb,sizeof(verb));
''' + block + r'''
}
int main(void) {
  ew_track_t t; ew_decision_t d;
  memset(&t,0,sizeof(t));t.valid=true;t.approaching=true;t.snr=30;t.speed_kmh=5;
  assert(ew_sensitivity_get()==EW_SENSITIVITY_STANDARD);
  t.range_m=28;assert(ew_decide(&t).level==EW_ALERT_NONE);
  assert(ew_sensitivity_set(EW_SENSITIVITY_EARLY)==0);
  assert(ew_decide(&t).level==EW_ALERT_SOFT);
  t.range_m=9;assert(ew_decide(&t).level==EW_ALERT_EMERGENCY);
  t.range_m=16;assert(ew_decide(&t).level==EW_ALERT_STRONG);
  t.range_m=31.25;assert(ew_decide(&t).level==EW_ALERT_SOFT);
  t.range_m=31.26;assert(ew_decide(&t).level==EW_ALERT_NONE);
  t.range_m=100;t.speed_kmh=100;assert(ew_decide(&t).level==EW_ALERT_STRONG);
  assert(ew_sensitivity_set((ew_sensitivity_t)2)<0);
  assert(ew_sensitivity_get()==EW_SENSITIVITY_EARLY);
  t.speed_kmh=1;t.range_m=1;assert(ew_decide(&t).level==EW_ALERT_NONE);
  t.radar_alarm=true;assert(ew_decide(&t).level==EW_ALERT_SOFT);
  t.radar_alarm=false;t.speed_kmh=5;t.snr=0;assert(ew_decide(&t).level==EW_ALERT_NONE);
  assert(ew_sensitivity_set(EW_SENSITIVITY_STANDARD)==0);
  t.snr=30;t.range_m=28;assert(ew_decide(&t).level==EW_ALERT_NONE);
  t.range_m=9;d=ew_decide(&t);assert(d.level==EW_ALERT_STRONG);
  dispatch("sensitivity a get");dispatch("sensitivity b early");
  dispatch("sensitivity c get");dispatch("sensitivity d standard");
  dispatch("sensitivity e unknown");dispatch("sensitivity f early extra");
  dispatch("sensitivity bad! early");dispatch("sensitivity g get");
  assert(ew_sensitivity_get()==EW_SENSITIVITY_STANDARD);
  return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='ew_sensitivity_') as directory:
            source = Path(directory) / 'test.c'
            exe = Path(directory) / 'test.exe'
            source.write_text(c, encoding='utf-8')
            subprocess.run(['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror',
                            '-I',str(SRC),str(source),str(SRC/'ew_ld2451.c'),'-lm','-o',str(exe)],check=True)
            lines = subprocess.check_output([str(exe)],text=True).splitlines()
            results = [json.loads(line.split('] ',1)[1]) for line in lines]
        self.assertEqual([r.get('profile') for r in results],
                         ['standard','early','early','standard',None,None,None,'standard'])
        self.assertTrue(all(r['ok'] is False and r['id'] is None for r in results[4:7]))
        self.assertEqual(results[1]['factor'],1.25)
        self.assertTrue(results[1]['volatile'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
