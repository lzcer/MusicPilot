<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  sites,
  draggedSiteId,
  sitePrioritySaving,
  activeConfigMenu,
  openNewSiteDialog,
  editSite,
  startSiteDrag,
  finishSiteDrag,
  dropSite,
  openDeleteSite,
  configMenuKey,
  toggleConfigMenu
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <div class="toolbar-row">
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openNewSiteDialog">新增站点</v-btn>
    </div>
    <div class="card-grid">
      <v-card
        v-for="site in sites"
        :key="site.id || site.name"
        class="config-card site-config-card"
        :class="{ 'site-config-card-dragging': draggedSiteId === site.id }"
        :draggable="Boolean(site.id) && !sitePrioritySaving"
        @click="editSite(site)"
        @dragend="finishSiteDrag"
        @dragover.prevent
        @dragstart="startSiteDrag(site)"
        @drop.prevent="dropSite(site)"
      >
        <v-card-title class="config-card-title d-flex align-center">
          <v-icon class="site-drag-handle" icon="mdi-drag-vertical" size="small" />
          <span>{{ site.name }}</span>
          <v-spacer />
          <div v-if="site.id" class="config-card-menu" @click.stop>
            <v-btn
              icon="mdi-dots-vertical"
              size="small"
              variant="text"
              @click.stop="toggleConfigMenu('site', site.id)"
            />
            <v-card
              v-if="activeConfigMenu === configMenuKey('site', site.id)"
              class="config-card-menu-panel"
              elevation="0"
              @click.stop
            >
              <button class="config-card-menu-item" type="button" @click="openDeleteSite(site)">
                删除
              </button>
            </v-card>
          </div>
        </v-card-title>
        <v-card-text>
          <div class="muted">{{ site.base_url }}</div>
          <div class="mt-1">
            <v-chip size="small" :color="site.enabled ? 'success' : 'warning'" variant="tonal">
              {{ site.enabled ? '启用' : '停用' }}
            </v-chip>
            <v-chip size="small" variant="tonal" class="ml-1"
              >{{ site.max_concurrency }} 并发</v-chip
            >
            <v-chip size="small" variant="tonal" class="ml-1">优先级 {{ site.priority }}</v-chip>
            <v-chip v-if="site.use_proxy" size="small" color="primary" variant="tonal" class="ml-1"
              >代理</v-chip
            >
          </div>
        </v-card-text>
      </v-card>
    </div>
  </section>
</template>
