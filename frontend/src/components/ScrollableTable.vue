<template>
  <div
    class="scrollable-table"
    v-bind="$attrs"
    :style="{ '--scrollable-table-min-width': tableMinWidth }"
  >
    <v-table>
      <slot />
    </v-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    minWidth?: string | number
  }>(),
  { minWidth: '100%' }
)

const tableMinWidth = computed(() =>
  typeof props.minWidth === 'number' ? `${props.minWidth}px` : props.minWidth
)
</script>

<style scoped>
.scrollable-table {
  min-width: 0;
  overflow: hidden;
}

.scrollable-table :deep(.v-table__wrapper) {
  overflow-x: auto;
}

.scrollable-table :deep(table) {
  table-layout: fixed;
  min-width: var(--scrollable-table-min-width, 100%);
  width: max(100%, var(--scrollable-table-min-width, 100%));
}

.scrollable-table :deep(th),
.scrollable-table :deep(td) {
  overflow: hidden;
  white-space: nowrap;
}
</style>
