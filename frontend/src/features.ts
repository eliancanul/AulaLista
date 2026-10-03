import { defineAsyncComponent, defineComponent, h, type Component } from 'vue';
import type { FeatureModules } from './shell';
import AppStatus from './components/AppStatus.vue';

const modules: Partial<Record<string, () => Promise<{ default: Component }>>> = import.meta.glob<{ default: Component }>([
  './features/landing/LandingPage.vue', './features/review/UploadReview.vue',
  './features/editor/ActivityEditor.vue', './features/export/ActivityExport.vue', './features/chat/TeacherChat.vue',
]);
const entries = {
  landing: './features/landing/LandingPage.vue',
  review: './features/review/UploadReview.vue',
  editor: './features/editor/ActivityEditor.vue',
  export: './features/export/ActivityExport.vue',
  chat: './features/chat/TeacherChat.vue',
} as const;

export const features: FeatureModules = {};
for (const [name, path] of Object.entries(entries)) {
  const loader = modules[path];
  if (loader) features[name as keyof FeatureModules] = defineAsyncComponent({
    loader,
    delay: 0,
    loadingComponent: defineComponent(() => () => h(AppStatus, { title: 'Abriendo la vista', kind: 'loading' })),
    errorComponent: defineComponent(() => () => h(AppStatus, { title: 'No se pudo abrir la vista', detail: 'Vuelve al inicio e inténtalo de nuevo cuando puedas acceder al nodo local.', kind: 'error' })),
  });
}
