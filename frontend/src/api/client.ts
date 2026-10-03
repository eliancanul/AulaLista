import { decodeDraft, decodeInterpretation, type DraftChanges } from '../contracts/interpretation';

const messages: Record<number, string> = {
  401: 'Inicia sesión para continuar. Tu texto sigue aquí.',
  403: 'No se pudo autorizar la solicitud. Revisa tu sesión y tus permisos.',
  404: 'No se encontró este documento o no tienes acceso.',
  409: 'El borrador cambió. Compara la versión guardada antes de continuar.',
  413: 'El archivo supera el tamaño máximo permitido.',
  415: 'Selecciona un documento PDF.',
  422: 'Revisa los datos antes de volver a enviarlos.',
  503: 'El servicio no está disponible. Inténtalo más tarde.',
  504: 'La interpretación tardó demasiado. Puedes volver a intentarlo.',
};

export class APIError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

export function readCSRF(): string | null {
  const masked = document.querySelector<HTMLInputElement>('input[name=csrfmiddlewaretoken]')?.value ||
    document.querySelector<HTMLMetaElement>('meta[name=csrf-token]')?.content;
  if (masked) return masked;
  const cookie = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith('csrftoken='));
  try { return cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : null; }
  catch { return null; }
}

export function createAPI(options: { fetch?: typeof fetch; csrf?: () => string | null } = {}) {
  const transport = options.fetch ?? globalThis.fetch.bind(globalThis);
  const csrf = options.csrf ?? readCSRF;

  async function request(path: string, method: string, body?: FormData | object, signal?: AbortSignal) {
    const headers = new Headers({ Accept: 'application/json' });
    if (method !== 'GET') {
      const token = csrf();
      if (!token) throw new APIError(403, 'csrf_missing', 'Abre tu sesión docente antes de enviar cambios. Tu texto se conserva.');
      headers.set('X-CSRFToken', token);
    }
    const multipart = body instanceof FormData;
    if (body && !multipart) headers.set('Content-Type', 'application/json');
    let response: Response;
    try {
      response = await transport(`/api/v1${path}`, {
        method, headers, credentials: 'same-origin', redirect: 'error', cache: 'no-store', signal,
        body: body ? multipart ? body : JSON.stringify(body) : undefined,
      });
    } catch (error) {
      if (signal?.aborted) throw error;
      throw new APIError(0, 'network_unavailable', 'No se pudo conectar con el nodo local. Tu texto se conserva.');
    }
    if (!response.ok) {
      throw new APIError(response.status, `http_${response.status}`, messages[response.status] ?? 'No se pudo completar la solicitud. Tu texto se conserva.');
    }
    if (!response.headers.get('content-type')?.includes('application/json')) {
      throw new APIError(502, 'invalid_response', 'El servidor no devolvió una respuesta válida.');
    }
    try { return await response.json() as unknown; }
    catch { throw new APIError(502, 'invalid_response', 'El servidor no devolvió una respuesta válida.'); }
  }

  const idPath = (id: string) => {
    if (!id || id === '.' || id === '..') throw new Error('Falta una referencia válida del documento.');
    return encodeURIComponent(id);
  };

  return {
    async listInterpretations() {
      const rows = await request('/interpretations', 'GET');
      if (!Array.isArray(rows)) throw new Error('Lista de documentos no válida.');
      return rows.map(row => ({ document_id: String(row.document_id), created_at: String(row.created_at), draft: decodeDraft(row.draft) }));
    },
    async history(id: string) {
      const rows = await request(`/drafts/${idPath(id)}/history`, 'GET');
      if (!Array.isArray(rows)) throw new Error('Historial no válido.');
      return rows.map(row => ({ draft: decodeDraft(row.draft), action: String(row.action), created_at: String(row.created_at) }));
    },
    async createInterpretation(file: File, signal?: AbortSignal) {
      const data = new FormData();
      data.set('file', file);
      return decodeInterpretation(await request('/interpretations', 'POST', data, signal));
    },
    async getInterpretation(id: string, signal?: AbortSignal) {
      const result = decodeInterpretation(await request(`/interpretations/${idPath(id)}`, 'GET', undefined, signal));
      if (result.document_id !== id) throw new APIError(502, 'wrong_document', 'El servidor devolvió otro documento.');
      return result;
    },
    async patchDraft(id: string, body: { expected_revision: number; changes: DraftChanges }) {
      return decodeDraft(await request(`/drafts/${idPath(id)}`, 'PATCH', body));
    },
    async approveDraft(id: string, body: { expected_revision: number; confirm: true }) {
      return decodeDraft(await request(`/drafts/${idPath(id)}/approve`, 'POST', body));
    },
    chat(body: { interpretation_id: string; message: string }, signal?: AbortSignal) {
      return request('/chat', 'POST', body, signal);
    },
  };
}

export type AulaAPI = ReturnType<typeof createAPI>;
