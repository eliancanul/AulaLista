<script setup>
import UploadReview from './UploadReview.vue'
import { uncertainInterpretation } from './review-fixture.mjs'
defineEmits(['continue'])
</script>

<template>
  <UploadReview :initial-interpretation="uncertainInterpretation" fixture @continue="$emit('continue', $event)" />
</template>
