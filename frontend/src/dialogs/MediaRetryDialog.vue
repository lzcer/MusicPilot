<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { mediaRetrying, mediaRetryDialog, pendingMediaRetryLabel, confirmRetryMedia } =
  useWorkspace()
</script>

<template>
  <v-dialog v-model="mediaRetryDialog" max-width="400">
    <v-card title="确认重试">
      <v-card-text>确认重试 {{ pendingMediaRetryLabel }} ？</v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="mediaRetrying" @click="mediaRetryDialog = false">
          取消
        </v-btn>
        <v-btn color="primary" variant="tonal" :loading="mediaRetrying" @click="confirmRetryMedia">
          确认重试
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
