<script setup lang="ts">
import { useWorkspace } from '../workspace'
import ScrollableTable from '../components/ScrollableTable.vue'
import TruncatedTableCell from '../components/TruncatedTableCell.vue'

const {
  selectedPlaylist,
  playlistTracks,
  playlistTrackTitleQuery,
  playlistTrackArtistQuery,
  playlistTrackDownloadStatus,
  playlistTrackLibraryStatus,
  playlistTrackPage,
  playlistTrackPageSize,
  playlistTrackTotal,
  locatedPlaylistTrackId,
  playlistTracksDialog,
  playlistTrackLoading,
  playlistPageDownloading,
  playlistTrackDownloadStatusOptions,
  playlistTrackLibraryStatusOptions,
  playlistTrackPageLength,
  downloadablePlaylistTracks,
  viewPlaylist,
  loadPlaylistTracks,
  applyPlaylistTrackFilters,
  openPlaylistAddDialog,
  openPlaylistTrackEditDialog,
  isPlaylistTrackDownloading,
  canStartPlaylistTrackDownload,
  playlistTrackActionIcon,
  playlistTrackActionTitle,
  downloadPlaylistTrack,
  downloadPlaylistTrackPage,
  playlistTrackStatusText,
  playlistTrackStatusColor
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="playlistTracksDialog" max-width="980">
    <v-card>
      <v-card-title class="d-flex align-center ga-2">
        <span class="text-truncate">{{
          selectedPlaylist ? selectedPlaylist.name : '歌单明细'
        }}</span>
        <v-spacer />
        <v-menu>
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              prepend-icon="mdi-plus"
              variant="tonal"
              size="small"
              :disabled="!selectedPlaylist"
            >
              添加
            </v-btn>
          </template>
          <v-list density="compact">
            <v-list-item
              prepend-icon="mdi-music-circle-outline"
              title="从音乐库添加"
              @click="openPlaylistAddDialog('library')"
            />
            <v-list-item
              prepend-icon="mdi-web"
              title="从网络添加"
              @click="openPlaylistAddDialog('network')"
            />
          </v-list>
        </v-menu>
        <v-btn
          prepend-icon="mdi-download-multiple"
          variant="tonal"
          size="small"
          title="下载本页"
          :loading="playlistPageDownloading"
          :disabled="
            !selectedPlaylist ||
            playlistTrackLoading ||
            playlistPageDownloading ||
            !downloadablePlaylistTracks.length
          "
          @click="downloadPlaylistTrackPage"
        >
          下载本页
        </v-btn>
        <v-btn
          icon="mdi-refresh"
          variant="text"
          size="small"
          title="刷新"
          :loading="playlistTrackLoading"
          :disabled="!selectedPlaylist"
          @click="selectedPlaylist && loadPlaylistTracks(selectedPlaylist)"
        />
      </v-card-title>
      <v-card-text>
        <div class="toolbar-row dialog-filter-row">
          <v-text-field
            v-model="playlistTrackTitleQuery"
            label="歌名"
            prepend-inner-icon="mdi-magnify"
            density="compact"
            hide-details
            clearable
            @keyup.enter="applyPlaylistTrackFilters"
            @click:clear="applyPlaylistTrackFilters"
          />
          <v-text-field
            v-model="playlistTrackArtistQuery"
            label="歌手"
            prepend-inner-icon="mdi-account-music-outline"
            density="compact"
            hide-details
            clearable
            @keyup.enter="applyPlaylistTrackFilters"
            @click:clear="applyPlaylistTrackFilters"
          />
          <v-select
            v-model="playlistTrackDownloadStatus"
            :items="playlistTrackDownloadStatusOptions"
            label="下载状态"
            density="compact"
            hide-details
            @update:model-value="applyPlaylistTrackFilters"
          />
          <v-select
            v-model="playlistTrackLibraryStatus"
            :items="playlistTrackLibraryStatusOptions"
            label="在库状态"
            density="compact"
            hide-details
            @update:model-value="applyPlaylistTrackFilters"
          />
          <v-btn prepend-icon="mdi-magnify" variant="tonal" @click="applyPlaylistTrackFilters">
            查询
          </v-btn>
        </div>
        <v-alert
          v-if="locatedPlaylistTrackId !== null"
          color="primary"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          <div class="d-flex align-center justify-space-between flex-wrap ga-2">
            <span>正在查看定位到的曲目</span>
            <v-btn
              variant="text"
              size="small"
              @click="selectedPlaylist && viewPlaylist(selectedPlaylist)"
            >
              显示全部曲目
            </v-btn>
          </div>
        </v-alert>
        <v-progress-linear v-if="playlistTrackLoading" indeterminate color="primary" />
        <ScrollableTable class="playlist-track-table fixed-table" :min-width="1180">
          <thead>
            <tr>
              <th class="track-position-col">#</th>
              <th class="track-title-col">歌曲</th>
              <th class="track-artist-col">艺人</th>
              <th class="track-album-col">专辑</th>
              <th class="track-error-col">错误</th>
              <th class="sticky-track-col sticky-track-library-col">音乐库</th>
              <th class="sticky-track-col sticky-track-status-col">下载状态</th>
              <th class="sticky-track-col sticky-track-download-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!playlistTracks.length && !playlistTrackLoading">
              <td colspan="8" class="empty-cell">
                {{ locatedPlaylistTrackId === null ? '暂无歌曲' : '该曲目已不在歌单中' }}
              </td>
            </tr>
            <tr v-for="track in playlistTracks" :key="track.id">
              <td>{{ track.position }}</td>
              <td><TruncatedTableCell :value="track.title" /></td>
              <td><TruncatedTableCell :value="track.artist || '-'" /></td>
              <td><TruncatedTableCell :value="track.album || '-'" /></td>
              <td><TruncatedTableCell :value="track.last_error || '-'" /></td>
              <td class="sticky-track-col sticky-track-library-col">
                <v-icon
                  v-if="track.exists_in_library"
                  icon="mdi-check-circle"
                  color="success"
                  size="22"
                  title="已存在"
                />
                <span v-else>-</span>
              </td>
              <td class="sticky-track-col sticky-track-status-col">
                <v-chip
                  :color="playlistTrackStatusColor(track.download_status)"
                  size="small"
                  variant="tonal"
                >
                  {{ playlistTrackStatusText(track.download_status) }}
                </v-chip>
              </td>
              <td class="sticky-track-col sticky-track-download-col">
                <v-btn
                  icon="mdi-pencil-outline"
                  color="primary"
                  variant="text"
                  size="small"
                  title="编辑"
                  @click="openPlaylistTrackEditDialog(track)"
                />
                <v-btn
                  :icon="playlistTrackActionIcon(track)"
                  color="primary"
                  variant="text"
                  size="small"
                  :title="playlistTrackActionTitle(track)"
                  :loading="isPlaylistTrackDownloading(track.id)"
                  :disabled="!canStartPlaylistTrackDownload(track)"
                  @click="downloadPlaylistTrack(track)"
                />
              </td>
            </tr>
          </tbody>
        </ScrollableTable>
        <div class="pagination-row">
          <v-select
            v-model="playlistTrackPageSize"
            :items="[20, 50, 100]"
            label="每页"
            density="compact"
            hide-details
            class="page-size-select"
            @update:model-value="applyPlaylistTrackFilters"
          />
          <v-pagination
            v-model="playlistTrackPage"
            :length="playlistTrackPageLength"
            density="comfortable"
            total-visible="7"
            @update:model-value="selectedPlaylist && loadPlaylistTracks(selectedPlaylist)"
          />
          <v-chip color="secondary" variant="tonal">共 {{ playlistTrackTotal }} 首</v-chip>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="playlistTracksDialog = false">关闭</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
