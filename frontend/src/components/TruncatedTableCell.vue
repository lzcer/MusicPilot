<template>
  <v-tooltip location="top" max-width="640">
    <template #activator="{ props: tooltipProps }">
      <span v-bind="tooltipProps" class="truncated-table-cell">{{ value }}</span>
    </template>
    <span class="truncated-table-tooltip">{{ tooltip }}</span>
  </v-tooltip>
</template>

<script setup lang="ts">
const props = defineProps<{
  value: string
  tooltip?: string
}>()

const tooltip = props.tooltip ?? props.value
</script>

<style scoped>
.truncated-table-cell {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.truncated-table-tooltip {
  overflow-wrap: anywhere;
  white-space: pre-line;
}
</style>
