<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  playlistLibrarySyncDialog,
  playlistLibrarySyncForm,
  enabledMediaServerOptions,
  isPlaylistSyncingToLibrary,
  applyPlaylistLibrarySyncBinding,
  syncPlaylistToLibrary
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="playlistLibrarySyncDialog" max-width="520">
    <v-card title="同步到音乐库">
      <v-card-text class="dialog-stack">
        <div class="muted">
          {{ playlistLibrarySyncForm.playlist?.name || '-' }}
        </div>
        <v-select
          v-model="playlistLibrarySyncForm.media_server_id"
          :items="enabledMediaServerOptions"
          item-title="title"
          item-value="value"
          label="同步账号"
          no-data-text="暂无已启用的音乐库账号"
          @update:model-value="applyPlaylistLibrarySyncBinding"
        />
        <v-switch
          v-model="playlistLibrarySyncForm.public"
          color="primary"
          density="compact"
          hide-details
          inset
          label="公开"
        />
        <v-switch
          v-model="playlistLibrarySyncForm.auto_sync"
          color="primary"
          density="compact"
          hide-details
          inset
          label="自动双向同步"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="playlistLibrarySyncDialog = false">取消</v-btn>
        <v-btn
          color="primary"
          :disabled="!playlistLibrarySyncForm.media_server_id || !playlistLibrarySyncForm.playlist"
          :loading="
            playlistLibrarySyncForm.playlist
              ? isPlaylistSyncingToLibrary(playlistLibrarySyncForm.playlist.id)
              : false
          "
          @click="syncPlaylistToLibrary"
        >
          同步
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
