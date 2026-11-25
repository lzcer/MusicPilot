<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  refreshData,
  playlists,
  playlistLoading,
  playlistDownloading,
  loadPlaylists,
  openPlaylistImportDialog,
  viewPlaylist,
  syncPlaylist,
  isPlaylistSyncingToLibrary,
  openPlaylistLibrarySyncDialog,
  downloadPlaylist,
  openDeletePlaylist,
  formatOptionalTime,
  playlistPlatformLabel,
  playlistStatusText,
  playlistStatusColor
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <div class="toolbar-row">
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openPlaylistImportDialog">
        新增
      </v-btn>
      <v-btn
        prepend-icon="mdi-refresh"
        variant="tonal"
        :loading="playlistLoading"
        @click="refreshData(loadPlaylists)"
      >
        刷新
      </v-btn>
    </div>
    <v-card>
      <v-progress-linear v-if="playlistLoading" indeterminate color="primary" />
      <v-table class="playlist-table fixed-table">
        <thead>
          <tr>
            <th class="playlist-name-col">歌单</th>
            <th class="playlist-platform-col">平台</th>
            <th class="count-col">歌曲</th>
            <th class="count-col">已存在</th>
            <th class="count-col">等待</th>
            <th class="count-col">已提交</th>
            <th class="count-col">失败</th>
            <th class="status-col">状态</th>
            <th class="time-col">最近同步</th>
            <th class="sticky-action-col playlist-action-col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!playlists.length">
            <td colspan="10" class="empty-cell">暂无歌单</td>
          </tr>
          <tr v-for="playlist in playlists" :key="playlist.id">
            <td>
              <div class="playlist-title-cell">
                <img
                  v-if="playlist.cover_url"
                  :src="playlist.cover_url"
                  alt=""
                  class="playlist-cover"
                  loading="lazy"
                />
                <div class="playlist-title-text">
                  <div class="truncate-text" :title="playlist.name">{{ playlist.name }}</div>
                  <div class="muted truncate-text" :title="playlist.owner_name || '-'">
                    {{ playlist.owner_name || '-' }}
                  </div>
                </div>
              </div>
            </td>
            <td class="truncate-cell" :title="playlistPlatformLabel(playlist.platform)">
              {{ playlistPlatformLabel(playlist.platform) }}
            </td>
            <td>{{ playlist.track_count }}</td>
            <td>{{ playlist.existing_count }}</td>
            <td>{{ playlist.waiting_count }}</td>
            <td>{{ playlist.submitted_count }}</td>
            <td>{{ playlist.failed_count }}</td>
            <td>
              <v-chip :color="playlistStatusColor(playlist.status)" size="small" variant="tonal">
                {{ playlistStatusText(playlist.status) }}
              </v-chip>
            </td>
            <td class="truncate-cell" :title="formatOptionalTime(playlist.last_synced_at)">
              {{ formatOptionalTime(playlist.last_synced_at) }}
            </td>
            <td class="sticky-action-col playlist-action-col">
              <v-btn
                icon="mdi-eye-outline"
                color="primary"
                variant="text"
                size="small"
                title="查看"
                @click="viewPlaylist(playlist)"
              />
              <v-btn
                icon="mdi-sync"
                color="primary"
                variant="text"
                size="small"
                title="同步来源"
                @click="syncPlaylist(playlist)"
              />
              <v-btn
                icon="mdi-playlist-check"
                color="primary"
                variant="text"
                size="small"
                title="同步到音乐库"
                :loading="isPlaylistSyncingToLibrary(playlist.id)"
                @click="openPlaylistLibrarySyncDialog(playlist)"
              />
              <v-btn
                icon="mdi-download"
                color="primary"
                variant="text"
                size="small"
                title="下载"
                :loading="playlistDownloading"
                @click="downloadPlaylist(playlist)"
              />
              <v-btn
                icon="mdi-delete-outline"
                color="error"
                variant="text"
                size="small"
                title="删除"
                @click="openDeletePlaylist(playlist)"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>
  </section>
</template>
