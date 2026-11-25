<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  playlists,
  libraryPlaylistDialog,
  libraryPlaylistTrack,
  libraryPlaylistId,
  libraryPlaylistSaving,
  libraryPlaylistDuplicate,
  playlistLoading,
  addLibraryTrackToPlaylist,
  playlistTrackLabel,
  locatePlaylistTrack
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="libraryPlaylistDialog" :persistent="libraryPlaylistSaving" max-width="480">
    <v-card title="加入歌单">
      <v-card-text class="dialog-stack">
        <div>
          {{ libraryPlaylistTrack?.title
          }}<span v-if="libraryPlaylistTrack?.artist"> · {{ libraryPlaylistTrack.artist }}</span>
        </div>
        <v-autocomplete
          v-model="libraryPlaylistId"
          :items="playlists"
          item-title="name"
          item-value="id"
          label="选择歌单"
          no-data-text="暂无歌单"
          :loading="playlistLoading"
          :disabled="libraryPlaylistSaving"
          hide-details
          @update:model-value="libraryPlaylistDuplicate = null"
        />
        <v-alert v-if="libraryPlaylistDuplicate" color="primary" variant="tonal" density="compact">
          <div class="d-flex align-center justify-space-between flex-wrap ga-2">
            <span>歌单中已存在：{{ playlistTrackLabel(libraryPlaylistDuplicate) }}</span>
            <v-btn
              variant="text"
              size="small"
              @click="locatePlaylistTrack(libraryPlaylistDuplicate)"
            >
              在歌单中查看
            </v-btn>
          </div>
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          variant="text"
          :disabled="libraryPlaylistSaving"
          @click="libraryPlaylistDialog = false"
          >取消</v-btn
        >
        <v-btn
          color="primary"
          :loading="libraryPlaylistSaving"
          :disabled="libraryPlaylistId === null || playlistLoading"
          @click="addLibraryTrackToPlaylist"
        >
          添加
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
