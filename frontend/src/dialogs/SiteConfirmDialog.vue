<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  selectedMedia,
  siteConfirmDialog,
  selectedSiteIds,
  selectedAlbumNames,
  selectedMediaAlbums,
  enabledSites,
  canRunMetadataSiteSearch,
  runMetadataSiteSearch,
  selectAllAlbums,
  clearSelectedAlbums,
  toggleSelectedAlbum
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="siteConfirmDialog" max-width="620">
    <v-card title="确认搜索站点">
      <v-card-text class="dialog-stack">
        <div v-if="selectedMedia" class="site-confirm-media">
          <div class="site-confirm-label">媒体信息</div>
          <div class="site-confirm-title">{{ selectedMedia.title }}</div>
          <div class="site-confirm-line">{{ selectedMedia.artist || '未知艺人' }}</div>
          <div class="site-confirm-section-head site-confirm-album-label">
            <div class="site-confirm-label">专辑范围</div>
            <div v-if="selectedMediaAlbums.length" class="site-confirm-actions">
              <v-btn size="x-small" variant="text" @click="selectAllAlbums">全选</v-btn>
              <v-btn size="x-small" variant="text" @click="clearSelectedAlbums">清空</v-btn>
            </div>
          </div>
          <div v-if="selectedMediaAlbums.length" class="album-select-grid">
            <button
              v-for="album in selectedMediaAlbums"
              :key="album"
              type="button"
              class="album-select-chip"
              :class="{ 'is-selected': selectedAlbumNames.includes(album) }"
              :title="album"
              @click="toggleSelectedAlbum(album)"
            >
              <v-icon
                :icon="
                  selectedAlbumNames.includes(album)
                    ? 'mdi-checkbox-marked'
                    : 'mdi-checkbox-blank-outline'
                "
                size="18"
              />
              <span>{{ album }}</span>
            </button>
          </div>
          <div
            v-if="selectedMediaAlbums.length && !selectedAlbumNames.length"
            class="site-confirm-hint"
          >
            至少选择一个专辑后才能执行搜索
          </div>
          <div v-else-if="!selectedMediaAlbums.length" class="site-confirm-line">未知专辑</div>
        </div>
        <div>
          <div class="site-confirm-label site-confirm-site-label">站点范围</div>
          <div class="site-confirm-site-list">
            <v-checkbox
              v-for="site in enabledSites"
              :key="site.id || site.name"
              v-model="selectedSiteIds"
              :label="site.name"
              :value="site.id"
              density="compact"
              hide-details
            />
            <div v-if="!enabledSites.length" class="empty-cell">暂无启用站点</div>
          </div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="siteConfirmDialog = false">取消</v-btn>
        <v-btn color="primary" :disabled="!canRunMetadataSiteSearch" @click="runMetadataSiteSearch">
          执行搜索
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
