#!/usr/bin/env python3
"""Replace mM3PMonitorBlob[] in patches/darwinboot-cpuon-monitor.patch with a
monitor .bin and fix the enclosing hunk header's new-side line count and the
'N-byte' size mentions. Usage: swap_blob.py monitor37.bin"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, '../../patches/darwinboot-cpuon-monitor.patch')
blob = open(os.path.join(HERE, sys.argv[1]), 'rb').read()
L = open(P).read().split('\n')
s = next(i for i, l in enumerate(L) if 'mM3PMonitorBlob[] = {' in l)
e = next(i for i in range(s, len(L)) if L[i].strip() in ('+};', '+  };'))
old_n = e - s - 1
rows = ['+    ' + ', '.join(f'0x{b:02x}' for b in blob[i:i + 12]) + ',' for i in range(0, len(blob), 12)]
L[s + 1:e] = rows
d = len(rows) - old_n
h = max(i for i in range(s) if L[i].startswith('@@'))
m = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)', L[h])
L[h] = f'@@ -{m[1]},{m[2]} +{m[3]},{int(m[4]) + d} @@{m[5]}'
for j in range(h + 1, len(L)):                      # later hunks shift on the new side
    mm = re.match(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*)', L[j])
    if mm: L[j] = f'@@ -{mm[1]},{mm[2]} +{int(mm[3]) + d},{mm[4]} @@{mm[5]}'
t = '\n'.join(L)
t = re.sub(r'copies a \d+-byte position', f'copies a {len(blob)}-byte position', t)
open(P, 'w').write(t)
print(f'blob {len(blob)} B, {len(rows)} lines ({d:+d}); hunk {L[h]}')
