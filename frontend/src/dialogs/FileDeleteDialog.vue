<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  fileDeleteDialog,
  fileDeleting,
  pendingFileDeleteLabel,
  pendingFileDeleteHasDirectory,
  confirmFileDelete
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="fileDeleteDialog" max-width="480">
    <v-card title="确认删除">
      <v-card-text>
        确定删除{{ pendingFileDeleteLabel || '选中的项目' }}吗？
        <span v-if="pendingFileDeleteHasDirectory">目录会被递归删除。</span>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="fileDeleting" @click="fileDeleteDialog = false">
          取消
        </v-btn>
        <v-btn color="error" :loading="fileDeleting" @click="confirmFileDelete"> 删除 </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
