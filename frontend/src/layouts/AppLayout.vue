<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { provideWorkspace } from '../workspace'
import { installPageLifecycle } from '../workspace/lifecycle'
import WorkspaceDialogs from '../dialogs/WorkspaceDialogs.vue'
import '../styles/workspace.css'

const workspace = provideWorkspace()
const { activePage, drawer, navGroups, pageTitle, switchPage, activeConfigMenu, snackbar } =
  workspace
const route = useRoute()
const routeError = ref(false)
function handleRouteError() {
  routeError.value = true
}
window.addEventListener('musicpilot:route-error', handleRouteError)
onUnmounted(() => window.removeEventListener('musicpilot:route-error', handleRouteError))
installPageLifecycle(workspace)
function reload() {
  window.location.reload()
}
</script>

<template>
  <div class="workspace" @click="activeConfigMenu = null">
    <v-navigation-drawer v-model="drawer" width="244">
      <div class="brand-block">
        <div class="brand-title">MusicPilot</div>
        <div class="brand-subtitle">音乐库自动化</div>
      </div>
      <v-list nav density="compact" class="nav-list">
        <v-list-item
          :active="activePage === 'dashboard'"
          prepend-icon="mdi-view-dashboard-outline"
          title="仪表盘"
          rounded="lg"
          @click="switchPage('dashboard')"
        />
        <v-list-item
          :active="activePage === 'discovery'"
          prepend-icon="mdi-compass-outline"
          title="发现"
          rounded="lg"
          @click="switchPage('discovery')"
        />
        <v-divider class="nav-group-divider" />
        <template v-for="(group, index) in navGroups" :key="group.title">
          <v-divider v-if="index > 0" class="nav-group-divider" />
          <v-list-subheader class="nav-group-title">{{ group.title }}</v-list-subheader>
          <v-list-item
            v-for="item in group.items"
            :key="item.value"
            :active="activePage === item.value"
            :prepend-icon="item.icon"
            :title="item.title"
            rounded="lg"
            @click="switchPage(item.value)"
          />
        </template>
      </v-list>
    </v-navigation-drawer>
    <v-app-bar height="64" flat border>
      <v-app-bar-nav-icon @click="drawer = !drawer" />
      <v-toolbar-title>{{ pageTitle }}</v-toolbar-title>
      <v-spacer />
    </v-app-bar>
    <v-main>
      <div class="content">
        <v-alert v-if="routeError" type="warning" variant="tonal" class="mb-4">
          页面资源加载失败，请检查网络或刷新以获取最新版本。
          <v-btn variant="text" @click="reload">刷新页面</v-btn>
        </v-alert>
        <router-view v-slot="{ Component }">
          <keep-alive :max="12">
            <component :is="Component" :key="route.name" />
          </keep-alive>
        </router-view>
      </div>
    </v-main>
    <WorkspaceDialogs />
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" location="top right">{{
      snackbar.text
    }}</v-snackbar>
  </div>
</template>
