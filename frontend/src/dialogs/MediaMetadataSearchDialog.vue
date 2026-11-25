<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  mediaMetadataSearchDialog,
  mediaMetadataSearching,
  manualMetadataSearchQuery,
  manualMetadataSource,
  manualMetadataResults,
  manualOrganizeIsDirectory,
  metadataSourceOptions,
  metadataSourceLabel,
  searchManualMetadata,
  selectManualMetadata
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="mediaMetadataSearchDialog" max-width="920">
    <v-card :title="manualOrganizeIsDirectory ? '选择专辑' : '选择元数据'">
      <v-card-text class="dialog-stack">
        <div class="manual-search-row">
          <v-select
            v-model="manualMetadataSource"
            class="metadata-source-select"
            density="comfortable"
            hide-details
            :items="metadataSourceOptions"
            label="来源"
          />
          <v-text-field
            v-model="manualMetadataSearchQuery"
            class="manual-search-input"
            density="comfortable"
            hide-details
            label="搜索元数据"
            prepend-inner-icon="mdi-magnify"
            @keyup.enter="searchManualMetadata"
          />
          <v-btn
            color="primary"
            prepend-icon="mdi-magnify"
            :loading="mediaMetadataSearching"
            @click="searchManualMetadata"
          >
            搜索
          </v-btn>
        </div>
        <div v-if="mediaMetadataSearching" class="loading-panel">
          <v-progress-circular indeterminate color="primary" size="34" width="3" />
          <span>正在搜索元数据</span>
        </div>
        <div v-else-if="manualMetadataResults.length" class="metadata-result-grid">
          <article
            v-for="item in manualMetadataResults"
            :key="`${item.source || manualMetadataSource}:${item.source_id || item.title}:${item.album || ''}`"
            class="metadata-result-card"
            @click="selectManualMetadata(item)"
          >
            <img v-if="item.cover_url" class="metadata-result-cover" :src="item.cover_url" alt="" />
            <div class="metadata-result-body">
              <div class="metadata-result-title">{{ item.title || '-' }}</div>
              <div class="metadata-result-meta">{{ item.artist || '未知歌手' }}</div>
              <div class="metadata-result-meta">{{ item.album || '未知专辑' }}</div>
              <div class="metadata-result-tags">
                <v-chip size="small" variant="tonal">{{ item.year || '-' }}</v-chip>
                <v-chip size="small" variant="tonal">
                  {{ metadataSourceLabel(item.source || manualMetadataSource) }}
                </v-chip>
              </div>
              <p v-if="item.lyrics" class="metadata-result-lyrics">{{ item.lyrics }}</p>
            </div>
          </article>
        </div>
        <div v-else class="empty-cell">暂无元数据结果</div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="mediaMetadataSearchDialog = false">关闭</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
