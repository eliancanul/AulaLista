<script setup lang="ts">
withDefaults(defineProps<{
  entryHref?: string
  exportsAvailable?: boolean
}>(), {
  entryHref: '/tutor/imports/new/',
  exportsAvailable: false,
})
</script>

<template>
  <section class="landing" aria-labelledby="landing-title" lang="es-MX">
    <div class="landing-hero">
      <p class="landing-eyebrow">AulaLista · Preparación docente</p>
      <h1 id="landing-title">De tu material curricular a una actividad que puedes editar.</h1>
      <p class="landing-intro">
        Parte de tu documento, revisa lo que dice y adapta el borrador a tu grupo.
        Tú decides qué conservar y qué corregir.
      </p>
      <a class="landing-primary" :href="entryHref" aria-describedby="landing-access">
        Preparar una actividad
      </a>
      <p id="landing-access" class="landing-note">
        Necesitas tu cuenta docente. Si aún no has entrado, primero iniciarás sesión.
      </p>
    </div>

    <section class="landing-process" aria-labelledby="landing-process-title">
      <h2 id="landing-process-title">Empieza con lo que ya tienes</h2>
      <ol class="landing-steps">
        <li>
          <h3>Comparte tu material</h3>
          <p>Selecciona el PDF curricular con el que quieres trabajar.</p>
        </li>
        <li>
          <h3>Revisa la interpretación</h3>
          <p>Contrasta la información con la fuente y aclara lo que falte o no corresponda.</p>
        </li>
        <li>
          <h3>Haz tuyo el borrador</h3>
          <p>Ajusta la actividad antes de aprobarla. Una propuesta automática puede equivocarse.</p>
        </li>
      </ol>
    </section>

    <div class="landing-boundaries">
      <section aria-labelledby="landing-review-title">
        <h2 id="landing-review-title">La revisión sigue en tus manos</h2>
        <p>
          La asistencia propone borradores. Una persona con permiso de revisión editorial
          debe aprobar y publicar el material; la maestra o el maestro decide cuándo activar la sesión.
        </p>
      </section>
      <section aria-labelledby="landing-offline-title">
        <h2 id="landing-offline-title">Prepara también tu clase sin conexión</h2>
        <p v-if="exportsAvailable">
          Descarga o imprime la actividad revisada antes de desconectarte.
          Esa copia se puede consultar sin Internet.
        </p>
        <p v-else>
          Antes de ir al aula, prepara una copia del material que puedas consultar sin Internet.
          La descarga de actividades desde esta pantalla aún no está habilitada.
        </p>
        <p class="landing-note">
          La interpretación asistida puede necesitar conexión. Una copia descargada no incluye esa asistencia.
        </p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.landing {
  box-sizing: border-box;
  width: 100%;
  max-width: 72rem;
  margin-inline: auto;
  padding: clamp(1rem, 4vw, 3rem);
  color: var(--color-ink, #161a1d);
  background: var(--color-paper, #f7f5f0);
  font-family: system-ui, sans-serif;
  font-size: 1rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.landing h1, .landing h2, .landing h3, .landing p { margin: 0; }
.landing h1 { max-width: 23ch; font-size: clamp(2rem, 5vw, 3.5rem); line-height: 1.15; }
.landing h2 { font-size: 1.375rem; line-height: 1.3; }
.landing h3 { font-size: 1.125rem; }
.landing p { max-width: 65ch; }
.landing-hero, .landing-process, .landing-boundaries section { display: grid; gap: var(--space-3, 1rem); }
.landing-eyebrow { font-weight: 650; }
.landing-intro { font-size: 1.125rem; }
.landing-note { font-size: 1rem; }

.landing-primary {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  width: fit-content;
  max-width: 100%;
  padding: var(--space-2, .75rem) var(--space-4, 1.5rem);
  border-radius: var(--radius, .5rem);
  background: var(--color-action, #611232);
  color: var(--color-surface, #ffffff);
  font-weight: 700;
  text-align: center;
  text-decoration: underline;
  text-underline-offset: .2em;
}
.landing-primary:focus-visible { outline: 4px solid var(--color-focus, #795b1e); outline-offset: 4px; }
.landing-process { margin-top: 2.5rem; }
.landing-steps { display: grid; gap: var(--space-4, 1.5rem); margin: 0; padding-left: 1.5rem; }
.landing-steps li { padding-left: .25rem; }
.landing-steps li::marker { font-weight: 700; }
.landing-steps p { margin-top: var(--space-1, .5rem); }
.landing-boundaries { display: grid; gap: var(--space-4, 1.5rem); margin-top: 2.5rem; }
.landing-boundaries section {
  align-content: start;
  padding: var(--space-4, 1.5rem);
  border: 1px solid var(--color-review, #795b1e);
  border-radius: var(--radius, .5rem);
  background: var(--color-surface, #ffffff);
}
@media (max-width: 420px) { .landing-primary { width: 100%; } }
@media (min-width: 760px) {
  .landing-steps { grid-template-columns: repeat(3, minmax(0, 1fr)); column-gap: 2.5rem; }
  .landing-boundaries { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
