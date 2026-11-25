<script setup lang="ts">
import { ref } from 'vue'
import { ApiError } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function login() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    password.value = ''
  } catch (cause) {
    error.value =
      cause instanceof ApiError && cause.status === 401
        ? '用户名或密码错误'
        : '登录失败，请检查服务连接后重试。'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-screen">
    <v-card class="login-card">
      <v-card-title class="text-h5 font-weight-bold">MusicPilot</v-card-title>
      <v-card-text>
        <v-form @submit.prevent="login">
          <v-text-field v-model="username" label="用户名" autocomplete="username" />
          <v-text-field
            v-model="password"
            label="密码"
            type="password"
            autocomplete="current-password"
          />
          <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
          <v-btn block color="primary" size="large" type="submit" :loading="loading">登录</v-btn>
        </v-form>
      </v-card-text>
    </v-card>
  </main>
</template>
