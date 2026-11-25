<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { deleteDialog, deleting, deleteTarget, deleteTargetLabel, confirmDelete } = useWorkspace()
</script>

<template>
  <v-dialog v-model="deleteDialog" max-width="420">
    <v-card title="确认删除">
      <v-card-text>
        确定删除{{ deleteTargetLabel(deleteTarget) }}“{{ deleteTarget?.name }}”吗？
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="deleting" @click="deleteDialog = false">取消</v-btn>
        <v-btn color="error" :loading="deleting" @click="confirmDelete">删除</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
