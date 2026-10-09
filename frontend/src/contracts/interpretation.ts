export interface ActivityContent {
  title: string;
  objective: string;
  materials: string[];
  steps: string[];
  assessment: string;
  source_ids: string[];
}

export interface DraftResponse extends ActivityContent {
  id: string;
  revision: number;
  approval_status: 'pending' | 'approved';
  status: string;
}

export interface Interpretation {
  schema_version: 1 | 2;
  document_id: string;
  source_segments: { id: string; text: string; page: number }[];
  fields: {
    key: string;
    value: string | string[] | null;
    status: 'extracted' | 'suggested' | 'unknown';
    evidence_ids: string[];
    reason: string;
  }[];
  missing_questions: string[];
  draft: DraftResponse;
  diagnostics?: Record<string, unknown>;
}

export type DraftChanges = Pick<ActivityContent, 'title' | 'objective' | 'materials' | 'steps' | 'assessment'>;

export interface SavedActivity {
  id: string;
  revision: number;
  status: 'draft' | 'approved';
  content: ActivityContent;
  approved: { revision: number; content: ActivityContent } | null;
}

function invalid(): never {
  throw new Error('La respuesta del servidor no tiene el formato esperado. Tu trabajo se conserva.');
}

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) invalid();
  return value as Record<string, unknown>;
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string');
}

export function decodeDraft(value: unknown): DraftResponse {
  const draft = object(value);
  if (typeof draft.id !== 'string' || !draft.id || !Number.isSafeInteger(draft.revision) ||
      Number(draft.revision) < 1 || !['pending', 'approved'].includes(String(draft.approval_status)) ||
      typeof draft.status !== 'string' ||
      !['title', 'objective', 'assessment'].every(key => typeof draft[key] === 'string') ||
      !['materials', 'steps', 'source_ids'].every(key => strings(draft[key]))) invalid();
  return structuredClone(draft) as unknown as DraftResponse;
}

export function decodeInterpretation(value: unknown): Interpretation {
  const data = object(value);
  if (![1, 2].includes(Number(data.schema_version)) || typeof data.schema_version !== 'number' || typeof data.document_id !== 'string' || !data.document_id ||
      !Array.isArray(data.source_segments) || !Array.isArray(data.fields) || !strings(data.missing_questions)) invalid();
  const sourceIds = new Set<string>();
  for (const item of data.source_segments) {
    const source = object(item);
    if (typeof source.id !== 'string' || !source.id || sourceIds.has(source.id) ||
        typeof source.text !== 'string' || !Number.isSafeInteger(source.page) || Number(source.page) < 1) invalid();
    if (data.schema_version === 2 && (
        !['text', 'heading_candidate', 'table_row_candidate'].includes(String(source.kind)) ||
        !Number.isSafeInteger(source.text_start) || !Number.isSafeInteger(source.text_end) ||
        Number(source.text_start) < 0 || Number(source.text_end) <= Number(source.text_start))) invalid();
    sourceIds.add(source.id);
  }
  for (const item of data.fields) {
    const field = object(item);
    if (typeof field.key !== 'string' || typeof field.reason !== 'string' ||
        !['extracted', 'suggested', 'unknown'].includes(String(field.status)) ||
        !(field.value === null || typeof field.value === 'string' || strings(field.value)) ||
        !strings(field.evidence_ids) || field.evidence_ids.some(id => !sourceIds.has(id)) ||
        (field.status === 'unknown' ? field.value !== null : field.value === null || !field.evidence_ids.length)) invalid();
  }
  const draft = decodeDraft(data.draft);
  if (draft.source_ids.some(id => !sourceIds.has(id))) invalid();
  return structuredClone({ ...data, draft }) as unknown as Interpretation;
}

export function toSavedActivity(value: unknown, previous: SavedActivity['approved'] = null): SavedActivity {
  const draft = decodeDraft(value);
  const { title, objective, materials, steps, assessment, source_ids } = draft;
  const content = { title, objective, materials, steps, assessment, source_ids };
  return {
    id: draft.id,
    revision: draft.revision,
    status: draft.approval_status === 'approved' ? 'approved' : 'draft',
    content,
    approved: draft.approval_status === 'approved'
      ? { revision: draft.revision, content: structuredClone(content) }
      : previous ? structuredClone(previous) : null,
  };
}
