<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  mediaDeleteAllConfirmDialog,
  mediaDeleting,
  activeMediaDeleteMode,
  pendingMediaDeleteLabel,
  confirmDeleteMedia
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="mediaDeleteAllConfirmDialog" max-width="480">
    <v-card title="确认删除全部">
      <v-card-text class="dialog-stack">
        <div>确认删除{{ pendingMediaDeleteLabel || '整理记录' }}？</div>
        <v-alert type="error" variant="tonal" density="compact">
          此操作将删除整理记录、媒体文件以及源文件，且不可恢复。
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          variant="text"
          :disabled="mediaDeleting"
          @click="mediaDeleteAllConfirmDialog = false"
        >
          取消
        </v-btn>
        <v-btn
          color="error"
          :disabled="mediaDeleting"
          :loading="activeMediaDeleteMode === 'all'"
          @click="confirmDeleteMedia('all')"
        >
          确认删除全部
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
