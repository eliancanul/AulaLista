import type { Interpretation } from '../src/contracts/interpretation';

export function interpretation(): Interpretation {
  return {
    schema_version: 1,
    document_id: 'documento-ejemplo',
    source_segments: [{ id: 'p1', text: 'Grado: 3ro. Usar papel para comparar las figuras.', page: 1 }],
    fields: [{ key: 'grado', value: '3ro', status: 'extracted', evidence_ids: ['p1'], reason: '' },
      { key: 'nivel_educativo', value: null, status: 'unknown', evidence_ids: [], reason: 'No está indicado.' },
      ...['proyecto', 'campos_formativos', 'proposito', 'finalidad', 'metodologia', 'escenario_proyecto', 'duracion_proyecto', 'contenidos', 'pda', 'ejes_articuladores', 'inicio', 'desarrollo', 'cierre', 'materiales', 'evaluacion'].map(key => ({ key, value: null, status: 'unknown' as const, evidence_ids: [], reason: 'Pendiente.' }))],
    missing_questions: ['¿Cuál es el nivel educativo?'],
    diagnostics: { source_warnings: [] },
    draft: {
      id: 'documento-ejemplo', revision: 1, approval_status: 'pending', status: 'needs_review',
      title: 'Figuras', objective: 'Comparar figuras.', materials: ['Papel'], steps: ['Comparar.'],
      assessment: 'Explicar las diferencias.', source_ids: ['p1'],
    },
  };
}
