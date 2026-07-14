<template>
  <v-menu
    v-model="menuOpen"
    :close-on-content-click="false"
    location="bottom start"
    max-width="560"
    min-width="360"
  >
    <template #activator="{ props: activatorProps }">
      <v-text-field
        v-bind="activatorProps"
        :label="label"
        :model-value="modelValue"
        append-inner-icon="mdi-folder-open-outline"
        readonly
      />
    </template>

    <v-card class="directory-picker-panel">
      <v-card-text class="directory-picker-content">
        <div class="directory-picker-breadcrumbs">
          <v-btn
            v-for="breadcrumb in breadcrumbs"
            :key="`${breadcrumb.path}:${breadcrumb.title}`"
            :disabled="loading"
            size="small"
            variant="text"
            @click="loadDirectory(breadcrumb.path)"
          >
            {{ breadcrumb.title }}
          </v-btn>
        </div>

        <v-btn
          v-if="parentPath !== null"
          :disabled="loading"
          block
          class="directory-picker-parent"
          prepend-icon="mdi-arrow-up"
          variant="text"
          @click="loadDirectory(parentPath)"
        >
          返回上级
        </v-btn>

        <v-progress-linear v-if="loading" color="primary" indeterminate />
        <v-alert v-if="error" class="mb-2" density="compact" type="error" variant="tonal">
          {{ error }}
        </v-alert>

        <v-list v-if="entries.length" class="directory-picker-list" density="compact">
          <v-list-item
            v-for="entry in entries"
            :key="entry.path"
            :disabled="loading"
            :title="entry.name"
            append-icon="mdi-chevron-right"
            prepend-icon="mdi-folder-outline"
            @click="loadDirectory(entry.path)"
          />
        </v-list>
        <div v-else-if="!loading && !error" class="directory-picker-empty">
          当前目录下没有子目录
        </div>
      </v-card-text>

      <v-divider />
      <v-card-actions class="directory-picker-actions">
        <div class="directory-picker-current" :title="currentPath || '请选择磁盘'">
          {{ currentPath || '请选择磁盘' }}
        </div>
        <v-spacer />
        <v-btn variant="text" @click="menuOpen = false">取消</v-btn>
        <v-btn
          color="primary"
          :disabled="!currentPath || loading"
          variant="flat"
          @click="selectCurrentDirectory"
        >
          选择当前目录
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../api'

type DirectoryBreadcrumb = {
  title: string
  path: string
}

type DirectoryEntry = {
  name: string
  path: string
}

type DirectoryListResponse = {
  path?: string | null
  parent?: string | null
  breadcrumbs: DirectoryBreadcrumb[]
  entries: DirectoryEntry[]
}

const props = defineProps<{
  label: string
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const menuOpen = ref(false)
const loading = ref(false)
const error = ref('')
const currentPath = ref<string | null>(null)
const parentPath = ref<string | null>(null)
const breadcrumbs = ref<DirectoryBreadcrumb[]>([])
const entries = ref<DirectoryEntry[]>([])

watch(menuOpen, (open) => {
  if (open) void loadInitialDirectory()
})

async function loadInitialDirectory() {
  error.value = ''
  const initialPath = props.modelValue.trim()
  if (initialPath && (await loadDirectory(initialPath, false))) return
  await loadDirectory('')
}

async function loadDirectory(path: string, showError = true): Promise<boolean> {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (path) params.set('path', path)
    const query = params.toString()
    const response = await api<DirectoryListResponse>(
      `/api/directories${query ? `?${query}` : ''}`
    )
    currentPath.value = response.path ?? null
    parentPath.value = response.parent ?? null
    breadcrumbs.value = response.breadcrumbs
    entries.value = response.entries
    error.value = ''
    return true
  } catch (caught) {
    if (showError) {
      error.value = caught instanceof Error ? caught.message : '目录加载失败'
    }
    return false
  } finally {
    loading.value = false
  }
}

function selectCurrentDirectory() {
  if (!currentPath.value) return
  emit('update:modelValue', currentPath.value)
  menuOpen.value = false
}
</script>

<style scoped>
.directory-picker-panel {
  width: min(560px, calc(100vw - 32px));
}

.directory-picker-content {
  padding: 12px;
}

.directory-picker-breadcrumbs {
  display: flex;
  min-width: 0;
  overflow-x: auto;
  padding-bottom: 4px;
}

.directory-picker-breadcrumbs .v-btn {
  flex: 0 0 auto;
  min-width: 0;
  padding-inline: 8px;
}

.directory-picker-parent {
  justify-content: flex-start;
}

.directory-picker-list {
  max-height: 320px;
  overflow-y: auto;
}

.directory-picker-empty {
  color: rgb(var(--v-theme-on-surface-variant));
  padding: 24px 12px;
  text-align: center;
}

.directory-picker-actions {
  min-width: 0;
}

.directory-picker-current {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 12px;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
