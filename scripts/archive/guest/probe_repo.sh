#!/bin/bash
cd ~/openvela
echo "=== vendor/openvela ==="
find vendor -maxdepth 4 -type d | head -40
ls -la vendor/openvela/
echo "=== packages ==="
ls packages | head
echo "=== repo list (sifli/sf32) ==="
repo list 2>/dev/null | grep -iE 'sifli|sf32|vendor' | head -40
echo "=== manifest projects count ==="
repo list 2>/dev/null | wc -l
echo "=== .repo/manifest.xml include ==="
ls .repo/manifests/ | head
grep -n 'sifli\|sf32\|vendor' .repo/manifests/*.xml 2>/dev/null | head -30
grep -n 'sifli\|sf32' contest2026_313_bianyuanxingzhe/openvela.xml 2>/dev/null | head -20
echo "=== incomplete? ==="
repo status -j4 2>&1 | head -30