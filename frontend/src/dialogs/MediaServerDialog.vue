<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  mediaServerDialog,
  mediaServerTesting,
  editingMediaServerId,
  mediaServerUserForm,
  updateMediaServerUserPassword,
  testMediaServerUser,
  saveMediaServerUser
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="mediaServerDialog" max-width="560">
    <v-card :title="editingMediaServerId ? '编辑音乐库用户' : '新增音乐库用户'">
      <v-card-text class="dialog-stack">
        <v-text-field v-model="mediaServerUserForm.username" label="用户名" autofocus />
        <v-text-field
          :model-value="mediaServerUserForm.password"
          label="密码"
          type="password"
          :placeholder="editingMediaServerId ? '留空则保持原密码' : ''"
          @update:model-value="updateMediaServerUserPassword"
        />
        <v-switch v-model="mediaServerUserForm.enabled" color="primary" label="启用" hide-details />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="mediaServerDialog = false">取消</v-btn>
        <v-btn :loading="mediaServerTesting" variant="tonal" @click="testMediaServerUser"
          >测试</v-btn
        >
        <v-btn color="primary" @click="saveMediaServerUser">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
