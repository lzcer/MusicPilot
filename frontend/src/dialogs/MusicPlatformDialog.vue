<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { musicPlatformDialog, musicPlatformConnecting, musicPlatformForm, connectMusicPlatform } =
  useWorkspace()
</script>

<template>
  <v-dialog v-model="musicPlatformDialog" max-width="620">
    <v-card title="关联音乐平台">
      <v-card-text class="dialog-stack">
        <v-select
          v-model="musicPlatformForm.platform"
          :items="[{ title: 'Spotify', value: 'spotify' }]"
          label="平台"
        />
        <v-text-field v-model="musicPlatformForm.client_id" label="Client ID" />
        <v-text-field
          v-model="musicPlatformForm.client_secret"
          label="Client Secret"
          type="password"
        />
        <v-text-field v-model="musicPlatformForm.redirect_uri" label="Redirect URI" />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          variant="text"
          :disabled="musicPlatformConnecting"
          @click="musicPlatformDialog = false"
        >
          取消
        </v-btn>
        <v-btn color="primary" :loading="musicPlatformConnecting" @click="connectMusicPlatform">
          下一步
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
