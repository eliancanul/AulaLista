<script setup lang="ts">
import { onBeforeUnmount, shallowRef } from 'vue';
import { createTeacherChat } from './chat';
import type { ChatTransport, SourceSegment } from './chat';

const props = defineProps<{ interpretationId: string; sources: SourceSegment[]; transport: ChatTransport }>();
const chat = createTeacherChat(props.interpretationId, props.sources, request => props.transport(request));
const state = shallowRef(chat.snapshot());
const unsubscribe = chat.subscribe(value => { state.value = value; });
onBeforeUnmount(() => { unsubscribe(); chat.dispose(); });
const inputId = `chat-question-${props.interpretationId}`;
</script>

<template>
  <section class="teacher-chat" aria-label="Consulta tus fuentes">
    <h2>Consulta tus fuentes</h2>
    <p>Busca fragmentos de tu material. Las respuestas no cambian ni aprueban tu actividad.</p>
    <p v-if="!state.turns.length">Pregunta por los materiales, el objetivo o las indicaciones de tu documento.</p>
    <ol aria-label="Preguntas y respuestas">
      <li v-for="(turn, index) in state.turns" :key="index">
        <h3>Tu pregunta</h3>
        <p class="text">{{ turn.question }}</p>
        <h3>Consulta del material</h3>
        <p class="text">{{ turn.answer }}</p>
        <details v-if="turn.sources.length">
          <summary>Ver fuentes de esta respuesta</summary>
          <blockquote v-for="source in turn.sources" :key="source.id">
            <p v-if="source.page != null">Página {{ source.page }}</p>
            <p class="text">{{ source.text }}</p>
          </blockquote>
        </details>
        <p v-else>No hay suficiente fuente local para respaldar esta respuesta.</p>
      </li>
    </ol>
    <p role="status" aria-live="polite">{{ state.status === 'loading' ? 'Consultando tus fuentes…' : state.turns.length ? 'Respuesta disponible para revisar.' : '' }}</p>
    <div v-if="state.error" role="alert">
      <p>{{ state.error }}</p>
      <button v-if="state.retryable" type="button" @click="chat.retry()">Reintentar la consulta anterior</button>
    </div>
    <form :aria-busy="state.status === 'loading'" @submit.prevent="chat.send()">
      <label :for="inputId">Escribe tu pregunta</label>
      <textarea :id="inputId" :value="state.input" maxlength="4000" rows="4"
        @input="chat.setInput(($event.target as HTMLTextAreaElement).value)" />
      <button type="submit" :disabled="state.status === 'loading' || !state.input.trim() || state.input.length > 4000">Consultar</button>
    </form>
  </section>
</template>

<style scoped>
.teacher-chat { max-width: 52rem; padding: 1rem; color: #172c2b; background: #fff; }
ol { padding-left: 1.4rem; }
li { margin-block: 1.5rem; }
.text { white-space: pre-wrap; overflow-wrap: anywhere; }
textarea { display: block; width: 100%; box-sizing: border-box; font: inherit; margin-block: .5rem; }
button { min-height: 2.75rem; padding: .5rem 1rem; font: inherit; cursor: pointer; }
button:disabled { cursor: default; }
button:focus-visible, textarea:focus-visible, summary:focus-visible { outline: 3px solid #146b65; outline-offset: 3px; }
</style>
