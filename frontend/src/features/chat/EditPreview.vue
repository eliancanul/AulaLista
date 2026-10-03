<script setup lang="ts">
import { computed, ref } from 'vue';
import { createEditPreview } from './editPreview';
import type { DraftContext, EditProposal } from './editPreview';
import type { SourceSegment } from './chat';

const props = defineProps<{ proposal: EditProposal; current: DraftContext; sources: SourceSegment[] }>();
const emit = defineEmits<{
  accept: [value: NonNullable<ReturnType<ReturnType<typeof createEditPreview>['accept']>>];
  reject: [proposalId: string];
}>();
let preview: ReturnType<typeof createEditPreview> | null = null;
const error = ref('');
const decision = ref<'accepted' | 'rejected' | null>(null);
try { preview = createEditPreview(props.proposal, props.sources.map(source => source.id)); }
catch (cause) { error.value = (cause as Error).message; }
const rows = preview?.rows() ?? [];
const stale = computed(() => preview !== null && !preview.isCurrent(props.current));
const support = preview ? props.sources.filter(source => props.proposal.source_ids.includes(source.id)) : [];
const format = (value: string | string[]) => Array.isArray(value) ? value.join('\n') : value;
function accept() {
  const result = preview?.accept(props.current);
  if (!result) return;
  decision.value = 'accepted';
  emit('accept', result);
}
function reject() {
  if (decision.value) return;
  preview?.reject();
  decision.value = 'rejected';
  emit('reject', props.proposal.id);
}
</script>

<template>
  <section class="edit-preview" aria-label="Revisar cambios propuestos">
    <h2>Revisa los cambios propuestos</h2>
    <p>Tu actividad se conserva hasta que aceptes. Aceptar cambia el borrador; no lo guarda, aprueba ni publica.</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-for="row in rows" :key="row.key">
      <h3>{{ row.label }}</h3>
      <div class="comparison">
        <div><h4>Antes de la propuesta</h4><pre>{{ format(row.before) }}</pre></div>
        <div><h4>Propuesta</h4><pre>{{ format(row.after) }}</pre></div>
      </div>
    </div>
    <details v-if="support.length"><summary>Ver fuentes de la propuesta</summary>
      <blockquote v-for="source in support" :key="source.id">
        <p v-if="source.page != null">Página {{ source.page }}</p><pre>{{ source.text }}</pre>
      </blockquote>
    </details>
    <p v-if="stale && !decision" role="alert">Tu actividad cambió después de esta propuesta. Descártala y solicita otra para conservar tus cambios.</p>
    <p v-if="decision" role="status">{{ decision === 'accepted' ? 'Aceptaste la propuesta. Revisa el borrador antes de guardarlo.' : 'Descartaste la propuesta. Tu actividad se conserva.' }}</p>
    <template v-else>
      <button type="button" :disabled="!preview || stale" @click="accept">Aceptar cambios en el borrador</button>
      <button type="button" @click="reject">Rechazar propuesta</button>
    </template>
  </section>
</template>

<style scoped>
.edit-preview { padding: 1rem; border: 2px solid #146b65; color: #172c2b; background: #fff; }
.comparison { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(16rem, 100%), 1fr)); gap: 1rem; }
pre { font: inherit; white-space: pre-wrap; overflow-wrap: anywhere; }
button { min-height: 2.75rem; margin: .5rem .5rem .5rem 0; padding: .5rem; font: inherit; }
button:focus-visible, summary:focus-visible { outline: 3px solid #146b65; outline-offset: 3px; }
</style>
