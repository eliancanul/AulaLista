export const MAX_PDF_BYTES = 25 * 1024 * 1024

export const FIELD_LABELS = {
  proyecto: 'Proyecto', campos_formativos: 'Campos formativos', proposito: 'Propósito',
  finalidad: 'Finalidad', metodologia: 'Metodología', escenario_proyecto: 'Escenario',
  grado: 'Grado', nivel_educativo: 'Nivel educativo', duracion_proyecto: 'Duración',
  contenidos: 'Contenidos', pda: 'Procesos de desarrollo de aprendizaje',
  ejes_articuladores: 'Ejes articuladores', inicio: 'Inicio', desarrollo: 'Desarrollo',
  cierre: 'Cierre', materiales: 'Materiales', evaluacion: 'Evaluación',
}

export const STATUS_LABELS = {
  extracted: 'Encontrado en el documento', suggested: 'Propuesta por confirmar', unknown: 'Por aclarar',
}

const QUESTIONS = {
  grado: '¿A qué grado corresponde el material?',
  nivel_educativo: '¿A qué nivel educativo corresponde el material?',
  proposito: '¿Qué quieres que practique el grupo?',
  desarrollo: '¿Qué hará el grupo durante la actividad?',
  evaluacion: '¿Cómo revisarás el trabajo realizado?',
}

const text = value => typeof value === 'string' && value.trim().length > 0
const texts = value => Array.isArray(value) && value.every(text)
const invalidResponse = () => Object.assign(new Error('Respuesta no válida'), { code: 'invalid_response' })

// This boundary verifies display safety and references, not pedagogical correctness.
export function readInterpretation(value) {
  if (!value || ![1, 2].includes(value.schema_version) || !text(value.document_id) ||
      !Array.isArray(value.source_segments) || !Array.isArray(value.fields) ||
      !texts(value.missing_questions)) throw invalidResponse()
  const sources = new Map()
  for (const segment of value.source_segments) {
    if (!segment || !text(segment.id) || !text(segment.text) ||
        !Number.isInteger(segment.page) || segment.page < 1 || sources.has(segment.id)) throw invalidResponse()
    if (value.schema_version === 2 && (
      !['text', 'heading_candidate', 'table_row_candidate'].includes(segment.kind) ||
      !Number.isSafeInteger(segment.text_start) || !Number.isSafeInteger(segment.text_end) ||
      segment.text_start < 0 || segment.text_end <= segment.text_start)) throw invalidResponse()
    sources.set(segment.id, segment)
  }
  const references = ids => texts(ids) && new Set(ids).size === ids.length && ids.every(id => sources.has(id))
  const keys = new Set()
  for (const field of value.fields) {
    if (!field || !Object.hasOwn(FIELD_LABELS, field.key) || keys.has(field.key) ||
        !Object.hasOwn(STATUS_LABELS, field.status) || typeof field.reason !== 'string' ||
        !references(field.evidence_ids)) throw invalidResponse()
    if (field.status === 'unknown' ? field.value !== null :
      (!(text(field.value) || (texts(field.value) && field.value.length > 0)) || field.evidence_ids.length === 0)) throw invalidResponse()
    keys.add(field.key)
  }
  if (keys.size !== Object.keys(FIELD_LABELS).length) throw invalidResponse()
  const draft = value.draft
  if (!draft || !['title', 'objective', 'assessment'].every(key => typeof draft[key] === 'string') ||
      ![draft.materials, draft.steps].every(items => Array.isArray(items) && items.every(item => typeof item === 'string')) || !references(draft.source_ids) ||
      !Number.isInteger(draft.revision) || draft.revision < 1 || !['pending', 'approved'].includes(draft.approval_status)) throw invalidResponse()
  const warnings = value.diagnostics?.source_warnings
  if (!Array.isArray(warnings) || warnings.some(w => !w || !text(w.message) || !Number.isInteger(w.page) || w.page < 1)) throw invalidResponse()
  return structuredClone(value)
}

export function questionsFor(interpretation) {
  return interpretation.fields
    .filter(field => Object.hasOwn(QUESTIONS, field.key) && field.status !== 'extracted')
    .map(field => ({ key: field.key, text: QUESTIONS[field.key] }))
}

export function displayValue(value) {
  return value === null ? 'No se pudo determinar' : Array.isArray(value) ? value.join(', ') : value
}

export function validateFile(file, maxBytes = MAX_PDF_BYTES) {
  if (!file || !/\.pdf$/i.test(file.name) || (file.type && file.type !== 'application/pdf')) return 'Elige un archivo PDF.'
  if (!Number.isFinite(file.size) || file.size <= 0) return 'El archivo está vacío. Elige otro PDF.'
  if (file.size > maxBytes) return `El archivo supera el límite de ${Math.floor(maxBytes / 1024 / 1024)} MB. Elige uno más pequeño.`
  return null
}

export function uploadError(error) {
  const status = error?.status
  if (status === 401 || status === 403) return { message: 'Tu sesión no permite cargar el documento. Vuelve a iniciar sesión y conserva este archivo.', retryable: false, action: 'sign-in' }
  if (status === 413 || status === 415 || status === 422) return { message: 'No se pudo leer este PDF. Revisa que no esté vacío, dañado, protegido o sea demasiado grande.', retryable: false }
  if (error?.code === 'invalid_response') return { message: 'La respuesta no contiene fuentes y campos válidos. Conserva tu archivo y solicita apoyo.', retryable: false }
  if (error?.code === 'unavailable') return { message: 'La carga todavía no está disponible. Conserva tu archivo e inténtalo más tarde.', retryable: false }
  return { message: 'No recibimos la interpretación. Comprueba tu conexión antes de volver a intentar. El documento podría haberse guardado; reintentar puede crear otra copia.', retryable: true }
}

export function createReviewSession({ upload, initialInterpretation = null, onChange = () => {}, maxBytes = MAX_PDF_BYTES } = {}) {
  let sequence = 0
  let pending
  let state = {
    phase: initialInterpretation ? 'review' : 'idle', file: null, error: null,
    interpretation: initialInterpretation ? readInterpretation(initialInterpretation) : null,
    answers: {},
  }
  const publish = changes => {
    state = { ...state, ...changes }
    onChange(state)
  }
  return {
    get state() { return state },
    selectFile(file) {
      if (state.phase === 'submitting' || state.interpretation) return false
      const message = validateFile(file, maxBytes)
      publish({ file: message ? null : file, phase: message ? 'error' : 'ready', error: message ? { message, retryable: false } : null })
      return !message
    },
    async submit() {
      if (!state.file || state.phase === 'submitting' || state.interpretation) return false
      if (state.phase === 'error' && !state.error.retryable) return false
      const request = ++sequence
      pending = new AbortController()
      publish({ phase: 'submitting', error: null })
      try {
        if (!upload) throw Object.assign(new Error('Carga no disponible'), { code: 'unavailable' })
        const interpretation = readInterpretation(await upload(state.file, { signal: pending.signal }))
        if (request !== sequence) return false
        publish({ phase: 'review', interpretation, answers: {}, error: null })
        return true
      } catch (error) {
        if (request !== sequence) return false
        publish({ phase: 'error', error: uploadError(error) })
        return false
      }
    },
    stopWaiting() {
      if (state.phase !== 'submitting') return
      sequence += 1
      pending.abort()
      publish({ phase: 'stopped', error: null })
    },
    answer(key, value) {
      if (!state.interpretation || !Object.hasOwn(FIELD_LABELS, key) || typeof value !== 'string') return
      publish({ answers: { ...state.answers, [key]: value } })
    },
    handoff() {
      if (state.phase !== 'review') return null
      return structuredClone({ interpretation: state.interpretation, answers: state.answers })
    },
    dispose() { sequence += 1; pending?.abort() },
  }
}

// S11 owns multipart encoding, same-origin identity and CSRF enforcement.
export function createInterpretationUploader(api) {
  return (file, { signal } = {}) => api.createInterpretation(file, signal)
}
