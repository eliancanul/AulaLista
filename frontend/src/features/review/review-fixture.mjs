import { FIELD_LABELS } from './review-model.mjs'

export const uncertainInterpretation = {
  schema_version: 1,
  document_id: 'demostracion-s12',
  source_segments: [{ id: 'fragmento-1', page: 1, text: '3ro. Proyecto: Cuidamos el agua. Propósito: Reconocer usos cotidianos del agua. En equipos, dibujen cómo usan el agua en casa.' }],
  fields: Object.keys(FIELD_LABELS).map(key => {
    const values = { proyecto: 'Cuidamos el agua', proposito: 'Reconocer usos cotidianos del agua', grado: '3ro', desarrollo: 'En equipos, dibujen cómo usan el agua en casa.' }
    const value = values[key] ?? null
    return { key, value, status: key === 'grado' ? 'suggested' : value ? 'extracted' : 'unknown', evidence_ids: value ? ['fragmento-1'] : [], reason: key === 'grado' ? 'El grado no indica si corresponde a primaria o secundaria.' : value ? '' : 'El fragmento no lo indica.' }
  }),
  missing_questions: ['¿A qué nivel educativo corresponde el material?', '¿Cómo se revisará el trabajo realizado?'],
  draft: { title: 'Cuidamos el agua', objective: 'Reconocer usos cotidianos del agua', materials: [], steps: ['En equipos, dibujen cómo usan el agua en casa.'], assessment: '', source_ids: ['fragmento-1'], revision: 1, approval_status: 'pending', status: 'needs_review' },
  diagnostics: { method: 'local_source_interpreter', provider_status: 'not_requested', attempts: 0, errors: [], model_winner: null, source_page_count: 1, source_warnings: [] },
}
