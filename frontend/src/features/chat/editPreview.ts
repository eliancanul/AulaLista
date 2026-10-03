export type EditableContent = {
  title: string;
  objective: string;
  materials: string[];
  steps: string[];
  assessment: string;
};
export type DraftContext = { id: string; revision: number; content: EditableContent };
export type EditProposal = {
  id: string;
  base: DraftContext;
  changes: Partial<EditableContent>;
  source_ids: string[];
};
export const editLabels: Record<keyof EditableContent, string> = {
  title: 'Título', objective: 'Objetivo', materials: 'Materiales', steps: 'Pasos', assessment: 'Evaluación',
};
const fields = Object.keys(editLabels) as (keyof EditableContent)[];
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const same = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

function validField(key: string, value: unknown): boolean {
  return key === 'materials' || key === 'steps'
    ? Array.isArray(value) && value.every(item => typeof item === 'string')
    : fields.includes(key as keyof EditableContent) && typeof value === 'string';
}

export function createEditPreview(raw: EditProposal, sourceIds: string[]) {
  if (!raw || typeof raw.id !== 'string' || !raw.id || !raw.base ||
      typeof raw.base.id !== 'string' || !raw.base.id || !Number.isSafeInteger(raw.base.revision) || raw.base.revision < 1 ||
      !raw.base.content || !fields.every(key => validField(key, raw.base.content[key])) ||
      !raw.changes || !Object.keys(raw.changes).length ||
      !Object.entries(raw.changes).every(([key, value]) => validField(key, value)) ||
      !Array.isArray(raw.source_ids) || !raw.source_ids.length ||
      !raw.source_ids.every(id => typeof id === 'string' && sourceIds.includes(id))) {
    throw new Error('No hay suficiente fuente local o la propuesta no es válida. Tu actividad no cambió.');
  }
  const proposal = copy(raw);
  let decided = false;
  const rows = fields.filter(key => key in proposal.changes && !same(proposal.base.content[key], proposal.changes[key]))
    .map(key => ({ key, label: editLabels[key], before: copy(proposal.base.content[key]), after: copy(proposal.changes[key]!) }));
  if (!rows.length) throw new Error('La propuesta no contiene cambios.');
  function isCurrent(current: DraftContext) {
    return current.id === proposal.base.id && current.revision === proposal.base.revision &&
      fields.every(key => same(current.content[key], proposal.base.content[key]));
  }
  return {
    rows: () => copy(rows),
    isCurrent,
    accept(current: DraftContext) {
      if (decided || !isCurrent(current)) return null;
      decided = true;
      return copy({ proposal_id: proposal.id, base: proposal.base, changes: proposal.changes });
    },
    reject() {
      if (decided) return false;
      decided = true;
      return true;
    },
  };
}
