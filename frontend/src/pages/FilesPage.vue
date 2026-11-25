<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  mediaManualSubmitting,
  fileRootType,
  fileEntries,
  selectedFilePaths,
  filePath,
  fileParent,
  fileRoot,
  fileLoading,
  fileError,
  fileSearchQuery,
  fileOrganizing,
  fileRootTypeOptions,
  fileBreadcrumbs,
  allFilesSelected,
  someFilesSelected,
  trimmedInput,
  openFileManualOrganize,
  loadFiles,
  openFileEntry,
  isAudioFile,
  openFileDetail,
  runFileSearch,
  clearFileSearch,
  openFileOrganize,
  organizeSelectedFiles,
  openFileDelete,
  deleteSelectedFiles,
  changeFileRootType,
  formatSize,
  formatTime
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <div class="toolbar-row">
      <v-select
        :model-value="fileRootType"
        :items="fileRootTypeOptions"
        item-title="title"
        item-value="value"
        label="当前目录"
        hide-details
        class="file-root-select"
        :disabled="fileLoading"
        @update:model-value="changeFileRootType"
      />
      <v-btn
        prepend-icon="mdi-refresh"
        variant="tonal"
        :loading="fileLoading"
        @click="loadFiles(filePath)"
      >
        刷新
      </v-btn>
      <v-btn
        prepend-icon="mdi-arrow-up"
        variant="tonal"
        :disabled="fileParent === null || fileLoading"
        @click="loadFiles(fileParent || '')"
      >
        上级目录
      </v-btn>
      <v-btn
        prepend-icon="mdi-playlist-check"
        color="primary"
        variant="tonal"
        :disabled="
          fileRootType !== 'source' || !selectedFilePaths.length || fileLoading || fileOrganizing
        "
        @click="organizeSelectedFiles"
      >
        批量整理
      </v-btn>
      <v-btn
        prepend-icon="mdi-delete"
        color="error"
        variant="tonal"
        :disabled="!selectedFilePaths.length || fileLoading"
        @click="deleteSelectedFiles"
      >
        删除
      </v-btn>
      <v-text-field
        v-model="fileSearchQuery"
        label="搜索文件"
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        class="file-search"
        @keyup.enter="runFileSearch"
        @click:clear="clearFileSearch"
      />
      <v-btn
        prepend-icon="mdi-magnify"
        variant="tonal"
        :loading="fileLoading"
        @click="runFileSearch"
      >
        搜索
      </v-btn>
      <v-chip v-if="fileRoot" color="secondary" variant="tonal">{{ fileRoot }}</v-chip>
    </div>

    <div class="file-breadcrumbs">
      <button
        v-for="(item, index) in fileBreadcrumbs"
        :key="item.path"
        class="file-breadcrumb"
        type="button"
        :disabled="item.path === filePath || fileLoading"
        @click="loadFiles(item.path)"
      >
        <span v-if="index > 0">/</span>
        {{ item.title }}
      </button>
    </div>

    <v-card>
      <v-progress-linear v-if="fileLoading" indeterminate color="primary" />
      <v-table>
        <thead>
          <tr>
            <th class="select-cell">
              <v-checkbox
                v-model="allFilesSelected"
                :indeterminate="someFilesSelected"
                density="compact"
                hide-details
              />
            </th>
            <th>名称</th>
            <th>类型</th>
            <th>大小</th>
            <th>修改时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="fileError">
            <td colspan="6" class="empty-cell">{{ fileError }}</td>
          </tr>
          <tr v-else-if="!fileEntries.length && !fileLoading">
            <td colspan="6" class="empty-cell">
              {{ trimmedInput(fileSearchQuery) ? '没有匹配文件' : '目录为空' }}
            </td>
          </tr>
          <tr
            v-for="entry in fileEntries"
            :key="entry.path"
            :class="{ 'file-row-clickable': entry.type === 'directory' }"
            @click="openFileEntry(entry)"
          >
            <td class="select-cell" @click.stop>
              <v-checkbox
                v-model="selectedFilePaths"
                :value="entry.path"
                density="compact"
                hide-details
              />
            </td>
            <td>
              <div class="file-name-cell">
                <v-icon
                  :icon="
                    entry.type === 'directory' ? 'mdi-folder-outline' : 'mdi-file-music-outline'
                  "
                  size="22"
                />
                <button
                  class="file-name-button"
                  type="button"
                  :disabled="entry.type !== 'directory'"
                  @click.stop="openFileEntry(entry)"
                >
                  {{ entry.name }}
                </button>
              </div>
            </td>
            <td>{{ entry.type === 'directory' ? '目录' : '文件' }}</td>
            <td>{{ entry.type === 'directory' ? '-' : formatSize(entry.size) }}</td>
            <td>{{ entry.modified_at ? formatTime(entry.modified_at) : '-' }}</td>
            <td>
              <v-btn
                v-if="isAudioFile(entry)"
                icon="mdi-eye-outline"
                color="primary"
                variant="text"
                size="small"
                title="查看"
                @click.stop="openFileDetail(entry)"
              />
              <v-btn
                icon="mdi-playlist-check"
                color="primary"
                variant="text"
                size="small"
                :disabled="fileRootType !== 'source' || fileOrganizing"
                :title="fileRootType === 'source' ? '整理' : '映射目录不能整理'"
                @click.stop="openFileOrganize(entry)"
              />
              <v-btn
                icon="mdi-pencil-box-outline"
                color="primary"
                variant="text"
                size="small"
                :disabled="fileRootType !== 'source' || mediaManualSubmitting"
                :title="fileRootType === 'source' ? '手动整理' : '仅源目录可手动整理'"
                @click.stop="openFileManualOrganize(entry)"
              />
              <v-btn
                icon="mdi-delete"
                color="error"
                variant="text"
                size="small"
                title="删除"
                @click.stop="openFileDelete(entry)"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>
  </section>
</template>
