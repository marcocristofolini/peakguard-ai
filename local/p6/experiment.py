"""Teste local com captura observada; não aceita kubeconfig/contexto externos."""
import json
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from peakguard.scenarios import Scenario
from peakguard.simulator import Config, compare

CMD = ['kubectl', '--kubeconfig', str(ROOT / 'local/p6/.kubeconfig'), '--context', 'kind-peakguard-p6']
OUT = ROOT / 'evidence/p6'

def kube(*args):
    return subprocess.check_output(CMD + list(args), text=True, timeout=30)

def query(expression):
    path = '/api/v1/namespaces/peakguard-p6/services/prometheus:9090/proxy/api/v1/query?query=' + urllib.parse.quote(expression, safe='')
    return json.loads(kube('get', '--raw', path))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    kube('-n', 'peakguard-p6', 'delete', 'job', 'load', '--ignore-not-found=true')
    kube('apply', '-f', str(ROOT / 'local/p6/load.yaml'))
    start = time.time()
    samples = []
    for tick in range(16):
        deployment = json.loads(kube('-n', 'peakguard-p6', 'get', 'deployment', 'documents', '-o', 'json'))
        sample = {'elapsed_seconds': time.time()-start, 'ready_replicas': deployment['status'].get('readyReplicas', 0),
                  'desired_replicas': deployment['spec']['replicas'],
                  'queries': {key: query(expr) for key, expr in {
                      'submitted': 'sum(documents_submitted_total)', 'processed': 'sum(documents_processed_total)',
                      'backlog': 'sum(documents_backlog)', 'targets': 'sum(up{job="documents"})',
                      'throughput_docs_per_second': 'sum(rate(documents_processed_total[30s]))',
                      'wait_max_seconds': 'max(documents_queue_wait_max_seconds)'}.items()}}
        samples.append(sample)
        print(json.dumps({'sample': tick, 'ready': sample['ready_replicas']}), flush=True)
        if tick < 15:
            time.sleep(10)
    kube('-n', 'peakguard-p6', 'wait', '--for=condition=complete', 'job/load', '--timeout=60s')
    logs = kube('-n', 'peakguard-p6', 'logs', 'job/load')
    load = [json.loads(line) for line in logs.splitlines() if line.startswith('{')]
    report = {'labels': {'metrics': 'observed', 'load': 'synthetic', 'cost': 'estimated'},
              'kubernetes_version': json.loads(kube('version', '-o', 'json')),
              'samples': samples, 'load': load,
              'hpa': json.loads(kube('-n', 'peakguard-p6', 'get', 'hpa', 'documents', '-o', 'json')),
              'estimated_cost_brl': sum(a['ready_replicas'] * (b['elapsed_seconds']-a['elapsed_seconds'])/3600*1.2 for a,b in zip(samples,samples[1:])),
              'price_assumption_brl_per_replica_hour': 1.2,
              'cost_method': 'left-hand integration of sampled ready replicas; excludes node, pending pods and monitoring'}
    (OUT / 'observed.json').write_text(json.dumps(report, indent=2)+'\n')
    rates = tuple((12 if 2 <= i < 11 else 1)*60 for i in range(13))
    # Referência idealizada: mesma carga nominal, capacidade de 300 doc/min/réplica não calibrada.
    scenario = Scenario('p6_controlled_peak', 0, rates, rates)
    simulated = compare(scenario, Config(tick_minutes=1/6, capacity_docs_per_minute_per_replica=300, max_replicas=4))
    (OUT / 'simulated.json').write_text(json.dumps(simulated, indent=2)+'\n')
    verify(report)


def verify(report):
    assert len(report['load']) == 13, 'Carga incompleta'
    samples = report['samples']
    assert any(s['ready_replicas'] > 1 for s in samples), 'HPA não escalou'
    def value(sample, key):
        results = sample['queries'][key]['data']['result']
        return float(results[0]['value'][1]) if results else 0
    assert all(value(s, 'targets') > 0 for s in samples), 'Prometheus não coletou targets'
    assert value(samples[-1], 'processed') > 0, 'Nenhum processamento observado'



if __name__ == '__main__':
    main()
