<script setup lang="ts">
withDefaults(defineProps<{ title: string; detail?: string; kind?: 'empty' | 'loading' | 'error' | 'ready' }>(), { kind: 'empty' });
</script>

<template>
  <section class="app-status" :class="`app-status--${kind}`" :aria-busy="kind === 'loading'">
    <p :role="kind === 'error' ? 'alert' : 'status'" aria-live="polite"><strong>{{ title }}</strong></p>
    <p v-if="detail">{{ detail }}</p>
    <slot />
  </section>
</template>
