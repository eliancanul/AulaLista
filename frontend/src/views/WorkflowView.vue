<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { shellKey, type FeatureName } from '../shell';
import { toSavedActivity, type ActivityContent, type Interpretation, type SavedActivity } from '../contracts/interpretation';
import AppStatus from '../components/AppStatus.vue';

const services = inject(shellKey)!;
const route = useRoute();
const router = useRouter();
const feature = route.meta.feature as FeatureName;
const documentId = String(route.params.id);
const documentData = shallowRef<Interpretation | null>(null);
const activity = shallowRef<SavedActivity | null>(null);
const loading = ref(true);
const error = ref('');
const history = ref<Awaited<ReturnType<typeof services.api.history>>>([]);
async function refreshHistory() {
  try { history.value = await services.api.history(documentId); }
  catch { error.value = 'El cambio fue confirmado, pero no se pudo actualizar el historial. Vuelve a cargarlo cuando haya conexión.'; }
}
const mountedFeature = ref<{ hasUnsavedChanges?: () => boolean } | null>(null);
const dirty = ref(false);
const notes = ref(services.reviewNotes.get(documentId) ?? {});
const exportState = shallowRef<{ saved: { revision: number }; draft: ActivityContent; approved: SavedActivity['approved'] } | null>(null);
const controller = new AbortController();
const hasChanges = () => dirty.value || !!mountedFeature.value?.hasUnsavedChanges?.();
services.leave.hasChanges = hasChanges;
let previousApproved: SavedActivity['approved'] = null;

function decode(value: unknown) {
  const saved = toSavedActivity(value, previousApproved);
  if (activity.value && saved.id !== activity.value.id) throw new Error('La respuesta no corresponde a esta actividad.');
  previousApproved = saved.approved;
  return saved;
}
const persistence = {
  async save(id: string, request: { expected_revision: number; content: ActivityContent }) {
    const { title, objective, materials, steps, assessment } = request.content;
    return decode(await services.api.patchDraft(id, {
      expected_revision: request.expected_revision, changes: { title, objective, materials, steps, assessment },
    }));
  },
  async approve(id: string, request: { expected_revision: number; reviewed: true }) {
    if (!services.canApprove || request.reviewed !== true) throw new Error('Se requiere permiso y confirmación de revisión.');
    return decode(await services.api.approveDraft(id, { expected_revision: request.expected_revision, confirm: true }));
  },
};
async function load() {
  if (!documentData.value) loading.value = true;
  error.value = '';
  try {
    const result = await services.api.getInterpretation(documentId, controller.signal);
    if (controller.signal.aborted) return;
    const revisions = await services.api.history(documentId);
    if (controller.signal.aborted) return;
    history.value = revisions;
    const approved = [...revisions].reverse().find(row => row.action === 'approved');
    previousApproved = approved ? toSavedActivity(approved.draft).approved : previousApproved;
    const saved = decode(result.draft);
    documentData.value = result;
    activity.value = saved;
    if (!exportState.value) exportState.value = { saved, draft: saved.content, approved: saved.approved };
  } catch (cause) {
    if (!controller.signal.aborted) error.value = cause instanceof Error ? cause.message : 'No se pudo cargar el documento.';
  } finally { loading.value = false; }
}
const featureProps = computed(() => {
  if (feature === 'editor') return { activity: activity.value, persistence, canApprove: services.canApprove };
  if (feature === 'review') return { initialInterpretation: documentData.value };
  if (feature === 'export') return { state: exportState.value, source: documentData.value };
  return { interpretationId: documentId, sources: documentData.value?.source_segments, transport: services.api.chat };
});
function changed(state: { needsLeaveWarning: boolean; saved: SavedActivity; draft: ActivityContent; approved: SavedActivity['approved'] }) {
  dirty.value = state.needsLeaveWarning;
  exportState.value = state;
}
function preserveInput() { if (feature === 'review' || feature === 'chat') dirty.value = true; }
async function continueReview(result: { interpretation: Interpretation; answers: Record<string, string> }) {
  if (result.interpretation.document_id !== documentId) return;
  notes.value = { ...result.answers };
  services.reviewNotes.set(documentId, notes.value);
  dirty.value = false;
  await router.push({ name: 'editor', params: { id: documentId } });
}
onMounted(load);
onBeforeUnmount(() => {
  controller.abort();
  if (services.leave.hasChanges === hasChanges) services.leave.hasChanges = () => false;
});
</script>

<template>
  <section class="stack">
    <h1 v-if="feature !== 'review' || !services.features.review">{{ route.meta.title }}</h1>
    <nav class="workflow-nav" aria-label="Pasos de preparación">
      <RouterLink v-for="item in [{ name: 'review', label: '1. Fuentes' }, { name: 'editor', label: '2. Actividad' }, { name: 'export', label: '3. Descargas' }, { name: 'chat', label: 'Consultar fuentes' }]" :key="item.name" :to="{ name: item.name, params: { id: documentId } }">{{ item.label }}</RouterLink>
    </nav>
    <AppStatus v-if="loading" kind="loading" title="Cargando el documento guardado" />
    <AppStatus v-if="error" kind="error" title="No se pudo cargar la versión guardada" :detail="error">
      <div class="actions"><button type="button" @click="load">Volver a intentar</button><a href="/cms/login/?next=/sprint/">Abrir sesión docente</a></div>
    </AppStatus>
    <template v-if="documentData && activity">
      <aside v-if="Object.keys(notes).length" class="app-status">
        <h2>Tus aclaraciones de revisión</h2>
        <p>Se conservan sólo mientras esta aplicación siga abierta. Incorpora las que necesites al borrador y guárdalo. No cambian los datos extraídos.</p>
        <ul><li v-for="(note, key) in notes" :key="key">{{ note }}</li></ul>
      </aside>
      <div v-if="services.features[feature]" @input="preserveInput">
        <component :is="services.features[feature]" ref="mountedFeature" v-bind="featureProps" @change="feature === 'editor' && changed($event)" @request-refresh="load" @saved="refreshHistory" @approved="refreshHistory" @continue="continueReview" />
        <component v-if="feature === 'editor' && services.features.export && exportState" :is="services.features.export" :state="exportState" :source="documentData" />
      </div>
      <AppStatus v-else kind="empty" title="Esta vista todavía no está disponible" detail="El documento guardado se conserva. Puedes volver al espacio docente para continuar con las herramientas disponibles.">
        <a href="/tutor/">Abrir espacio docente</a>
      </AppStatus>
      <details>
        <summary>Historial de revisiones ({{ history.length }})</summary>
        <p>Cada guardado conserva la revisión anterior. Aprobar no publica contenido para estudiantes.</p>
        <article v-for="row in history" :key="row.draft.revision">
          <h3>Versión {{ row.draft.revision }} · {{ {created: 'Borrador inicial', edited: 'Edición guardada', approved: 'Aprobación humana'}[row.action] || row.action }}</h3>
          <p>{{ row.created_at }}</p>
          <pre>{{ row.draft.title }}
{{ row.draft.objective }}
{{ row.draft.steps.join('\n') }}</pre>
          <p>Fuentes: {{ row.draft.source_ids.join(', ') }}</p>
        </article>
      </details>
      <a :href="`/api/v1/interpretations/${encodeURIComponent(documentId)}/source`">Descargar PDF fuente conservado</a>
    </template>
  </section>
</template>

<style scoped>
.workflow-nav { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.workflow-nav a { display: inline-flex; align-items: center; min-height: 44px; padding: var(--space-1); }
.workflow-nav a[aria-current=page] { font-weight: 750; text-decoration-thickness: 3px; }
</style>
