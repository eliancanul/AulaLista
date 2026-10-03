import { afterEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import App from '../src/App.vue';
import { features } from '../src/features';
import { createAPI } from '../src/api/client';
import { createAulaRouter } from '../src/router';
import { shellKey, type ShellServices } from '../src/shell';
import { interpretation } from './s11-fixtures';

const wrappers: VueWrapper[] = [];
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); document.body.innerHTML = ''; });
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
async function settle() { await vi.dynamicImportSettled(); await flushPromises(); }

async function render(path: string, transport: typeof fetch) {
  const services: ShellServices = { api: createAPI({ fetch: (url, options) => String(url).endsWith('/history') ? Promise.resolve(json([])) : transport(url, options), csrf: () => 'fixture-csrf' }),
    features, canApprove: true, reviewNotes: new Map(), leave: { hasChanges: () => false, confirmLeave: () => false } };
  const router = createAulaRouter(services.leave, createMemoryHistory());
  await router.push(path);
  const wrapper = mount(App, { attachTo: document.body, global: { plugins: [router], provide: { [shellKey as symbol]: services } } });
  wrappers.push(wrapper);
  await settle();
  return { wrapper, router, services };
}

describe('published specialist integration with fixture HTTP', () => {
  it.skipIf(!features.landing)('mounts the actual landing page with the shell entry and truthful export availability', async () => {
    const { wrapper } = await render('/', async () => json(interpretation()));
    expect(wrapper.findAll('h1')).toHaveLength(1);
    expect(wrapper.find('.landing-primary').attributes('href')).toBe('#/preparar');
    expect(wrapper.text()).toContain('aún no está habilitada');
    expect(wrapper.text()).toContain('debe aprobar y publicar');
    expect(wrapper.findAll('.landing a')).toHaveLength(1);
  });

  it.skipIf(!features.editor || !features.export)('keeps text typed during save and supplies that live draft to the real export component', async () => {
    let resolveSave!: (value: Response) => void;
    const transport = vi.fn<typeof fetch>().mockImplementation(async (_url, options) => options?.method === 'PATCH'
      ? new Promise<Response>(resolve => { resolveSave = resolve; }) : json(interpretation()));
    const { wrapper, router } = await render('/documentos/documento-ejemplo/actividad', transport);
    const title = wrapper.find('textarea');
    expect(title.exists()).toBe(true);
    await title.setValue('Texto enviado');
    await wrapper.find('form').trigger('submit');
    await settle();
    await title.setValue('Texto escrito después');
    resolveSave(json({ ...interpretation().draft, title: 'Texto enviado', revision: 2 }));
    await settle();
    expect((title.element as HTMLTextAreaElement).value).toBe('Texto escrito después');
    expect(wrapper.text()).toContain('Cambios sin guardar');
    expect(wrapper.findComponent({ name: 'ActivityExport' }).props('state').draft.title).toBe('Texto escrito después');
    expect(wrapper.findComponent({ name: 'ActivityExport' }).props('state').approved).toBeNull();
    await router.push('/');
    expect(router.currentRoute.value.name).toBe('editor');
    const options = transport.mock.calls.find(call => call[1]?.method === 'PATCH')![1];
    expect(JSON.parse(String(options?.body))).toEqual({ expected_revision: 1, changes: {
      title: 'Texto enviado', objective: 'Comparar figuras.', materials: ['Papel'], steps: ['Comparar.'], assessment: 'Explicar las diferencias.',
    } });
  });

  it.skipIf(!features.editor)('sends approval only after the actual editor confirmation and uses the returned revision', async () => {
    const transport = vi.fn<typeof fetch>().mockImplementation(async (_url, options) => json(options?.method === 'POST'
      ? { ...interpretation().draft, revision: 2, approval_status: 'approved' } : interpretation()));
    const { wrapper } = await render('/documentos/documento-ejemplo/actividad', transport);
    expect(transport.mock.calls).toHaveLength(1);
    const button = () => wrapper.findAll('button').find(button => button.text().includes('Aprobar'))!;
    expect(button().attributes('disabled')).toBeDefined();
    await wrapper.find('input[type=checkbox]').setValue(true);
    await button().trigger('click');
    await settle();
    const call = transport.mock.calls.find(call => call[1]?.method === 'POST')!;
    expect(call[0]).toBe('/api/v1/drafts/documento-ejemplo/approve');
    expect(JSON.parse(String(call[1]?.body))).toEqual({ expected_revision: 1, confirm: true });
    expect(wrapper.text()).toContain('Versión aprobada');
  });

  it.skipIf(!features.review || !features.editor)('hands off real review corrections without changing unknown source metadata', async () => {
    const { wrapper, router } = await render('/documentos/documento-ejemplo/revision', async () => json(interpretation()));
    expect(wrapper.text()).toContain('No se pudo determinar');
    const level = wrapper.findAll('.question').find(question => question.text().includes('nivel educativo'))!;
    await level.find('input').setValue('Secundaria');
    const sourceLink = wrapper.find('a[href^="#v-"]');
    if (sourceLink.exists()) await sourceLink.trigger('click');
    expect(router.currentRoute.value.name).toBe('review');
    await wrapper.findAll('button').find(button => button.text() === 'Continuar al borrador')!.trigger('click');
    await settle();
    expect(router.currentRoute.value.name).toBe('editor');
    expect(wrapper.text()).toContain('Secundaria');
    expect(wrapper.text()).toContain('No cambian los datos extraídos');
  });

  it.skipIf(!features.chat)('wires actual source lookup without sending an edit or approval', async () => {
    const transport = vi.fn<typeof fetch>().mockImplementation(async (_url, options) => json(options?.method === 'POST'
      ? { interpretation_id: 'documento-ejemplo', message: 'El documento menciona papel.', source_ids: ['p1'], proposals: [], mode: 'source_lookup', applies_changes: false }
      : interpretation()));
    const { wrapper } = await render('/documentos/documento-ejemplo/consulta', transport);
    await wrapper.find('textarea').setValue('¿Qué materiales hay?');
    await wrapper.find('form').trigger('submit');
    await settle();
    expect(wrapper.text()).toContain('El documento menciona papel.');
    expect(transport.mock.calls.map(call => call[0])).toEqual(['/api/v1/interpretations/documento-ejemplo', '/api/v1/chat']);
  });
});
