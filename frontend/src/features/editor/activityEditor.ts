export type ActivityContent = {
  title: string;
  objective: string;
  materials: string[];
  steps: string[];
  assessment: string;
  source_ids: string[];
};
export type ApprovedActivity = { revision: number; content: ActivityContent };
export type SavedActivity = {
  id: string;
  revision: number;
  status: 'draft' | 'approved';
  content: ActivityContent;
  approved: ApprovedActivity | null;
};
export type EditorPersistence = {
  save(id: string, request: { expected_revision: number; content: ActivityContent }): Promise<SavedActivity>;
  approve(id: string, request: { expected_revision: number; reviewed: true }): Promise<SavedActivity>;
};
export type EditorState = {
  saved: SavedActivity;
  draft: ActivityContent;
  approved: ApprovedActivity | null;
  remote: SavedActivity | null;
  pending: 'save' | 'approve' | null;
  error: string | null;
  conflict: boolean;
  dirty: boolean;
  isApproved: boolean;
  needsLeaveWarning: boolean;
};
const fields = ['title', 'objective', 'materials', 'steps', 'assessment', 'source_ids'] as const;
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const equal = (left: ActivityContent, right: ActivityContent) => fields.every(key => JSON.stringify(left[key]) === JSON.stringify(right[key]));

function validateContent(value: ActivityContent) {
  if (!value || ['title', 'objective', 'assessment'].some(key => typeof value[key as keyof ActivityContent] !== 'string') ||
    ['materials', 'steps', 'source_ids'].some(key => !Array.isArray(value[key as keyof ActivityContent]) ||
      !(value[key as 'materials'] as unknown[]).every(item => typeof item === 'string'))) {
    throw new Error('La respuesta del servidor no contiene una actividad válida.');
  }
}

function validateSaved(value: SavedActivity, id?: string) {
  if (!value || typeof value.id !== 'string' || !value.id || (id && value.id !== id) ||
    !Number.isSafeInteger(value.revision) || value.revision < 0 || !['draft', 'approved'].includes(value.status)) {
    throw new Error('La respuesta del servidor no corresponde a esta actividad.');
  }
  validateContent(value.content);
  if (value.approved !== null) {
    if (!value.approved || !Number.isSafeInteger(value.approved.revision) || value.approved.revision < 0 || value.approved.revision > value.revision) {
      throw new Error('La versión aprobada no es válida.');
    }
    validateContent(value.approved.content);
  }
  if (value.status === 'approved' && (!value.approved || !equal(value.content, value.approved.content) || value.approved.revision !== value.revision)) {
    throw new Error('Falta la confirmación de la versión aprobada.');
  }
}

export function createActivityEditor(initial: SavedActivity, persistence: EditorPersistence) {
  validateSaved(initial);
  let saved = copy(initial);
  let draft = copy(initial.content);
  let approved = copy(initial.approved);
  let remote: SavedActivity | null = null;
  let pending: EditorState['pending'] = null;
  let error: string | null = null;
  let conflict = false;
  const listeners = new Set<(state: EditorState) => void>();

  function snapshot(): EditorState {
    const dirty = !equal(draft, saved.content);
    return copy({ saved, draft, approved, remote, pending, error, conflict, dirty,
      isApproved: !dirty && !conflict && saved.status === 'approved',
      needsLeaveWarning: dirty || pending !== null || conflict });
  }
  function publish() { for (const listener of listeners) listener(snapshot()); }
  function fail(message: string) { error = message; publish(); return false; }

  function receive(value: SavedActivity) {
    try { validateSaved(value, saved.id); } catch (cause) { return fail((cause as Error).message); }
    if (value.revision < Math.max(saved.revision, remote?.revision ?? 0)) return false;
    if (JSON.stringify(value) === JSON.stringify(saved)) return true;
    remote = copy(value);
    conflict = true;
    return fail('Hay otra versión guardada. Compara los textos antes de decidir cuál conservar.');
  }

  async function persist(kind: 'save' | 'approve', reviewed = false) {
    if (pending) return false;
    if (conflict) return fail('Resuelve la diferencia con la versión guardada antes de continuar.');
    const sent = copy(draft);
    const revision = saved.revision;
    if (kind === 'approve' && (!reviewed || !equal(draft, saved.content) || !draft.source_ids.length)) {
      return fail('Guarda tus cambios, verifica las fuentes y confirma tu revisión antes de aprobar.');
    }
    if (kind === 'save' && equal(draft, saved.content)) return true;
    pending = kind;
    error = null;
    publish();
    try {
      const result = kind === 'save'
        ? await persistence.save(saved.id, { expected_revision: revision, content: copy(sent) })
        : await persistence.approve(saved.id, { expected_revision: revision, reviewed: true });
      validateSaved(result, saved.id);
      if (result.revision < revision || (kind === 'save' && result.revision === revision) || !equal(result.content, sent) ||
        (kind === 'save' && result.status !== 'draft') || (kind === 'approve' && result.status !== 'approved')) {
        throw new Error('El servidor devolvió una versión inesperada. Tu texto sigue aquí; consulta la versión guardada.');
      }
      saved = copy(result);
      approved = copy(result.approved);
      if (remote && remote.revision <= saved.revision && equal(remote.content, saved.content)) {
        remote = null;
        conflict = false;
      }
      if (!conflict) error = null;
      // The draft stays independent from the request snapshot while teachers type.
      return true;
    } catch (cause) {
      const failure = (cause && typeof cause === 'object' ? cause : {}) as { status?: number; current?: SavedActivity };
      if (failure.status === 409 || failure.status === 412) {
        conflict = true;
        if (failure.current) receive(failure.current);
        error = 'Otra versión cambió en el servidor. Tu texto sigue aquí. Carga la versión guardada para compararla.';
      } else {
        error = kind === 'save'
          ? 'No se pudo confirmar el guardado. Tu texto sigue aquí. Reintenta o descarga una copia del borrador.'
          : 'No se pudo confirmar la aprobación. Tu texto sigue aquí. Consulta el estado guardado antes de reintentar.';
      }
      return false;
    } finally {
      pending = null;
      publish();
    }
  }

  return {
    snapshot,
    subscribe(listener: (state: EditorState) => void) {
      listeners.add(listener);
      listener(snapshot());
      return () => { listeners.delete(listener); };
    },
    edit<K extends keyof ActivityContent>(key: K, value: ActivityContent[K]) {
      const next = { ...draft, [key]: copy(value) };
      validateContent(next);
      draft = next;
      publish();
    },
    receive,
    resolveRemote(choice: 'keep-local' | 'use-remote') {
      if (pending || !remote) return false;
      saved = copy(remote);
      approved = copy(remote.approved);
      if (choice === 'use-remote') draft = copy(remote.content);
      remote = null;
      conflict = false;
      error = null;
      publish();
      return true;
    },
    save: () => persist('save'),
    approve: (reviewed: boolean) => persist('approve', reviewed),
    recoveryJSON() {
      return JSON.stringify({ format: 'aulalista-activity-draft-v1', id: saved.id,
        base_revision: saved.revision, status: 'draft', content: copy(draft) }, null, 2);
    },
  };
}
