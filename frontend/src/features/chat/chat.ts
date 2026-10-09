export type SourceSegment = { id: string; text: string; page?: number | null };
export type ChatReply = {
  interpretation_id: string;
  message: string;
  source_ids: string[];
  proposals: unknown[];
  mode: 'source_lookup';
  applies_changes: false;
};
export type ChatTransport = (request: { interpretation_id: string; message: string }) => Promise<unknown>;
export type ChatTurn = { question: string; answer: string; sources: SourceSegment[] };
export type ChatState = {
  input: string;
  status: 'idle' | 'loading' | 'failed';
  error: string | null;
  retryable: boolean;
  turns: ChatTurn[];
};

const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));

function readReply(raw: unknown, id: string, sources: SourceSegment[]): ChatTurn {
  const reply = raw as ChatReply;
  if (!reply || reply.interpretation_id !== id || typeof reply.message !== 'string' || !reply.message.trim() ||
      reply.mode !== 'source_lookup' || reply.applies_changes !== false ||
      !Array.isArray(reply.proposals) || reply.proposals.length !== 0 || !Array.isArray(reply.source_ids) ||
      !reply.source_ids.every(key => typeof key === 'string' && sources.some(source => source.id === key))) {
    throw { retryable: false };
  }
  return { question: '', answer: reply.message,
    sources: [...new Set(reply.source_ids)].map(key => copy(sources.find(source => source.id === key)!)) };
}

export function createTeacherChat(id: string, sources: SourceSegment[], transport: ChatTransport) {
  const evidence = copy(sources);
  const state: ChatState = { input: '', status: 'idle', error: null, retryable: false, turns: [] };
  const listeners = new Set<(state: ChatState) => void>();
  let request = 0;
  let failedQuestion: string | null = null;
  let disposed = false;
  const snapshot = () => copy(state);
  const publish = () => { for (const listener of listeners) listener(snapshot()); };

  async function send(question: string) {
    if (disposed || state.status === 'loading' || !question.trim() || question.length > 4000) return false;
    const token = ++request;
    state.status = 'loading';
    state.error = null;
    state.retryable = false;
    publish();
    try {
      const raw = await transport({ interpretation_id: id, message: question });
      if (disposed || request !== token) return false;
      const turn = readReply(raw, id, evidence);
      state.turns.push({ ...turn, question });
      if (state.input === question) state.input = '';
      failedQuestion = null;
      state.status = 'idle';
      return true;
    } catch (cause) {
      if (disposed || request !== token) return false;
      const failure = cause as { status?: number; retryable?: boolean } | null;
      const status = failure?.status;
      state.retryable = failure?.retryable !== false &&
        (status === undefined || status === 429 || status >= 500);
      state.error = status === 401 || status === 403
        ? 'No se pudo consultar. Revisa tu acceso e inicia sesión de nuevo si es necesario. Tu texto sigue aquí.'
        : 'No se pudo completar la consulta. Tu pregunta y tu actividad se conservan.';
      failedQuestion = question;
      state.status = 'failed';
      return false;
    } finally {
      if (!disposed && request === token) publish();
    }
  }

  return {
    snapshot,
    subscribe(listener: (state: ChatState) => void) {
      listeners.add(listener);
      listener(snapshot());
      return () => { listeners.delete(listener); };
    },
    setInput(value: string) { state.input = value; publish(); },
    send: () => send(state.input),
    retry: () => failedQuestion && state.retryable ? send(failedQuestion) : Promise.resolve(false),
    dispose() { disposed = true; request++; listeners.clear(); },
  };
}
