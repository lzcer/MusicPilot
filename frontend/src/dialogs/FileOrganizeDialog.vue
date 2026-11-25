<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  fileOrganizeDialog,
  fileOrganizing,
  pendingFileOrganizeLabel,
  pendingFileOrganizeHasDirectory,
  confirmFileOrganize
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="fileOrganizeDialog" max-width="460">
    <v-card title="确认整理">
      <v-card-text>
        确定整理{{ pendingFileOrganizeLabel || '选中的项目' }}吗？
        <span v-if="pendingFileOrganizeHasDirectory">目录中的音频文件会批量刮削转移。</span>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="fileOrganizing" @click="fileOrganizeDialog = false">
          取消
        </v-btn>
        <v-btn color="primary" :loading="fileOrganizing" @click="confirmFileOrganize"> 整理 </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
