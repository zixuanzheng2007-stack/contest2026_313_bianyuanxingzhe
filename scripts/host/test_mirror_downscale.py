"""Check in-place RGB565 downsampling against a separate destination buffer."""
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("EW_REPO_ROOT", Path(__file__).resolve().parents[2]))
source = (ROOT / "app/edge_walker/ew_mirror.c").read_text(encoding="utf-8")
function = source[source.index("static void downscale_rgb565("):
                  source.index("static int pixel_equal565(")]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
'''
cases = r'''
int main(void) {
  int sizes[][2] = {{390,450}, {391,451}, {6,6}, {7,9}};
  unsigned t;
  int pad, scale;
  for (t = 0; t < sizeof(sizes)/sizeof(sizes[0]); t++) {
    for (pad = 0; pad <= 8; pad += 2) {
      for (scale = 1; scale <= 3; scale++) {
        int w = sizes[t][0], h = sizes[t][1], stride = w*2 + pad;
        int dw = w/scale, dh = h/scale;
        size_t n = (size_t)stride*h, i;
        uint8_t *src = malloc(n), *inplace = malloc(n), *out = malloc(n);
        assert(src && inplace && out);
        for (i = 0; i < n; i++) src[i] = (uint8_t)((i*37 + i/11) % 256);
        memcpy(inplace, src, n);
        downscale_rgb565(src,w,h,stride,scale,out,dw,dh);
        downscale_rgb565(inplace,w,h,stride,scale,inplace,dw,dh);
        assert(memcmp(out,inplace,(size_t)dw*dh*2) == 0);
        for (i = (size_t)dw*dh*2; i < n; i++) assert(inplace[i] == src[i]);
        free(src); free(inplace); free(out);
      }
    }
  }
  puts("PASS: 60 in-place cases, scales 1/2/3, padded rows, unchanged tail");
  return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="ew_mirror_test_") as directory:
    path = Path(directory)
    (path / "test.c").write_text(harness + function + cases, encoding="utf-8")
    built = subprocess.run(
        ["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror",
         "-Wno-unused-parameter", str(path / "test.c"),
         "-o", str(path / "test.exe")],
        capture_output=True, text=True,
    )
    if built.returncode != 0:
        raise RuntimeError(built.stdout + built.stderr)
    subprocess.run([str(path / "test.exe")], check=True)
