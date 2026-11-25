<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  availablePlaylists,
  selectedAvailablePlaylistIds,
  playlistImportUrl,
  playlistImportDialog,
  availablePlaylistLoading,
  importPlaylistUrl,
  importSelectedPlaylists,
  playlistPlatformLabel
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="playlistImportDialog" max-width="760">
    <v-card title="导入歌单">
      <v-card-text class="dialog-stack">
        <div class="toolbar-row">
          <v-text-field
            v-model="playlistImportUrl"
            label="歌单链接"
            hide-details
            class="platform-select"
            @keyup.enter="importPlaylistUrl"
          />
          <v-btn
            prepend-icon="mdi-link-variant-plus"
            color="primary"
            :loading="availablePlaylistLoading"
            :disabled="!playlistImportUrl.trim()"
            @click="importPlaylistUrl"
          >
            解析
          </v-btn>
        </div>
        <v-table>
          <thead>
            <tr>
              <th class="select-cell"></th>
              <th>封面</th>
              <th>歌单</th>
              <th>平台</th>
              <th>歌曲数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!availablePlaylists.length">
              <td colspan="5" class="empty-cell">请输入歌单链接并解析</td>
            </tr>
            <tr
              v-for="playlist in availablePlaylists"
              :key="playlist.import_token || playlist.external_id"
            >
              <td class="select-cell">
                <v-checkbox
                  v-model="selectedAvailablePlaylistIds"
                  :value="playlist.import_token || playlist.external_id"
                  density="compact"
                  hide-details
                />
              </td>
              <td>
                <v-img
                  v-if="playlist.cover_url"
                  :src="playlist.cover_url"
                  width="48"
                  height="48"
                  cover
                  class="playlist-cover"
                />
                <div v-else class="playlist-cover playlist-cover-placeholder">-</div>
              </td>
              <td>
                <div class="font-weight-medium">{{ playlist.name }}</div>
                <div class="muted-text">{{ playlist.owner_name || '-' }}</div>
              </td>
              <td>{{ playlist.platform ? playlistPlatformLabel(playlist.platform) : '-' }}</td>
              <td>{{ playlist.track_count }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          variant="text"
          :disabled="availablePlaylistLoading"
          @click="playlistImportDialog = false"
        >
          取消
        </v-btn>
        <v-btn
          color="primary"
          :loading="availablePlaylistLoading"
          :disabled="!selectedAvailablePlaylistIds.length"
          @click="importSelectedPlaylists"
        >
          确认同步
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
