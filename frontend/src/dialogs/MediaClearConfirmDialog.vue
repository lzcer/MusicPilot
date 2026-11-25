<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  mediaClearConfirmDialog,
  mediaClearing,
  pendingMediaClearMode,
  closeMediaClearConfirm,
  confirmClearMedia
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="mediaClearConfirmDialog" max-width="520">
    <v-card
      :title="pendingMediaClearMode === 'media_file' ? '再次确认删除媒体文件' : '再次确认清空记录'"
    >
      <v-card-text>
        <v-alert
          :type="pendingMediaClearMode === 'media_file' ? 'error' : 'warning'"
          variant="tonal"
          density="compact"
        >
          <template v-if="pendingMediaClearMode === 'media_file'">
            将永久清空全部整理记录，并删除记录关联的媒体库文件及对应音乐库索引；源文件不会被删除。此操作不可恢复。
          </template>
          <template v-else>
            将永久清空全部整理记录；媒体文件和源文件不会被删除。此操作不可恢复。
          </template>
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="mediaClearing" @click="closeMediaClearConfirm">
          取消
        </v-btn>
        <v-btn
          color="error"
          :disabled="mediaClearing"
          :loading="mediaClearing"
          @click="confirmClearMedia"
        >
          {{ pendingMediaClearMode === 'media_file' ? '确认删除媒体文件' : '确认清空记录' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
