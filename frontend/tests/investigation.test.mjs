import { test } from 'node:test';
import assert from 'node:assert/strict';
import { investigationLog, clock } from '../lib/investigation.mjs';

const tick = (time, replicas, backlog, violated = false) => ({
  time_minutes: time, active_replicas: replicas, backlog_docs: backlog, slo_violated: violated,
});
const run = (...ticks) => ({ ticks });

test('registra escala, violação e pico de fila em ordem de tempo', () => {
  const reactive = run(tick(0, 1, 0), tick(5, 1, 300, true), tick(6, 4, 661, true), tick(9, 4, 0));
  const anticipatory = run(tick(0, 1, 0), tick(3, 4, 0), tick(6, 4, 20));
  const log = investigationLog(reactive, anticipatory);
  assert.deepEqual(log.map((l) => l.time), [...log.map((l) => l.time)].sort((a, b) => a - b));
  assert.deepEqual(log.map((l) => [l.time, l.tone]), [
    [3, 'anticipatory'],
    [5, 'risk'],
    [6, 'reactive'],
    [6, 'reactive'],
    [6, 'anticipatory'],
  ]);
  assert.match(log.find((l) => l.tone === 'risk').text, /reativa viola o SLO/);
  assert.match(log.find((l) => /pico/.test(l.text) && l.tone === 'reactive').text, /661 doc/);
});

test('sem violação nem fila, não inventa evidência', () => {
  const flat = run(tick(0, 2, 0), tick(1, 2, 0));
  assert.deepEqual(investigationLog(flat, flat), []);
});

test('tolera execuções ausentes ou vazias', () => {
  assert.deepEqual(investigationLog(undefined, run()), []);
});

test('relógio relativo com dois dígitos', () => {
  assert.equal(clock(0), 't+00min');
  assert.equal(clock(8.5), 't+08min');
  assert.equal(clock(23), 't+23min');
});
