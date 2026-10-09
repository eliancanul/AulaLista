<script setup lang="ts">
import { inject } from 'vue';
import { shellKey } from '../shell';
const services = inject(shellKey)!;
</script>

<template>
  <component v-if="services.features.landing" :is="services.features.landing" entry-href="#/preparar" :exports-available="false" />
  <section v-else class="stack">
    <h1>Prepara una actividad con tus materiales</h1>
    <p>Carga un PDF, revisa sus fuentes y edita el borrador antes de aprobarlo.</p>
    <p>Si falta información, te lo mostraremos para que tú decidas cómo continuar.</p>
    <div><RouterLink class="button-link" to="/preparar">Preparar actividad</RouterLink></div>
    <p>Para guardar necesitas conexión con el nodo local de tu escuela. Las copias descargadas pueden consultarse sin conexión.</p>
  </section>
</template>
