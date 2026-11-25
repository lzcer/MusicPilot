<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  playlistTrackEditDialog,
  playlistTrackEditSaving,
  playlistTrackEditForm,
  savePlaylistTrackEdit
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="playlistTrackEditDialog" max-width="620">
    <v-card title="编辑歌单条目">
      <v-card-text class="dialog-stack">
        <v-text-field
          v-model="playlistTrackEditForm.title"
          label="歌名"
          autofocus
          @keyup.enter="savePlaylistTrackEdit"
        />
        <v-text-field v-model="playlistTrackEditForm.artist" label="歌手" />
        <v-text-field v-model="playlistTrackEditForm.album" label="专辑" />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          variant="text"
          :disabled="playlistTrackEditSaving"
          @click="playlistTrackEditDialog = false"
        >
          取消
        </v-btn>
        <v-btn
          color="primary"
          :loading="playlistTrackEditSaving"
          :disabled="!playlistTrackEditForm.title.trim()"
          @click="savePlaylistTrackEdit"
        >
          保存
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
