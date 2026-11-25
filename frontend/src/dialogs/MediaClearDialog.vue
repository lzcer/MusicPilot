<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { mediaClearDialog, mediaClearing, requestClearMedia } = useWorkspace()
</script>

<template>
  <v-dialog v-model="mediaClearDialog" max-width="580">
    <v-card title="清空全部整理记录">
      <v-card-text class="dialog-stack">
        <div>此操作将作用于全部整理记录，不受当前搜索条件、状态筛选、分页或勾选项影响。</div>
        <v-alert type="warning" variant="tonal" density="compact">
          <div>仅删除记录：清空整理记录，保留媒体文件和源文件。</div>
          <div>删除媒体文件：清空整理记录及关联的媒体库文件，保留源文件。</div>
        </v-alert>
      </v-card-text>
      <v-card-actions class="delete-action-buttons">
        <v-btn variant="text" :disabled="mediaClearing" @click="mediaClearDialog = false">
          取消
        </v-btn>
        <v-spacer />
        <v-btn variant="tonal" :disabled="mediaClearing" @click="requestClearMedia('record_only')">
          仅删除记录
        </v-btn>
        <v-btn color="error" :disabled="mediaClearing" @click="requestClearMedia('media_file')">
          删除媒体文件
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
