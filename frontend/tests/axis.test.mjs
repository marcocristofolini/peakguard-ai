import { test } from 'node:test';
import assert from 'node:assert/strict';
import { niceTicks } from '../lib/axis.mjs';

test('réplicas usam passos inteiros e redondos', () => {
  assert.deepEqual(niceTicks(7), [0, 2, 4, 6, 8]);
});
test('backlog e demanda usam múltiplos redondos', () => {
  assert.deepEqual(niceTicks(661), [0, 200, 400, 600, 800]);
  assert.deepEqual(niceTicks(1000), [0, 250, 500, 750, 1000]);
});
test('valores pequenos nunca geram frações', () => {
  assert.deepEqual(niceTicks(2), [0, 1, 2]);
  assert.deepEqual(niceTicks(1), [0, 1]);
});
test('série vazia ou nula ainda tem eixo válido', () => {
  assert.deepEqual(niceTicks(0), [0, 1]);
  assert.deepEqual(niceTicks(Number.NaN), [0, 1]);
});
test('o topo cobre o máximo e todos os rótulos são inteiros', () => {
  for (const max of [3, 9, 13, 47, 99, 101, 333, 898, 3099, 12345]) {
    const ticks = niceTicks(max);
    assert.ok(ticks.at(-1) >= max, `topo cobre ${max}`);
    assert.ok(ticks.length >= 2 && ticks.length <= 6, `quantidade de rótulos para ${max}`);
    assert.ok(ticks.every(Number.isInteger), `inteiros para ${max}`);
  }
});
