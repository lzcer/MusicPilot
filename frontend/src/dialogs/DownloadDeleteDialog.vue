<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  downloadDeleteDialog,
  downloadDeleting,
  activeDownloadDeleteMode,
  pendingDownloadDeleteLabel,
  confirmDeleteDownloads
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="downloadDeleteDialog" max-width="420">
    <v-card title="确认删除">
      <v-card-text> 请选择{{ pendingDownloadDeleteLabel }}的删除方式。 </v-card-text>
      <v-card-actions class="delete-action-buttons">
        <v-btn variant="text" :disabled="downloadDeleting" @click="downloadDeleteDialog = false">
          取消
        </v-btn>
        <v-spacer />
        <v-btn
          variant="tonal"
          :disabled="downloadDeleting"
          :loading="activeDownloadDeleteMode === 'record_only'"
          @click="confirmDeleteDownloads('record_only')"
        >
          仅删除记录
        </v-btn>
        <v-btn
          color="error"
          :disabled="downloadDeleting"
          :loading="activeDownloadDeleteMode === 'all'"
          @click="confirmDeleteDownloads('all')"
        >
          删除全部
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
