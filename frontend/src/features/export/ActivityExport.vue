<script setup lang="ts">
import { ref } from 'vue';
import { createActivityFile, downloadActivityFile } from './activityExport';
import type { ExportMode, ExportSource, ExportState } from './activityExport';

const props = defineProps<{ state: ExportState; source: ExportSource; demo?: boolean }>();
const emit = defineEmits<{ 'download-requested': [mode: ExportMode] }>();
const message = ref('');

function download(mode: ExportMode) {
  try {
    const result = downloadActivityFile(createActivityFile(props.state, props.source, mode, props.demo));
    message.value = result.message;
    if (result.ok) emit('download-requested', mode);
  } catch (cause) {
    message.value = cause instanceof Error ? cause.message : 'No se pudo preparar la copia. Tu actividad sigue en el editor.';
  }
}
</script>

<template>
  <section class="activity-export" aria-label="Descargar actividad">
    <h2>Lleva tu actividad al aula</h2>
    <p>Descarga un archivo HTML con el texto y las fuentes incluidas. Puedes abrirlo sin conexión e imprimirlo desde el navegador.</p>
    <p>El borrador incluye tus cambios actuales, aunque no estén guardados. Necesita revisión humana antes de usarlo con el grupo.</p>
    <div class="export-actions">
      <button type="button" @click="download('draft')">Descargar borrador para revisar</button>
      <button type="button" :disabled="!state.approved" @click="download('approved')">
        {{ state.approved ? `Descargar versión aprobada ${state.approved.revision}` : 'Sin versión aprobada para descargar' }}
      </button>
    </div>
    <p v-if="state.approved">La copia aprobada conserva esa revisión. Puede ser distinta del texto que estás editando.</p>
    <p>Los videos, imágenes, anexos y el PDF original no se incluyen. Prepara esos recursos antes de desconectarte. Descargar no guarda ni aprueba la actividad.</p>
    <p role="status" aria-live="polite">{{ message }}</p>
  </section>
</template>

<style scoped>
.activity-export { padding: 1.25rem; border: 1px solid #687583; border-radius: .5rem; }
.export-actions { display: flex; gap: .75rem; flex-wrap: wrap; }
button { padding: .75rem 1rem; font: inherit; cursor: pointer; }
button:disabled { cursor: not-allowed; }
button:focus-visible { outline: 3px solid #154d77; outline-offset: 3px; }
</style>
