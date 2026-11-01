import { test } from 'node:test';
import assert from 'node:assert/strict';
import { recommend } from '../lib/recommendation.mjs';
const run = (slo, cost, backlog) => ({ summary: { slo_violation_minutes: slo, cost_brl: cost, max_backlog_docs: backlog } });
test('prioriza menos violações mesmo com custo maior', () => {
  assert.equal(recommend(run(2, 1, 5), run(0, 2, 0)).policy, 'anticipatory');
});
test('em empate de SLO escolhe menor custo e explicita alternativa', () => {
  const result = recommend(run(0, 1, 0), run(0, 2, 0));
  assert.equal(result.policy, 'reactive');
  assert.match(result.reason, /custo/i);
});
test('empate completo é declarado', () => {
  assert.equal(recommend(run(0, 1, 0), run(0, 1, 0)).policy, 'tie');
});
