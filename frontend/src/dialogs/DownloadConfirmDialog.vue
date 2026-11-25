<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  pendingDownload,
  downloadSubmitting,
  torrentFiles,
  torrentFilesExpanded,
  torrentFilesLoading,
  torrentFilesError,
  collapsedTorrentDirectories,
  visibleTorrentFileNodes,
  searchResultType,
  toggleTorrentDirectory,
  toggleTorrentFiles,
  confirmDownload,
  formatSize
} = useWorkspace()
</script>

<template>
  <v-dialog
    :model-value="Boolean(pendingDownload)"
    max-width="560"
    scrollable
    @update:model-value="
      (value: boolean) => {
        if (!value) pendingDownload = null
      }
    "
  >
    <v-card class="download-confirm-card">
      <v-card-title class="download-confirm-title">
        <v-icon icon="mdi-monitor-arrow-down-variant" size="36" />
        <div>
          <div>确认下载</div>
          <div class="download-confirm-subtitle">
            {{ pendingDownload?.source }} - {{ pendingDownload?.title }}
          </div>
        </div>
      </v-card-title>
      <v-card-text v-if="pendingDownload" class="download-confirm-body">
        <div class="confirm-row">
          <v-icon icon="mdi-web" size="34" />
          <div>
            <div class="confirm-main-text">
              {{ pendingDownload.subtitle || pendingDownload.title }}
            </div>
            <div class="confirm-seeders">
              <span class="seeders"
                ><v-icon icon="mdi-arrow-up" size="18" />{{ pendingDownload.seeders }}</span
              >
              <span class="leechers"
                ><v-icon icon="mdi-arrow-down" size="18" />{{ pendingDownload.leechers || 0 }}</span
              >
            </div>
          </div>
        </div>
        <div class="confirm-row confirm-size-row">
          <v-icon icon="mdi-database" size="34" />
          <v-chip size="large" variant="tonal">{{ formatSize(pendingDownload.size_bytes) }}</v-chip>
          <v-btn
            color="primary"
            variant="text"
            size="small"
            :loading="torrentFilesLoading"
            :disabled="torrentFilesLoading"
            :aria-expanded="torrentFilesExpanded"
            @click="toggleTorrentFiles"
          >
            {{
              torrentFilesExpanded
                ? '收起文件列表'
                : torrentFilesError
                  ? '重试文件列表'
                  : '查看文件列表'
            }}
          </v-btn>
        </div>
        <div v-if="torrentFilesLoading" class="muted" role="status">正在获取并解析种子文件…</div>
        <v-alert
          v-if="torrentFilesError"
          type="error"
          variant="tonal"
          density="compact"
          role="alert"
        >
          {{ torrentFilesError }}
        </v-alert>
        <section v-if="torrentFilesExpanded && torrentFiles !== null" aria-label="种子文件列表">
          <div class="torrent-files-heading">文件列表（{{ torrentFiles.length }} 个文件）</div>
          <div v-if="!torrentFiles.length" class="muted">种子中没有可读取的文件条目</div>
          <div v-else class="torrent-files-scroll" tabindex="0" aria-label="滚动查看文件列表">
            <table class="torrent-files-table">
              <thead>
                <tr>
                  <th scope="col">名称</th>
                  <th scope="col">大小</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="node in visibleTorrentFileNodes" :key="node.id">
                  <td>
                    <div
                      class="torrent-file-node"
                      :style="{ '--torrent-file-indent': `${node.depth * 16}px` }"
                    >
                      <button
                        v-if="node.kind === 'directory'"
                        class="torrent-file-node-label torrent-file-directory"
                        type="button"
                        :title="node.path"
                        :aria-expanded="!collapsedTorrentDirectories.has(node.id)"
                        @click="toggleTorrentDirectory(node.id)"
                      >
                        <v-icon
                          :icon="
                            collapsedTorrentDirectories.has(node.id)
                              ? 'mdi-chevron-right'
                              : 'mdi-chevron-down'
                          "
                          size="16"
                        />
                        <v-icon
                          :icon="
                            collapsedTorrentDirectories.has(node.id)
                              ? 'mdi-folder-outline'
                              : 'mdi-folder-open-outline'
                          "
                          size="16"
                        />
                        <span>{{ node.name }}</span>
                      </button>
                      <div
                        v-else
                        class="torrent-file-node-label torrent-file-leaf"
                        :title="node.path"
                      >
                        <v-icon icon="mdi-file-outline" size="16" />
                        <span>{{ node.name }}</span>
                      </div>
                    </div>
                  </td>
                  <td>{{ node.kind === 'file' ? formatSize(node.size) : '' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <div class="confirm-row muted">
          <v-icon icon="mdi-clock-outline" size="28" />
          <span>{{ pendingDownload.published_at || '发布时间未知' }}</span>
        </div>
        <div v-if="pendingDownload.promotion" class="confirm-row confirm-promotion-row">
          <v-icon icon="mdi-tag-outline" size="28" />
          <v-chip color="success" size="large" variant="flat" class="confirm-promotion-chip">
            {{ pendingDownload.promotion }}
          </v-chip>
        </div>
        <div v-if="searchResultType(pendingDownload)" class="confirm-row muted">
          <v-icon icon="mdi-shape-outline" size="28" />
          <span>类型 {{ searchResultType(pendingDownload) }}</span>
        </div>
      </v-card-text>
      <v-card-actions class="download-confirm-actions">
        <v-btn variant="text" :disabled="downloadSubmitting" @click="pendingDownload = null"
          >取消</v-btn
        >
        <v-btn
          color="primary"
          prepend-icon="mdi-download"
          size="large"
          :loading="downloadSubmitting"
          :disabled="downloadSubmitting"
          @click="confirmDownload"
        >
          开始下载
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
