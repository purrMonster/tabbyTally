import { test } from 'node:test';
import assert from 'node:assert/strict';
import { nextRange } from '../src/checkpoint.js';
test('first activation skips existing mail', () => {
  assert.equal(nextRange(undefined, { uidValidity: 7n, uidNext: 101 }).last, 100);
});
test('restart catches up independent of read flags', () => {
  assert.equal(nextRange({ uid_validity: '7', last_uid: '100' }, { uidValidity: 7n, uidNext: 104 }).range, '101:103');
});
test('empty tail does not issue a reversed IMAP range', () => {
  assert.equal(nextRange({ uid_validity: '7', last_uid: '100' }, { uidValidity: 7n, uidNext: 101 }).range, null);
});
test('mailbox reset fails closed instead of skipping mail', () => {
  assert.throws(() => nextRange({ uid_validity: '7', last_uid: '100' }, { uidValidity: 8n, uidNext: 2 }), /UIDVALIDITY/);
});
