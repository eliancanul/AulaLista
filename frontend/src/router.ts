import { createRouter, createWebHashHistory, type RouterHistory } from 'vue-router';
import type { LeaveProtection } from './shell';
import DocumentsView from './views/DocumentsView.vue';
import HomeView from './views/HomeView.vue';
import UploadView from './views/UploadView.vue';
import WorkflowView from './views/WorkflowView.vue';
import NotFoundView from './views/NotFoundView.vue';

export function createAulaRouter(leave: LeaveProtection, history: RouterHistory = createWebHashHistory()) {
  const router = createRouter({
    history,
    routes: [
      { path: '/', name: 'home', component: HomeView, meta: { title: 'Inicio' } },
      { path: '/documentos', name: 'documents', component: DocumentsView, meta: { title: 'Mis borradores' } },
      { path: '/preparar', name: 'upload', component: UploadView, meta: { title: 'Preparar actividad' } },
      { path: '/documentos/:id/revision', name: 'review', component: WorkflowView, meta: { title: 'Revisar fuentes', feature: 'review' } },
      { path: '/documentos/:id/actividad', name: 'editor', component: WorkflowView, meta: { title: 'Editar actividad', feature: 'editor' } },
      { path: '/documentos/:id/descargas', name: 'export', component: WorkflowView, meta: { title: 'Descargar actividad', feature: 'export' } },
      { path: '/documentos/:id/consulta', name: 'chat', component: WorkflowView, meta: { title: 'Consultar fuentes', feature: 'chat' } },
      { path: '/:pathMatch(.*)*', component: NotFoundView, meta: { title: 'Página no encontrada' } },
    ],
  });
  router.beforeEach((to, from) => to.fullPath === from.fullPath || !leave.hasChanges() || leave.confirmLeave());
  return router;
}
