import { describe, expect, it, vi } from 'vitest';
import { createAPI, readCSRF } from '../src/api/client';
import { interpretation } from './s11-fixtures';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

describe('same-origin API contract', () => {
  it('sends the session and CSRF token with exactly the revision and editable fields', async () => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(json(interpretation().draft));
    const api = createAPI({ fetch: transport, csrf: () => 'masked-token' });
    const changes = { title: ' Texto exacto\n', objective: '', materials: [], steps: [], assessment: '' };
    await api.patchDraft('id / separado', { expected_revision: 7, changes });
    const [url, options] = transport.mock.calls[0];
    expect(url).toBe('/api/v1/drafts/id%20%2F%20separado');
    expect(options).toMatchObject({ method: 'PATCH', credentials: 'same-origin', redirect: 'error', cache: 'no-store' });
    expect(new Headers(options?.headers).get('X-CSRFToken')).toBe('masked-token');
    expect(JSON.parse(String(options?.body))).toEqual({ expected_revision: 7, changes });
  });

  it('does not send any mutation when CSRF is unavailable', async () => {
    const transport = vi.fn<typeof fetch>();
    const api = createAPI({ fetch: transport, csrf: () => null });
    await expect(api.approveDraft('id', { expected_revision: 1, confirm: true })).rejects.toMatchObject({ status: 403, code: 'csrf_missing' });
    expect(transport).not.toHaveBeenCalled();
  });

  it('uses multipart file without overriding its boundary', async () => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(json(interpretation(), 201));
    const api = createAPI({ fetch: transport, csrf: () => 'csrf' });
    const file = new File(['%PDF-fixture'], 'material.pdf', { type: 'application/pdf' });
    await api.createInterpretation(file);
    const [url, options] = transport.mock.calls[0];
    expect(url).toBe('/api/v1/interpretations');
    expect(new Headers(options?.headers).has('Content-Type')).toBe(false);
    expect((options?.body as FormData).get('file')).toBe(file);
  });

  it.each([401, 403, 404, 409, 413, 415, 422, 503, 504])('retains status %s without displaying raw server content or retrying', async status => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(json({ private: 'secret fixture' }, status));
    const api = createAPI({ fetch: transport, csrf: () => 'csrf' });
    await expect(api.getInterpretation('id')).rejects.toMatchObject({ status });
    expect(transport).toHaveBeenCalledTimes(1);
    try { await createAPI({ fetch: async () => json({}, status) }).getInterpretation('id'); }
    catch (error) { expect(String(error)).not.toContain('secret fixture'); }
  });

  it('rejects a login HTML response and a response for another document', async () => {
    const api = createAPI({ fetch: async () => new Response('<html>Login</html>', { headers: { 'Content-Type': 'text/html' } }) });
    await expect(api.getInterpretation('id')).rejects.toMatchObject({ code: 'invalid_response' });
    const wrong = createAPI({ fetch: async () => json(interpretation()) });
    await expect(wrong.getInterpretation('other')).rejects.toMatchObject({ code: 'wrong_document' });
  });

  it('reads the rendered masked token before the cookie and never sends GET CSRF', async () => {
    document.head.innerHTML = '<meta name="csrf-token" content="masked">';
    document.cookie = 'csrftoken=cookie';
    expect(readCSRF()).toBe('masked');
    document.head.innerHTML = '';
    expect(readCSRF()).toBe('cookie');
    const transport = vi.fn<typeof fetch>().mockResolvedValue(json(interpretation()));
    await createAPI({ fetch: transport }).getInterpretation('documento-ejemplo');
    expect(new Headers(transport.mock.calls[0][1]?.headers).has('X-CSRFToken')).toBe(false);
  });

  it('reports disconnection in Spanish without automatic resubmission', async () => {
    const transport = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(createAPI({ fetch: transport }).getInterpretation('id')).rejects.toMatchObject({ status: 0, message: 'No se pudo conectar con el nodo local. Tu texto se conserva.' });
    expect(transport).toHaveBeenCalledTimes(1);
  });

  it('does not expose malformed private response bodies in parser errors', async () => {
    const api = createAPI({ fetch: async () => new Response('private fixture is not JSON', { headers: { 'Content-Type': 'application/json' } }) });
    await expect(api.getInterpretation('id')).rejects.toMatchObject({ status: 502, message: 'El servidor no devolvió una respuesta válida.' });
  });
});
