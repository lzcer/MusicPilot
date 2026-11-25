<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  searchDialog,
  searchText,
  searchArtist,
  searchLoading,
  trimmedInput,
  runSearch,
  openDirectSiteSearchConfirm
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="searchDialog" max-width="460">
    <v-card title="搜索">
      <v-card-text class="dialog-stack">
        <v-text-field
          v-model="searchText"
          label="歌曲名"
          persistent-hint
          autofocus
          @keyup.enter="runSearch"
        />
        <v-text-field
          v-model="searchArtist"
          label="歌手（可选）"
          hint="直接搜索站点时不会使用"
          persistent-hint
          @keyup.enter="runSearch"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="searchDialog = false">取消</v-btn>
        <v-btn
          prepend-icon="mdi-server-network"
          variant="text"
          :disabled="!trimmedInput(searchText)"
          @click="openDirectSiteSearchConfirm"
        >
          搜索站点
        </v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-magnify"
          :disabled="!trimmedInput(searchText) && !trimmedInput(searchArtist)"
          :loading="searchLoading"
          @click="runSearch"
        >
          搜索
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
