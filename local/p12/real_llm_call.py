import os, sys, time, json
sys.path.insert(0, ".")  # rodar da raiz: set -a; . ./.env; set +a; python3 local/p12/real_llm_call.py
need = ("OPENAI_API_KEY", "PEAKGUARD_LLM_MODEL")
missing = [k for k in need if not os.environ.get(k)]
if missing:
    print("BLOQUEIO: variáveis ausentes:", ", ".join(missing)); sys.exit(2)
os.environ["PEAKGUARD_LLM_ENABLED"] = "true"
from peakguard.explanations import evidence, explain
from peakguard.llm import generate
from peakguard.scenarios import load_scenario
from peakguard.simulator import Config, compare
c = compare(load_scenario("predictable_peak", 42), Config())
usage, t0, lat = {}, None, None
def provider(ctx):
    global t0, lat
    t0 = time.perf_counter()
    try:
        return generate(ctx, usage=usage)
    finally:
        lat = time.perf_counter() - t0
r = explain(c, provider=provider, use_llm=True)
print(json.dumps({"model": os.environ["PEAKGUARD_LLM_MODEL"], "mode": r["mode"], "audit": r["audit"][0],
                  "latency_s": round(lat, 2) if lat else None, **usage,
                  "rationale_present": "rationale" in r}, ensure_ascii=False))
