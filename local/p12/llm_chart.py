"""P18: figura SVG da varredura com LLM, lida de evidence/p18/<modelo>.json (sem chamar a API).

Uso (na raiz): python3 local/p12/llm_chart.py cohere_command-a-plus   → docs/p18-llm.svg
"""
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
data = json.loads((ROOT / 'evidence/p18' / f'{sys.argv[1]}.json').read_text())
rows = data['rows']
W, TOP, H = 880, 92, 44
BG, FG, MUTED, OK, WARN = '#14101f', '#ece8f6', '#9a93b0', '#4ade80', '#fbbf24'
max_latency = max(r['latency_s'] for r in rows)
parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {TOP + H * len(rows) + 56}" font-family="Ubuntu, sans-serif">',
         f'<rect width="100%" height="100%" rx="10" fill="{BG}"/>',
         f'<text x="24" y="34" fill="{FG}" font-size="18" font-weight="700">Execução com LLM: {escape(data["model"])}</text>',
         f'<text x="24" y="56" fill="{MUTED}" font-size="13">{data["accepted"]}/{data["calls"]} respostas aceitas pelo checker de fidelidade; '
         f'as demais caíram no fallback determinístico</text>']
for x, label in ((24, 'cenário (sintético)'), (250, 'resultado'), (520, 'latência (s)'), (740, 'tokens ent./saí.')):
    parts.append(f'<text x="{x}" y="82" fill="{MUTED}" font-size="12">{label}</text>')
for i, r in enumerate(rows):
    y = TOP + i * H
    ok = r['mode'] == 'llm'
    reason = '' if ok else ' · ' + ', '.join(r['audit'].get('reasons', []))
    tokens = f'{r["prompt_tokens"]:,} / {r["completion_tokens"]:,}'.replace(',', '.')
    bar = r['latency_s'] / max_latency * 150
    parts += [
        f'<text x="24" y="{y + 20}" fill="{FG}" font-size="14">{escape(r["scenario"])}</text>',
        f'<rect x="250" y="{y + 4}" width="14" height="14" rx="3" fill="{OK if ok else WARN}"/>',
        f'<text x="272" y="{y + 16}" fill="{FG}" font-size="13">{"aceita" if ok else "fallback"}{escape(reason)}</text>',
        f'<rect x="520" y="{y + 6}" width="{bar:.0f}" height="12" rx="3" fill="#8b5cf6"/>',
        f'<text x="{520 + bar + 8:.0f}" y="{y + 17}" fill="{MUTED}" font-size="12">{r["latency_s"]:.1f}</text>',
        f'<text x="740" y="{y + 17}" fill="{FG}" font-size="12">{tokens}</text>',
    ]
parts.append(f'<text x="24" y="{TOP + H * len(rows) + 30}" fill="{MUTED}" font-size="12">'
             'observed · cenários synthetic, seed 42 · custo estimado US$ 0 (plano gratuito) · evidence/p18</text></svg>')
(ROOT / 'docs/p18-llm.svg').write_text('\n'.join(parts) + '\n')
print('docs/p18-llm.svg')
