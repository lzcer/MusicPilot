<script setup lang="ts">
import { useWorkspace } from '../workspace'
import ScrollableTable from '../components/ScrollableTable.vue'
import TruncatedTableCell from '../components/TruncatedTableCell.vue'

const {
  downloadTaskItems,
  selectedDownloadTask,
  downloadItemsDialog,
  downloadItemsLoading,
  formatSize,
  downloadTaskItemStatusText,
  downloadTaskItemStatusColor
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="downloadItemsDialog" max-width="1120">
    <v-card
      :title="`下载明细${selectedDownloadTask?.name ? ` - ${selectedDownloadTask.name}` : ''}`"
    >
      <v-card-text>
        <v-progress-linear v-if="downloadItemsLoading" indeterminate class="mb-4" />
        <ScrollableTable class="fixed-table download-items-table" :min-width="1360">
          <thead>
            <tr>
              <th class="download-item-file-col">文件名</th>
              <th class="download-item-size-col">大小</th>
              <th class="download-item-title-col">解析标题</th>
              <th class="download-item-artist-col">任务艺术家</th>
              <th class="download-item-title-col">匹配标题</th>
              <th class="download-item-artist-col">匹配艺术家</th>
              <th class="download-item-album-col">专辑</th>
              <th class="download-item-status-col">状态</th>
              <th class="download-item-error-col">错误</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!downloadTaskItems.length">
              <td colspan="9" class="empty-cell">暂无明细</td>
            </tr>
            <tr v-for="item in downloadTaskItems" :key="item.id">
              <td><TruncatedTableCell :value="item.file_name" :tooltip="item.file_path" /></td>
              <td>{{ formatSize(item.size_bytes) }}</td>
              <td><TruncatedTableCell :value="item.parsed_title || '-'" /></td>
              <td><TruncatedTableCell :value="item.artist || '-'" /></td>
              <td><TruncatedTableCell :value="item.metadata_title || '-'" /></td>
              <td><TruncatedTableCell :value="item.metadata_artist || '-'" /></td>
              <td><TruncatedTableCell :value="item.metadata_album || '-'" /></td>
              <td>
                <v-chip
                  :color="downloadTaskItemStatusColor(item.status)"
                  size="small"
                  variant="tonal"
                >
                  {{ downloadTaskItemStatusText(item.status) }}
                </v-chip>
              </td>
              <td><TruncatedTableCell :value="item.last_error || '-'" /></td>
            </tr>
          </tbody>
        </ScrollableTable>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="downloadItemsDialog = false">关闭</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
