<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  refreshData,
  selectedDownloadIds,
  downloadActiveOnly,
  filteredDownloads,
  downloadEmptyText,
  allDownloadsSelected,
  someDownloadsSelected,
  downloadCreationTypeText,
  loadDownloads,
  viewDownloadItems,
  deleteDownloadTask,
  deleteSelectedDownloads,
  progressPercent,
  formatSize,
  downloadStatusText,
  downloadStatusColor
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <div class="toolbar-row download-toolbar">
      <v-btn prepend-icon="mdi-refresh" variant="tonal" @click="refreshData(loadDownloads)"
        >刷新</v-btn
      >
      <v-btn
        prepend-icon="mdi-delete"
        color="error"
        variant="tonal"
        :disabled="!selectedDownloadIds.length"
        @click="deleteSelectedDownloads"
      >
        删除
      </v-btn>
      <v-switch
        v-model="downloadActiveOnly"
        class="download-active-switch"
        color="primary"
        density="compact"
        hide-details
        inset
        label="仅看活跃"
      />
    </div>
    <v-card>
      <v-table class="download-table">
        <thead>
          <tr>
            <th class="select-cell">
              <v-checkbox
                v-model="allDownloadsSelected"
                :indeterminate="someDownloadsSelected"
                density="compact"
                hide-details
              />
            </th>
            <th class="download-name-cell">名称</th>
            <th class="download-type-cell">下载类型</th>
            <th class="download-size-cell">大小</th>
            <th class="download-status-cell">状态</th>
            <th class="download-progress-cell">进度</th>
            <th class="download-path-cell">保存路径</th>
            <th class="download-actions-cell">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!filteredDownloads.length">
            <td colspan="8" class="empty-cell">{{ downloadEmptyText }}</td>
          </tr>
          <tr v-for="row in filteredDownloads" :key="row.id || row.torrent_hash || row.name">
            <td class="select-cell">
              <v-checkbox
                v-if="typeof row.id === 'number'"
                v-model="selectedDownloadIds"
                :value="row.id"
                density="compact"
                hide-details
              />
            </td>
            <td class="download-name-cell">
              <span :title="row.name">{{ row.name }}</span>
            </td>
            <td class="download-type-cell">{{ downloadCreationTypeText(row.creation_type) }}</td>
            <td class="download-size-cell">{{ formatSize(row.size_bytes) }}</td>
            <td class="download-status-cell">
              <v-chip :color="downloadStatusColor(row.state)" size="small" variant="tonal">
                {{ downloadStatusText(row.state) }}
              </v-chip>
            </td>
            <td class="download-progress-cell">
              <v-progress-linear :model-value="progressPercent(row.progress)" height="8" rounded />
            </td>
            <td class="download-path-cell path-cell">{{ row.save_path || '-' }}</td>
            <td class="download-actions-cell table-actions">
              <v-btn
                icon="mdi-format-list-bulleted"
                color="primary"
                variant="text"
                size="small"
                title="查看明细"
                :disabled="typeof row.id !== 'number'"
                @click="viewDownloadItems(row)"
              />
              <v-btn
                icon="mdi-delete"
                color="error"
                variant="text"
                size="small"
                title="删除任务"
                :disabled="typeof row.id !== 'number'"
                @click="deleteDownloadTask(row)"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>
  </section>
</template>
