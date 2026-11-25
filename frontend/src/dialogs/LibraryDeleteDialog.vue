<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { libraryDeleteTrack, libraryDeleteDialog, libraryDeleting, deleteLibraryTrack } =
  useWorkspace()
</script>

<template>
  <v-dialog v-model="libraryDeleteDialog" :persistent="libraryDeleting" max-width="480">
    <v-card title="删除音乐库歌曲">
      <v-card-text>
        <p>将永久删除音乐库中《{{ libraryDeleteTrack?.title }}》的文件。</p>
        <p class="mt-2">歌单里的曲目会保留。此操作不可恢复。</p>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="libraryDeleting" @click="libraryDeleteDialog = false"
          >取消</v-btn
        >
        <v-btn color="error" :loading="libraryDeleting" @click="deleteLibraryTrack">删除</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
