<script setup lang="ts">
import { defineAsyncComponent, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useAuthStore } from './stores/auth'

const AppLayout = defineAsyncComponent(() => import('./layouts/AppLayout.vue'))
const LoginPage = defineAsyncComponent(() => import('./pages/LoginPage.vue'))
const auth = useAuthStore()
const { status, error } = storeToRefs(auth)
onMounted(() => void auth.checkSession())
</script>

<template>
  <v-app>
    <AppLayout v-if="status === 'authenticated'" />
    <LoginPage v-else-if="status === 'anonymous'" />
    <main v-else class="startup-screen" aria-live="polite" :aria-busy="status === 'checking'">
      <div class="startup-content">
        <strong class="brand-title">MusicPilot</strong>
        <template v-if="status === 'error'">
          <p>{{ error }}</p>
          <v-btn color="primary" @click="auth.checkSession">重试连接</v-btn>
        </template>
        <template v-else>
          <v-progress-linear indeterminate color="primary" rounded />
          <span>正在连接音乐库</span>
        </template>
      </div>
    </main>
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
