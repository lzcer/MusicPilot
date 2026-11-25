<script setup lang="ts">
import { usePwaStore } from '../stores/pwa'

const pwa = usePwaStore()
</script>

<template>
  <aside v-if="!pwa.online || pwa.showUpdate" class="pwa-notice" role="status" aria-live="polite">
    <template v-if="!pwa.online">
      <strong>当前离线</strong>
      <p>页面可以打开，音乐库查询和操作需要联网。</p>
    </template>
    <template v-else>
      <strong>新版本已准备好</strong>
      <p>刷新即可使用。请先保存当前正在编辑的内容。</p>
      <p v-if="pwa.updateError" class="pwa-error">{{ pwa.updateError }}</p>
      <div class="pwa-actions">
        <v-btn variant="text" :disabled="pwa.updating" @click="pwa.showUpdate = false">稍后</v-btn>
        <v-btn color="primary" :loading="pwa.updating" @click="pwa.applyUpdate">刷新更新</v-btn>
      </div>
    </template>
  </aside>
</template>

<style scoped>
.pwa-notice {
  position: fixed;
  z-index: 2000;
  right: max(16px, env(safe-area-inset-right));
  bottom: max(16px, env(safe-area-inset-bottom));
  width: min(400px, calc(100vw - 32px));
  padding: 20px;
  border: 1px solid #dbe3ef;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(23 32 51 / 12%);
}
.pwa-notice p {
  margin: 8px 0 0;
  color: #667085;
  font-size: 14px;
}
.pwa-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
.pwa-notice .pwa-error {
  color: #dc2626;
}
</style>
