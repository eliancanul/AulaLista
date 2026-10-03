import { createApp, nextTick } from 'vue';
import App from './App.vue';
import { createAPI } from './api/client';
import { features } from './features';
import { createAulaRouter } from './router';
import { shellKey, type ShellServices } from './shell';
import './styles/tokens.css';
import './styles/base.css';

const services: ShellServices = {
  api: createAPI(),
  features,
  reviewNotes: new Map(),
  canApprove: document.querySelector<HTMLMetaElement>('meta[name=aulalista-can-approve]')?.content === 'true',
  leave: {
    hasChanges: () => false,
    confirmLeave: () => window.confirm('Hay cambios sin guardar o una solicitud pendiente. ¿Quieres salir de esta vista?'),
  },
};
const router = createAulaRouter(services.leave);
router.afterEach(async (to, from, failure) => {
  if (failure) return;
  document.title = `${String(to.meta.title)} · AulaLista`;
  await nextTick();
  if (from.matched.length) document.querySelector<HTMLElement>('#main-content')?.focus();
});

createApp(App).provide(shellKey, services).use(router).mount('#app');
