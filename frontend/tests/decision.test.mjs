import { test } from 'node:test';
import assert from 'node:assert/strict';
import { interpretDecision } from '../lib/decision.mjs';

test('apresenta aprovação determinística sem sugerir execução automática', () => {
  const decision = interpretDecision({
    mode: 'offline',
    proposal: { policy: 'anticipatory' },
    explanation: 'Alternativa validada: anticipatory.',
    execution_allowed: false,
  });
  assert.equal(decision.status, 'approved');
  assert.equal(decision.policy, 'anticipatory');
  assert.match(decision.title, /Antecipativa/);
  assert.match(decision.reason, /validada/);
});

test('não recomenda política quando o validador se abstém', () => {
  const decision = interpretDecision({
    mode: 'offline',
    proposal: null,
    explanation: 'Nenhuma alternativa segura.',
    execution_allowed: false,
  });
  assert.equal(decision.status, 'abstained');
  assert.equal(decision.policy, null);
  assert.match(decision.title, /Nenhuma política/);
});

test('falha do backend não vira aprovação presumida', () => {
  const decision = interpretDecision(null);
  assert.equal(decision.status, 'unavailable');
  assert.equal(decision.policy, null);
});

test('nunca apresenta autorização para execução quando backend indica permissão', () => {
  const decision = interpretDecision({
    mode: 'offline',
    proposal: { policy: 'reactive' },
    explanation: 'Aprovada.',
    execution_allowed: true,
  });
  assert.equal(decision.status, 'unavailable');
  assert.equal(decision.policy, null);
});
