import type { ActivityContent, EditorPersistence, SavedActivity } from './activityEditor.ts';

export type DraftChanges = Pick<ActivityContent, 'title' | 'objective' | 'materials' | 'steps' | 'assessment'>;
export type DraftAPI = {
  patchDraft(id: string, request: { expected_revision: number; changes: DraftChanges }): Promise<unknown>;
  approveDraft(id: string, request: { expected_revision: number; confirm: true }): Promise<unknown>;
};

/** S11 supplies its authenticated client and the S09 response projection. */
export function createEditorPersistence(api: DraftAPI, decode: (response: unknown) => SavedActivity): EditorPersistence {
  return {
    async save(id, request) {
      const { title, objective, materials, steps, assessment } = request.content;
      return decode(await api.patchDraft(id, {
        expected_revision: request.expected_revision,
        changes: { title, objective, materials: [...materials], steps: [...steps], assessment },
      }));
    },
    async approve(id, request) {
      return decode(await api.approveDraft(id, { expected_revision: request.expected_revision, confirm: true }));
    },
  };
}
