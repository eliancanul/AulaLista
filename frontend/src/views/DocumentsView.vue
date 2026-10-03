<script setup lang="ts">
import { inject, onMounted, ref } from 'vue';
import { shellKey } from '../shell';
const api = inject(shellKey)!.api;
const rows = ref<Awaited<ReturnType<typeof api.listInterpretations>>>([]);
const error = ref('');
onMounted(async () => { try { rows.value = await api.listInterpretations(); } catch (e) { error.value = e instanceof Error ? e.message : 'No se pudo cargar.'; } });
</script>
<template><section class="stack"><h1>Mis borradores guardados</h1>
<p v-if="error" role="alert">{{ error }}</p>
<p v-else-if="!rows.length">Todavía no hay borradores guardados.</p>
<article v-for="row in rows" :key="row.document_id"><h2><RouterLink :to="{ name: 'editor', params: { id: row.document_id } }">{{ row.draft.title || 'Actividad sin título' }}</RouterLink></h2>
<p>Versión {{ row.draft.revision }} · {{ row.draft.approval_status === 'approved' ? 'Aprobada por una persona' : 'Pendiente de revisión' }}</p></article>
<RouterLink to="/preparar">Preparar otra actividad</RouterLink></section></template>
