<script setup lang="ts">
import { inject, onBeforeUnmount, onMounted, ref } from 'vue';
import { RouterLink, RouterView } from 'vue-router';
import EditorialBoundary from './components/EditorialBoundary.vue';
import { readCSRF } from './api/client';
import { shellKey } from './shell';

const services = inject(shellKey)!;
const offline = ref(false);
function signOut() {
  if (services.leave.hasChanges() && !services.leave.confirmLeave()) return;
  const form = document.createElement('form');
  form.method = 'POST'; form.action = '/tutor/logout/';
  const token = document.createElement('input');
  token.type = 'hidden'; token.name = 'csrfmiddlewaretoken'; token.value = readCSRF() ?? '';
  form.append(token); document.body.append(form); form.submit();
}
const updateConnection = () => { offline.value = !navigator.onLine; };
function warnBeforeLeave(event: BeforeUnloadEvent) {
  if (services.leave.hasChanges()) { event.preventDefault(); event.returnValue = ''; }
}
function followFragment(event: MouseEvent) {
  const anchor = (event.target as Element)?.closest('a');
  const href = anchor?.getAttribute('href');
  if (!href?.startsWith('#') || href.startsWith('#/')) return;
  const target = document.getElementById(href.slice(1));
  if (!target) return;
  event.preventDefault();
  target.scrollIntoView?.();
  target.focus();
}
onMounted(() => {
  updateConnection();
  window.addEventListener('online', updateConnection);
  window.addEventListener('offline', updateConnection);
  window.addEventListener('beforeunload', warnBeforeLeave);
});
onBeforeUnmount(() => {
  window.removeEventListener('online', updateConnection);
  window.removeEventListener('offline', updateConnection);
  window.removeEventListener('beforeunload', warnBeforeLeave);
});
</script>

<template>
  <div @click="followFragment">
  <a class="skip-link" href="#main-content">Saltar al contenido</a>
  <header class="app-header">
    <RouterLink class="brand" to="/">AulaLista</RouterLink>
    <nav aria-label="Navegación principal">
      <RouterLink to="/">Inicio</RouterLink>
      <RouterLink to="/documentos">Mis borradores</RouterLink>
      <RouterLink to="/preparar">Preparar actividad</RouterLink>
      <a href="/tutor/">Espacio docente</a>
      <button type="button" @click="signOut">Cerrar sesión</button>
    </nav>
  </header>
  <div class="app-body">
    <p v-if="offline" class="connection-status" role="status">
      El navegador indica que no hay conexión. Las copias descargadas siguen disponibles.
      Guardar cambios requiere acceso al nodo local.
    </p>
    <main id="main-content" tabindex="-1">
      <RouterView v-slot="{ Component, route }"><component :is="Component" :key="route.fullPath" /></RouterView>
    </main>
    <EditorialBoundary />
    <footer>Tu actividad permanece como borrador hasta una aprobación humana explícita.</footer>
  </div>
  </div>
</template>

<style scoped>
.skip-link { position: absolute; top: -8rem; left: var(--space-3); padding: var(--space-3); background: white; z-index: 10; }
.skip-link:focus { top: var(--space-1); }
.app-header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-3) max(var(--space-3), calc((100vw - 72rem) / 2)); background: var(--color-surface); border-bottom: 1px solid #686b6e; }
.brand { font-size: 1.5rem; font-weight: 750; text-decoration: none; min-height: 44px; display: inline-flex; align-items: center; }
nav { display: flex; flex-wrap: wrap; gap: var(--space-1); }
nav a { min-height: 44px; padding: var(--space-1); display: inline-flex; align-items: center; }
nav a[aria-current=page] { font-weight: 750; text-decoration-thickness: 3px; }
.app-body { max-width: 72rem; padding: var(--space-4) var(--space-3); margin-inline: auto; }
main { min-width: 0; }
footer { padding-block: var(--space-3); font-size: 0.9rem; }
.connection-status { padding: var(--space-3); border: 2px solid var(--color-review); background: var(--color-surface); }
@media (max-width: 420px) { .app-header { align-items: flex-start; } nav { width: 100%; } }
</style>
