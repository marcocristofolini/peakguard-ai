"""P18: uma chamada real por cenário; conta propostas aceitas pelo checker de fidelidade × fallback.

Uso (na raiz; a chave só no ambiente, nunca gravada):
    OPENAI_API_KEY=... PEAKGUARD_LLM_BASE_URL=... PEAKGUARD_LLM_MODEL=... python3 local/p12/llm_sweep.py [cenario ...]
Grava evidence/p18/<modelo>.json com auditoria, tokens, latência e a proposta devolvida (sem a chave).
Para na primeira falha de API 4xx, para não gastar chamadas à toa. Fora do CI (chamadas pagas).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['PEAKGUARD_LLM_ENABLED'] = 'true'
from peakguard.explanations import explain  # noqa: E402
from peakguard.llm import generate  # noqa: E402
from peakguard.scenarios import ALL_SCENARIOS, load_scenario  # noqa: E402
from peakguard.simulator import Config, compare  # noqa: E402

model = os.environ['PEAKGUARD_LLM_MODEL']
names = sys.argv[1:] or list(ALL_SCENARIOS)
rows = []
for name in names:
    usage, seen = {}, {}

    def provider(ctx):
        t0 = time.perf_counter()
        try:
            seen['proposal'] = generate(ctx, usage=usage)
            return seen['proposal']
        except Exception as e:  # classe e status, nunca o corpo (pode conter segredo)
            seen['error'] = f'{type(e).__name__} {getattr(e, "status_code", "")}'.strip()
            raise
        finally:
            seen['latency_s'] = round(time.perf_counter() - t0, 2)

    result = explain(compare(load_scenario(name, 42), Config()), provider=provider, use_llm=True)
    row = {'scenario': name, 'mode': result['mode'], 'audit': result['audit'][0], **seen, **usage}
    rows.append(row)
    print(json.dumps({'scenario': name, 'mode': row['mode'], 'reasons': row['audit'].get('reasons'),
                      'latency_s': row.get('latency_s'), 'in': usage.get('prompt_tokens'),
                      'out': usage.get('completion_tokens'), 'error': row.get('error')}, ensure_ascii=False), flush=True)
    if re.search(r' 4\d\d$', row.get('error', '')):
        print('Parando: erro 4xx do provedor.')
        break
out = ROOT / 'evidence/p18'
out.mkdir(parents=True, exist_ok=True)
accepted = sum(r['mode'] == 'llm' for r in rows)
(out / (model.replace('/', '_') + '.json')).write_text(json.dumps(
    {'labels': {'metrics': 'observed', 'load': 'synthetic'}, 'model': model,
     'base_url': os.environ.get('PEAKGUARD_LLM_BASE_URL'), 'accepted': accepted, 'calls': len(rows), 'rows': rows},
    indent=1, ensure_ascii=False) + '\n')
print(f'{model}: {accepted}/{len(rows)} aceitas pelo checker')
