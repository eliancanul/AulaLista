import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory } from 'vue-router';
import { defineComponent } from 'vue';
import App from '../src/App.vue';
import { createAulaRouter } from '../src/router';
import { createAPI } from '../src/api/client';
import { shellKey, type ShellServices } from '../src/shell';
import { interpretation } from './s11-fixtures';

const wrappers: VueWrapper[] = [];
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); document.body.innerHTML = ''; });

async function shell(path = '/', overrides: Partial<ShellServices> = {}) {
  const services: ShellServices = {
    api: createAPI({ fetch: async url => new Response(JSON.stringify(String(url).endsWith('/history') ? [] : interpretation()), { headers: { 'Content-Type': 'application/json' } }) }),
    features: {}, canApprove: false, reviewNotes: new Map(),
    leave: { hasChanges: () => false, confirmLeave: vi.fn(() => false) }, ...overrides,
  };
  const router = createAulaRouter(services.leave, createMemoryHistory());
  await router.push(path);
  const wrapper = mount(App, { attachTo: document.body, global: { plugins: [router], provide: { [shellKey as symbol]: services } } });
  wrappers.push(wrapper);
  await flushPromises();
  return { wrapper, router, services };
}

describe('application shell', () => {
  it('renders Spanish navigation, human authority and an actionable empty state', async () => {
    const { wrapper } = await shell();
    expect(wrapper.find('nav[aria-label="Navegación principal"]').text()).toContain('Preparar actividad');
    expect(wrapper.find('h1').text()).toBe('Prepara una actividad con tus materiales');
    expect(wrapper.text()).toContain('Una persona revisora autorizada aprueba y publica');
    expect(wrapper.find('a[href="/tutor/"]').exists()).toBe(true);
    expect(wrapper.findAll('main')).toHaveLength(1);
  });

  it('focuses local anchors without replacing the application route hash', async () => {
    const { wrapper, router } = await shell('/preparar');
    await wrapper.find('.skip-link').trigger('click');
    expect(document.activeElement?.id).toBe('main-content');
    expect(router.currentRoute.value.fullPath).toBe('/preparar');
  });

  it('blocks route changes when the mounted editor reports changes and accepts explicit leave', async () => {
    const Editor = defineComponent({ setup(_, { expose }) { expose({ hasUnsavedChanges: () => true }); }, template: '<div>Texto por guardar</div>' });
    const { wrapper, router, services } = await shell('/documentos/documento-ejemplo/actividad', { features: { editor: Editor } });
    await router.push('/preparar');
    expect(router.currentRoute.value.name).toBe('editor');
    expect(wrapper.text()).toContain('Texto por guardar');
    expect(services.leave.confirmLeave).toHaveBeenCalledOnce();
    services.leave.confirmLeave = () => true;
    await router.push('/preparar');
    await flushPromises();
    expect(wrapper.find('h1').text()).toBe('Prepara tu actividad');
  });

  it('guards browser unload and navigation for typed chat text', async () => {
    const Chat = defineComponent({ template: '<textarea aria-label="Pregunta" />' });
    const { wrapper, services, router } = await shell('/documentos/documento-ejemplo/consulta', { features: { chat: Chat } });
    await wrapper.find('textarea').setValue('Pregunta pendiente');
    expect(services.leave.hasChanges()).toBe(true);
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    await router.push('/');
    expect(router.currentRoute.value.name).toBe('chat');
  });

  it('shows honest module availability and hides raw identifiers from shell text', async () => {
    const { wrapper } = await shell('/documentos/documento-ejemplo/actividad');
    expect(wrapper.text()).toContain('Esta vista todavía no está disponible');
    expect(wrapper.text()).not.toContain('documento-ejemplo');
  });

  it('retains review clarifications as separate notes without patching source or draft', async () => {
    const Review = defineComponent({ emits: ['continue'], setup(_, { emit }) {
      return { next: () => emit('continue', { interpretation: interpretation(), answers: { nivel_educativo: 'Secundaria' } }) };
    }, template: '<button @click="next">Continuar</button>' });
    const { wrapper, router, services } = await shell('/documentos/documento-ejemplo/revision', { features: { review: Review } });
    const save = vi.spyOn(services.api, 'patchDraft');
    await wrapper.find('main button').trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.name).toBe('editor');
    expect(wrapper.text()).toContain('Secundaria');
    expect(wrapper.text()).toContain('No cambian los datos extraídos');
    expect(save).not.toHaveBeenCalled();
  });

  it('makes errors recoverable and resolves unknown routes', async () => {
    const api = createAPI({ fetch: async () => new Response('', { status: 404 }) });
    const { wrapper } = await shell('/documentos/no-existe/revision', { api });
    expect(wrapper.find('[role=alert]').text()).toContain('No se pudo cargar');
    expect(wrapper.find('main button').text()).toBe('Volver a intentar');
    const missing = await shell('/ruta-inexistente');
    expect(missing.wrapper.find('h1').text()).toBe('No encontramos esta página');
  });
});
