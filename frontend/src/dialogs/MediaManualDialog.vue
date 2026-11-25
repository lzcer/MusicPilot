<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  mediaManualDialog,
  mediaManualSubmitting,
  mediaMetadataSearching,
  manualOrganizeTarget,
  manualMetadataSearchQuery,
  manualOrganizeIsDirectory,
  manualMetadataForm,
  searchManualMetadata,
  confirmManualOrganize
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="mediaManualDialog" max-width="760">
    <v-card class="manual-organize-card" title="手动整理">
      <v-card-text class="dialog-stack manual-organize-body">
        <div class="manual-source-path">{{ manualOrganizeTarget?.source_path || '-' }}</div>
        <div class="manual-search-row">
          <v-text-field
            v-model="manualMetadataSearchQuery"
            class="manual-search-input"
            density="comfortable"
            hide-details
            :label="manualOrganizeIsDirectory ? '搜索专辑' : '搜索元数据'"
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
        <div class="manual-metadata-grid">
          <v-text-field
            v-if="!manualOrganizeIsDirectory"
            v-model="manualMetadataForm.title"
            label="标题"
          />
          <v-text-field v-model="manualMetadataForm.artist" label="歌手" />
          <v-text-field v-model="manualMetadataForm.album" label="专辑" />
          <v-text-field
            v-if="!manualOrganizeIsDirectory"
            v-model.number="manualMetadataForm.year"
            label="年份"
            type="number"
          />
          <v-text-field
            v-if="!manualOrganizeIsDirectory"
            v-model.number="manualMetadataForm.track_number"
            label="曲序"
            type="number"
          />
          <v-text-field
            v-if="!manualOrganizeIsDirectory"
            v-model="manualMetadataForm.cover_url"
            label="封面地址"
          />
        </div>
        <v-textarea
          v-if="!manualOrganizeIsDirectory"
          v-model="manualMetadataForm.lyrics"
          class="manual-lyrics-field"
          label="歌词"
          no-resize
          rows="8"
        />
      </v-card-text>
      <v-card-actions class="manual-organize-actions">
        <v-spacer />
        <v-btn variant="text" :disabled="mediaManualSubmitting" @click="mediaManualDialog = false">
          取消
        </v-btn>
        <v-btn color="primary" :loading="mediaManualSubmitting" @click="confirmManualOrganize">
          确认整理
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
