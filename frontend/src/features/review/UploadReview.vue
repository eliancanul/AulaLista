<script setup>
import { computed, onBeforeUnmount, shallowRef, useId } from 'vue'
import { createReviewSession, displayValue, FIELD_LABELS, MAX_PDF_BYTES, questionsFor, STATUS_LABELS } from './review-model.mjs'

const props = defineProps({
  upload: Function,
  initialInterpretation: { type: Object, default: null },
  fixture: { type: Boolean, default: false },
  maxBytes: { type: Number, default: MAX_PDF_BYTES },
})
const emit = defineEmits(['continue', 'sign-in'])
const prefix = useId()
const state = shallowRef()
const session = createReviewSession({ upload: props.upload, initialInterpretation: props.initialInterpretation, maxBytes: props.maxBytes, onChange: next => { state.value = next } })
state.value = session.state
const questions = computed(() => state.value.interpretation ? questionsFor(state.value.interpretation) : [])
const sourceIndex = computed(() => new Map((state.value.interpretation?.source_segments ?? []).map((segment, index) => [segment.id, index])))
const sourceAnchor = id => `${prefix}-source-${sourceIndex.value.get(id)}`
const isBusy = computed(() => state.value.phase === 'submitting')
function chooseFile(event) {
  const file = event.target.files?.[0]
  if (file) session.selectFile(file)
  event.target.value = ''
}
function continueReview() {
  const result = session.handoff()
  if (result) emit('continue', result)
}
onBeforeUnmount(() => session.dispose())
</script>

<template>
  <section class="upload-review" :aria-labelledby="`${prefix}-heading`" :aria-busy="isBusy">
    <h1 :id="`${prefix}-heading`">Revisa tu material</h1>
    <p v-if="fixture" class="notice" role="note">Demostración con datos de ejemplo. No es una interpretación de tu archivo ni un resultado de un modelo.</p>
    <p>Verifica lo que encontramos antes de preparar la actividad. Tú decides qué corregir.</p>
    <template v-if="!state.interpretation">
      <label :for="`${prefix}-file`">Selecciona tu material en PDF</label>
      <input :id="`${prefix}-file`" type="file" accept=".pdf,application/pdf" :disabled="isBusy" :aria-describedby="`${prefix}-limit`" @change="chooseFile">
      <p :id="`${prefix}-limit`">Un PDF de hasta {{ Math.floor(maxBytes / 1024 / 1024) }} MB. No incluyas datos del alumnado.</p>
      <p v-if="state.file">Archivo seleccionado: {{ state.file.name }}</p>
      <div v-if="state.error" role="alert" class="notice">
        <p>{{ state.error.message }}</p>
        <button v-if="state.error.action === 'sign-in'" type="button" @click="emit('sign-in')">Revisar acceso</button>
      </div>
      <p v-if="isBusy" role="status">Enviando y leyendo tu documento. Esto puede tardar.</p>
      <p v-if="state.phase === 'stopped'" role="status">Dejaste de esperar. Esto no confirma que se haya cancelado el trabajo en el servidor. Reintentar puede crear otra copia.</p>
      <button v-if="isBusy" type="button" @click="session.stopWaiting()">Dejar de esperar</button>
      <button v-else type="button" :disabled="!state.file || (state.phase === 'error' && !state.error.retryable)" @click="session.submit()">
        {{ state.phase === 'error' || state.phase === 'stopped' ? 'Volver a intentar' : 'Leer documento' }}
      </button>
    </template>
    <template v-else>
      <p class="notice">Esta revisión no aprueba ni publica la actividad.</p>
      <p v-if="state.interpretation.draft.status === 'No hay suficiente fuente local'" role="alert">No hay suficiente fuente local. Completa y verifica el borrador antes de solicitar su aprobación.</p>
      <ul v-if="state.interpretation.diagnostics.source_warnings.length" aria-label="Partes del documento que requieren atención">
        <li v-for="(warning, index) in state.interpretation.diagnostics.source_warnings" :key="index">Página {{ warning.page }}: {{ warning.message }}</li>
      </ul>
      <h2>Información encontrada</h2>
      <ul class="fields">
        <li v-for="(field, index) in state.interpretation.fields" :key="field.key" class="field">
          <h3>{{ FIELD_LABELS[field.key] }}</h3>
          <p class="status">{{ STATUS_LABELS[field.status] }}</p>
          <p>{{ displayValue(field.value) }}</p>
          <p v-if="field.reason">{{ field.reason }}</p>
          <ul v-if="field.evidence_ids.length" aria-label="Fuentes de este dato">
            <li v-for="id in field.evidence_ids" :key="id"><a :href="`#${sourceAnchor(id)}`">Ver fragmento de la página {{ state.interpretation.source_segments[sourceIndex.get(id)].page }}</a></li>
          </ul>
          <details>
            <summary>Añadir mi corrección</summary>
            <label :for="`${prefix}-correction-${index}`">Tu corrección de {{ FIELD_LABELS[field.key].toLowerCase() }}</label>
            <textarea :id="`${prefix}-correction-${index}`" :value="state.answers[field.key] ?? ''" @input="session.answer(field.key, $event.target.value)" />
          </details>
        </li>
      </ul>
      <h2 v-if="questions.length">Aclaraciones para preparar la actividad</h2>
      <p v-if="questions.length">Responde lo que sepas. Puedes continuar con datos pendientes; no se completarán por ti.</p>
      <div v-for="(question, index) in questions" :key="question.key" class="question">
        <label :for="`${prefix}-answer-${index}`">{{ question.text }}</label>
        <input :id="`${prefix}-answer-${index}`" type="text" :value="state.answers[question.key] ?? ''" @input="session.answer(question.key, $event.target.value)">
      </div>
      <h2>Fragmentos de tu documento</h2>
      <p v-if="!state.interpretation.source_segments.length">No se encontraron fragmentos legibles.</p>
      <article v-for="segment in state.interpretation.source_segments" :id="sourceAnchor(segment.id)" :key="segment.id" tabindex="-1" class="source">
        <h3>Página {{ segment.page }}</h3>
        <blockquote>{{ segment.text }}</blockquote>
      </article>
      <p>Tus aclaraciones se conservan en esta pantalla. Continuar las entrega al editor; todavía no se han guardado.</p>
      <button type="button" @click="continueReview">Continuar al borrador</button>
    </template>
  </section>
</template>

<style scoped>
.upload-review { max-width: 58rem; margin: 0 auto; padding: 1.5rem; color: #17352b; background: #fff; line-height: 1.6; }
.fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr)); gap: 1rem; padding: 0; list-style: none; }
.field, .source, .notice { padding: 1rem; border: 1px solid #697a71; border-radius: .5rem; }
h3 { margin: 0; }
.status { font-weight: 700; }
label { display: block; font-weight: 600; }
input, textarea { max-width: 100%; box-sizing: border-box; font: inherit; padding: .5rem; }
textarea, input[type='text'] { width: 100%; }
.question, .source { margin-block: 1rem; }
blockquote { white-space: pre-wrap; overflow-wrap: anywhere; margin-inline: 0; }
button { padding: .7rem 1rem; font: inherit; cursor: pointer; }
a { color: #174c91; }
:focus-visible, .source:target { outline: 3px solid #8c3c08; outline-offset: 3px; }
button:disabled { cursor: not-allowed; }
</style>
