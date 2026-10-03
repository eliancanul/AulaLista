<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue';
import { createActivityEditor, type ActivityContent, type EditorPersistence, type SavedActivity } from './activityEditor';

const props = withDefaults(defineProps<{
  activity: SavedActivity;
  persistence: EditorPersistence;
  canApprove?: boolean;
}>(), { canApprove: false });
const emit = defineEmits(['change', 'saved', 'approved', 'request-refresh']);
const editor = createActivityEditor(props.activity, props.persistence);
const state = shallowRef(editor.snapshot());
const reviewed = ref(false);
const unsubscribe = editor.subscribe(next => {
  if (JSON.stringify(next.draft) !== JSON.stringify(state.value.draft) || next.saved.revision !== state.value.saved.revision || next.conflict) reviewed.value = false;
  state.value = next;
  emit('change', next);
});
watch(() => props.activity, value => editor.receive(value), { deep: true });
const approvalEnabled = computed(() => props.canApprove && reviewed.value && !state.value.dirty && !state.value.pending && !state.value.conflict && !state.value.isApproved && state.value.draft.source_ids.length > 0);
const statusText = computed(() => state.value.pending === 'save' ? 'Guardando…'
  : state.value.pending === 'approve' ? 'Confirmando aprobación…'
  : state.value.conflict ? 'Hay versiones por comparar'
  : state.value.dirty ? 'Cambios sin guardar'
  : state.value.isApproved ? 'Versión aprobada' : 'Borrador guardado, pendiente de aprobación');
const textFields = [
  { key: 'title', label: 'Título' },
  { key: 'objective', label: 'Objetivo' },
  { key: 'materials', label: 'Materiales (uno por línea)' },
  { key: 'steps', label: 'Pasos (uno por línea)' },
  { key: 'assessment', label: 'Evaluación' },
] as const;
function fieldText(content: ActivityContent, key: keyof ActivityContent) {
  const value = content[key];
  return Array.isArray(value) ? value.join('\n') : value;
}
function edit(key: typeof textFields[number]['key'], event: Event) {
  const value = (event.target as HTMLTextAreaElement).value;
  if (key === 'materials' || key === 'steps') editor.edit(key, value.split('\n'));
  else editor.edit(key, value);
}
async function save() { if (await editor.save()) emit('saved', editor.snapshot().saved); }
async function approve() {
  if (approvalEnabled.value && await editor.approve(reviewed.value)) emit('approved', editor.snapshot().approved);
}
function download() {
  const url = URL.createObjectURL(new Blob([editor.recoveryJSON()], { type: 'application/json;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'actividad-borrador.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function warnBeforeLeave(event: BeforeUnloadEvent) {
  if (editor.snapshot().needsLeaveWarning) { event.preventDefault(); event.returnValue = ''; }
}
onMounted(() => window.addEventListener('beforeunload', warnBeforeLeave));
onBeforeUnmount(() => { unsubscribe(); window.removeEventListener('beforeunload', warnBeforeLeave); });
defineExpose({ hasUnsavedChanges: () => editor.snapshot().needsLeaveWarning, receive: editor.receive });
</script>

<template>
  <section class="activity-editor" aria-label="Editor de actividad">
    <header>
      <h2>Prepara tu actividad</h2>
      <p role="status" aria-live="polite">{{ statusText }}</p>
      <p>Revisa el contenido y sus fuentes. Guardar un borrador no lo aprueba ni lo publica.</p>
    </header>
    <p v-if="state.error" role="alert">{{ state.error }}</p>
    <form @submit.prevent="save">
      <label v-for="field in textFields" :key="field.key" class="editor-field">
        <span>{{ field.label }}</span>
        <textarea :value="fieldText(state.draft, field.key)" :rows="field.key === 'title' ? 2 : 4" @input="edit(field.key, $event)" />
      </label>
      <p v-if="!state.draft.source_ids.length" role="status">No hay suficiente fuente local</p>
      <details v-else>
        <summary>Referencias de las fuentes</summary>
        <ul><li v-for="source in state.draft.source_ids" :key="source">{{ source }}</li></ul>
      </details>
      <div class="editor-actions">
        <button type="submit" :disabled="!state.dirty || !!state.pending || state.conflict">Guardar borrador</button>
        <button type="button" @click="download">Descargar copia del borrador</button>
      </div>
      <p>La copia conserva el texto actual, incluidos los cambios sin guardar. No es una actividad aprobada.</p>
    </form>
    <section v-if="state.conflict" aria-label="Comparar versiones">
      <h3>Tu texto se conserva</h3>
      <button v-if="!state.remote" type="button" :disabled="!!state.pending" @click="emit('request-refresh', state.saved.id)">Cargar versión guardada</button>
      <template v-else>
        <p>Compara la versión guardada con tu edición antes de continuar.</p>
        <div v-for="field in textFields" :key="field.key" class="version-comparison">
          <h4>{{ field.label }}</h4>
          <div><strong>Tu edición</strong><pre>{{ fieldText(state.draft, field.key) }}</pre></div>
          <div><strong>Versión guardada</strong><pre>{{ fieldText(state.remote.content, field.key) }}</pre></div>
        </div>
        <p>Fuentes de tu edición: {{ state.draft.source_ids.join(', ') || 'Sin fuentes' }}</p>
        <p>Fuentes guardadas: {{ state.remote.content.source_ids.join(', ') || 'Sin fuentes' }}</p>
        <div class="editor-actions">
          <button type="button" :disabled="!!state.pending" @click="editor.resolveRemote('keep-local')">Conservar mi texto para volver a guardarlo</button>
          <button type="button" :disabled="!!state.pending" @click="editor.resolveRemote('use-remote')">Reemplazar mi texto por la versión guardada</button>
        </div>
      </template>
    </section>
    <section aria-label="Revisión y aprobación">
      <h3>Aprobación humana</h3>
      <label><input v-model="reviewed" type="checkbox" :disabled="!canApprove || state.dirty || !!state.pending || state.conflict"> Revisé la actividad y sus fuentes.</label>
      <button type="button" :disabled="!approvalEnabled" @click="approve">Aprobar esta versión</button>
      <p v-if="!canApprove">Se requiere una persona autorizada para aprobar.</p>
      <p v-if="state.dirty">Guarda tus cambios antes de aprobar esta versión.</p>
      <details v-if="state.approved">
        <summary>Consultar la última versión aprobada</summary>
        <div v-for="field in textFields" :key="field.key"><strong>{{ field.label }}</strong><pre>{{ fieldText(state.approved.content, field.key) }}</pre></div>
        <p>Los cambios del borrador no modifican esta versión.</p>
      </details>
    </section>
  </section>
</template>

<style scoped>
.activity-editor { max-width: 58rem; margin-inline: auto; padding: 1rem; }
.editor-field { display: grid; gap: .4rem; margin-block: 1rem; }
textarea { box-sizing: border-box; width: 100%; padding: .65rem; font: inherit; resize: vertical; }
.editor-actions { display: flex; flex-wrap: wrap; gap: .75rem; margin-block: 1rem; }
button { padding: .7rem 1rem; min-height: 44px; font: inherit; cursor: pointer; }
button:disabled { cursor: default; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
section + section { margin-top: 1.5rem; border-top: 1px solid #999; padding-top: 1rem; }
.version-comparison { border-bottom: 1px solid #bbb; }
[role="alert"] { padding: 1rem; border: 2px solid #9b2323; }
:focus-visible { outline: 3px solid #155bb5; outline-offset: 3px; }
</style>
