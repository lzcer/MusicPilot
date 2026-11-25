<script setup lang="ts">
import { defineAsyncComponent, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAuthStore } from './stores/auth'
import { usePwaStore } from './stores/pwa'
import PwaStatus from './components/PwaStatus.vue'

const AppLayout = defineAsyncComponent(() => import('./layouts/AppLayout.vue'))
const LoginPage = defineAsyncComponent(() => import('./pages/LoginPage.vue'))
const auth = useAuthStore()
const pwa = usePwaStore()
pwa.initialize()
const { status, error } = storeToRefs(auth)
onMounted(() => void auth.checkSession())
watch(
  () => pwa.online,
  (online) => {
    if (online && status.value === 'error') void auth.checkSession()
  }
)
</script>

<template>
  <v-app>
    <AppLayout v-if="status === 'authenticated'" />
    <LoginPage v-else-if="status === 'anonymous'" />
    <main v-else class="startup-screen" aria-live="polite" :aria-busy="status === 'checking'">
      <div class="startup-content">
        <strong class="brand-title">MusicPilot</strong>
        <template v-if="status === 'error'">
          <p>{{ pwa.online ? error : '当前离线，连接网络后即可访问音乐库。' }}</p>
          <v-btn color="primary" @click="auth.checkSession">重试连接</v-btn>
        </template>
        <template v-else>
          <v-progress-linear indeterminate color="primary" rounded />
          <span>正在连接音乐库</span>
        </template>
      </div>
    </main>
    <PwaStatus />
  </v-app>
</template>

<style scoped>
.startup-screen {
  min-height: 100dvh;
  display: grid;
  place-items: center;
}
.startup-content {
  width: min(320px, calc(100vw - 48px));
  display: grid;
  gap: 20px;
  text-align: center;
}
.startup-content span,
.startup-content p {
  color: #667085;
  font-size: 14px;
}
</style>
