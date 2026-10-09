<script setup lang="ts">
withDefaults(defineProps<{ type?: 'button' | 'submit'; busy?: boolean; disabled?: boolean }>(), { type: 'button', busy: false, disabled: false });
</script>

<template>
  <button class="primary-action" :type="type" :disabled="disabled || busy" :aria-busy="busy"><slot /></button>
</template>
