<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  downloaderDialog,
  downloaderTesting,
  editingDownloaderId,
  downloaderForm,
  updateDownloaderPassword,
  selectDownloaderType,
  testDownloader,
  saveDownloader
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="downloaderDialog" max-width="560">
    <v-card :title="editingDownloaderId ? '编辑下载器' : '新增下载器'">
      <v-card-text class="dialog-stack">
        <v-select
          v-model="downloaderForm.type"
          :items="[
            { title: 'qBittorrent', value: 'qbittorrent' },
            { title: 'Transmission', value: 'transmission' }
          ]"
          label="类型"
          @update:model-value="selectDownloaderType"
        />
        <v-text-field v-model="downloaderForm.name" label="名称" />
        <v-text-field v-model="downloaderForm.base_url" label="地址" />
        <v-text-field v-model="downloaderForm.username" label="用户名" />
        <v-text-field
          :model-value="downloaderForm.password"
          label="密码"
          type="password"
          :placeholder="editingDownloaderId ? '留空则保持原密码' : ''"
          @update:model-value="updateDownloaderPassword"
        />
        <v-text-field
          v-model="downloaderForm.download_path"
          label="下载目录"
          placeholder="/downloads/music"
          required
        />
        <v-text-field
          v-model="downloaderForm.local_path"
          label="本机对应目录"
          placeholder="/volume1/music"
          required
        />
        <v-select
          v-model="downloaderForm.listen_mode"
          :items="
            downloaderForm.type === 'qbittorrent'
              ? [
                  { title: '轮询', value: 'polling' },
                  { title: 'qB 回调（预留）', value: 'qb_callback' }
                ]
              : [{ title: '轮询', value: 'polling' }]
          "
          label="监听模式"
          hint="用于监听下载进度"
          persistent-hint
        />
        <v-text-field
          v-if="downloaderForm.type === 'qbittorrent'"
          v-model="downloaderForm.monitor_tag"
          label="监听标签"
          placeholder="MusicPilot"
          hint="留空则关闭标签监听"
          persistent-hint
        />
        <v-switch
          v-model="downloaderForm.is_default"
          color="primary"
          label="设为默认"
          hide-details
        />
        <v-switch v-model="downloaderForm.enabled" color="primary" label="启用" hide-details />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="downloaderDialog = false">取消</v-btn>
        <v-btn :loading="downloaderTesting" variant="tonal" @click="testDownloader">测试</v-btn>
        <v-btn color="primary" @click="saveDownloader">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
