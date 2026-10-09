<script setup lang="ts">
import { inject, onBeforeUnmount, ref } from 'vue';
import { useRouter } from 'vue-router';
import { shellKey } from '../shell';
import AppStatus from '../components/AppStatus.vue';
import PrimaryAction from '../components/PrimaryAction.vue';

const services = inject(shellKey)!;
const router = useRouter();
const file = ref<File | null>(null);
const busy = ref(false);
const error = ref('');
const controller = new AbortController();
const hasChanges = () => busy.value;
services.leave.hasChanges = hasChanges;
function selectFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null;
  error.value = '';
}
async function submit() {
  if (!file.value || busy.value) return;
  if (!file.value.name.toLowerCase().endsWith('.pdf')) { error.value = 'Selecciona un documento PDF.'; return; }
  busy.value = true;
  error.value = '';
  try {
    const result = await services.api.createInterpretation(file.value, controller.signal);
    if (controller.signal.aborted) return;
    busy.value = false;
    await router.push({ name: 'review', params: { id: result.document_id } });
  } catch (cause) {
    if (!controller.signal.aborted) error.value = cause instanceof Error ? cause.message : 'No se pudo preparar el documento.';
  } finally { busy.value = false; }
}
onBeforeUnmount(() => {
  controller.abort();
  if (services.leave.hasChanges === hasChanges) services.leave.hasChanges = () => false;
});
</script>

<template>
  <section class="stack">
    <h1>Prepara tu actividad</h1>
    <p>Elige el PDF curricular que quieres revisar. Evita documentos con nombres o datos personales del alumnado.</p>
    <form class="stack" @submit.prevent="submit">
      <label for="curriculum-file">Documento PDF</label>
      <input id="curriculum-file" type="file" accept=".pdf,application/pdf" :disabled="busy" @change="selectFile" />
      <div><PrimaryAction type="submit" :busy="busy" :disabled="!file">{{ busy ? 'Preparando borrador…' : 'Revisar documento' }}</PrimaryAction></div>
    </form>
    <AppStatus v-if="busy" kind="loading" title="Estamos leyendo el documento" detail="Salir de esta vista deja de esperar la respuesta, pero no garantiza cancelar el trabajo del servidor." />
    <AppStatus v-if="error" kind="error" title="No se pudo completar la carga" :detail="error">
      <a href="/cms/login/?next=/sprint/">Abrir sesión docente</a>
    </AppStatus>
    <p>El resultado será un borrador editable. Revisa sus fuentes antes de aprobarlo.</p>
  </section>
</template>
