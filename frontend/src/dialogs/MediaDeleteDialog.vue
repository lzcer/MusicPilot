<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  mediaDeleteDialog,
  mediaDeleting,
  activeMediaDeleteMode,
  pendingMediaDeleteLabel,
  requestDeleteMedia
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="mediaDeleteDialog" max-width="520">
    <v-card title="确认删除">
      <v-card-text> 请选择{{ pendingMediaDeleteLabel || '整理记录' }}的删除方式。 </v-card-text>
      <v-card-actions class="delete-action-buttons">
        <v-btn variant="text" :disabled="mediaDeleting" @click="mediaDeleteDialog = false">
          取消
        </v-btn>
        <v-spacer />
        <v-btn
          variant="tonal"
          :disabled="mediaDeleting"
          :loading="activeMediaDeleteMode === 'record_only'"
          @click="requestDeleteMedia('record_only')"
        >
          仅删除记录
        </v-btn>
        <v-btn
          color="warning"
          variant="tonal"
          :disabled="mediaDeleting"
          :loading="activeMediaDeleteMode === 'media_file'"
          @click="requestDeleteMedia('media_file')"
        >
          删除媒体文件
        </v-btn>
        <v-btn
          color="error"
          :disabled="mediaDeleting"
          :loading="activeMediaDeleteMode === 'all'"
          @click="requestDeleteMedia('all')"
        >
          删除全部
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
