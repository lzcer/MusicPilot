<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  notifierDialog,
  notifierTesting,
  editingNotifierId,
  notifierForm,
  updateNotifierBotToken,
  testNotifier,
  saveNotifier
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="notifierDialog" max-width="560">
    <v-card :title="editingNotifierId ? '编辑通知' : '新增通知'">
      <v-card-text class="dialog-stack">
        <v-select v-model="notifierForm.type" :items="['telegram']" label="类型" />
        <v-text-field v-model="notifierForm.name" label="名称" />
        <v-text-field
          :model-value="notifierForm.bot_token"
          label="Bot Token"
          type="password"
          :placeholder="editingNotifierId ? '留空则保持原 Token' : ''"
          @update:model-value="updateNotifierBotToken"
        />
        <v-text-field v-model="notifierForm.webhook_url" label="Webhook URL" />
        <v-text-field v-model="notifierForm.chat_ids" label="Chat IDs" />
        <v-switch
          v-model="notifierForm.use_proxy"
          color="primary"
          label="使用系统代理"
          hide-details
        />
        <v-switch
          v-model="notifierForm.enable_download_notify"
          color="primary"
          label="下载通知"
          hide-details
        />
        <v-switch
          v-model="notifierForm.enable_library_notify"
          color="primary"
          label="媒体库刷新通知"
          hide-details
        />
        <v-switch v-model="notifierForm.enabled" color="primary" label="启用" hide-details />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="notifierDialog = false">取消</v-btn>
        <v-btn :loading="notifierTesting" variant="tonal" @click="testNotifier">测试</v-btn>
        <v-btn color="primary" @click="saveNotifier">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
