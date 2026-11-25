<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  musicLibraryQuery,
  musicLibraryPage,
  musicLibraryPageSize,
  musicLibraryTotal,
  musicLibraryStats,
  musicLibraryLoading,
  musicLibraryTracks,
  musicLibraryPageLength,
  loadMusicLibrary,
  applyMusicLibraryFilters,
  openLibraryPlaylistDialog,
  openLibraryDeleteDialog,
  syncMusicLibrary,
  formatSize,
  formatDuration
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <div class="toolbar-row">
      <v-btn
        prepend-icon="mdi-refresh"
        variant="tonal"
        :loading="musicLibraryLoading"
        @click="syncMusicLibrary"
      >
        同步
      </v-btn>
      <v-chip color="secondary" variant="tonal">Navidrome</v-chip>
      <v-chip color="primary" variant="tonal">歌曲 {{ musicLibraryStats.songs }}</v-chip>
      <v-chip color="primary" variant="tonal">专辑 {{ musicLibraryStats.albums }}</v-chip>
      <v-chip color="primary" variant="tonal">艺术家 {{ musicLibraryStats.artists }}</v-chip>
      <v-text-field
        v-model="musicLibraryQuery"
        label="搜索音乐库"
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        class="table-search"
        @keydown.enter="applyMusicLibraryFilters"
        @click:clear="applyMusicLibraryFilters"
      />
      <v-btn prepend-icon="mdi-magnify" variant="tonal" @click="applyMusicLibraryFilters">
        查询
      </v-btn>
    </div>
    <v-card>
      <v-progress-linear v-if="musicLibraryLoading" indeterminate color="primary" />
      <v-table class="music-library-table fixed-table">
        <thead>
          <tr>
            <th>标题</th>
            <th>艺人</th>
            <th>专辑</th>
            <th class="library-track-detail-col">时长</th>
            <th class="library-track-detail-col">大小</th>
            <th class="library-track-detail-col">年份</th>
            <th class="sticky-action-col library-track-action-col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!musicLibraryTracks.length">
            <td colspan="7" class="empty-cell">暂无音乐库记录</td>
          </tr>
          <tr v-for="track in musicLibraryTracks" :key="track.id">
            <td class="truncate-cell" :title="track.title">{{ track.title || '-' }}</td>
            <td class="truncate-cell" :title="track.artist ?? undefined">
              {{ track.artist || '-' }}
            </td>
            <td class="truncate-cell" :title="track.album ?? undefined">
              {{ track.album || '-' }}
            </td>
            <td>{{ formatDuration(track.duration) }}</td>
            <td>{{ formatSize(track.size) }}</td>
            <td>{{ track.year || '-' }}</td>
            <td class="sticky-action-col library-track-action-col">
              <div class="d-flex justify-center ga-1">
                <v-btn
                  icon="mdi-playlist-plus"
                  variant="text"
                  size="small"
                  title="加入歌单"
                  aria-label="加入歌单"
                  @click="openLibraryPlaylistDialog(track)"
                />
                <v-btn
                  icon="mdi-delete-outline"
                  variant="text"
                  size="small"
                  color="error"
                  title="删除歌曲"
                  aria-label="删除歌曲"
                  @click="openLibraryDeleteDialog(track)"
                />
              </div>
            </td>
          </tr>
        </tbody>
      </v-table>
      <div class="pagination-row">
        <v-select
          v-model="musicLibraryPageSize"
          :items="[10, 20, 50, 100]"
          density="comfortable"
          hide-details
          label="每页"
          class="page-size-select"
          @update:model-value="applyMusicLibraryFilters"
        />
        <v-pagination
          v-model="musicLibraryPage"
          :length="musicLibraryPageLength"
          density="comfortable"
          total-visible="5"
          @update:model-value="loadMusicLibrary"
        />
        <v-chip color="secondary" variant="tonal">共 {{ musicLibraryTotal }} 条</v-chip>
      </div>
    </v-card>
  </section>
</template>
