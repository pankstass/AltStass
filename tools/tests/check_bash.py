"""Проверка синтаксиса всех блоков команд через `bash -n` и отсутствия неподставленных @ТОКЕНОВ@.
Запуск из корня репозитория: python3 tools/tests/check_bash.py"""
import re, html, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
bad = tot = 0
for f in ('index.html', 'module2.html'):
    s = (ROOT / f).read_text(encoding='utf-8')
    for bid, code in re.findall(r'<div class="block[^"]*" id="([^"]+)".*?<pre><code>(.*?)</code></pre>', s, re.S):
        t = html.unescape(re.sub(r'<[^>]+>', '', code)); tot += 1
        r = subprocess.run(['bash', '-n'], input=t, capture_output=True, text=True)
        left = re.findall(r'@[A-Z][A-Z0-9_]*@', t)
        if r.returncode or left:
            bad += 1; print(f, bid, r.stderr.strip()[:200], left)
print('blocks:', tot, 'errors:', bad)
sys.exit(1 if bad else 0)
