import test from 'node:test';
import assert from 'node:assert/strict';
import { createEditorPersistence } from '../src/features/editor/persistence.ts';

test('S07 adapter sends only editable changes and preserves optimistic revision', async () => {
  let sent;
  const persistence = createEditorPersistence({ patchDraft: async (...args) => { sent = args; return 'response'; } }, value => ({ decoded: value }));
  const response = await persistence.save('draft-1', { expected_revision: 7, content: {
    title: ' Texto ', objective: 'Observar', materials: ['Papel'], steps: ['Mirar'], assessment: 'Comentar', source_ids: ['source-1'], approval_status: 'approved',
  } });
  assert.deepEqual(sent, ['draft-1', { expected_revision: 7, changes: { title: ' Texto ', objective: 'Observar', materials: ['Papel'], steps: ['Mirar'], assessment: 'Comentar' } }]);
  assert.deepEqual(response, { decoded: 'response' });
});

test('S07 adapter uses explicit confirm true for approval', async () => {
  let sent;
  const persistence = createEditorPersistence({ approveDraft: async (...args) => { sent = args; return 'approved response'; } }, value => value);
  await persistence.approve('draft-1', { expected_revision: 8, reviewed: true });
  assert.deepEqual(sent, ['draft-1', { expected_revision: 8, confirm: true }]);
});
