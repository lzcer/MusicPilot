<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { artistBuilding, clearArtistDialog, confirmClearAndRebuildArtistLibrary } = useWorkspace()
</script>

<template>
  <v-dialog v-model="clearArtistDialog" max-width="420">
    <v-card title="清空并重建">
      <v-card-text> 确定清空并重建歌手库吗？所有手动添加的别名和合并操作会丢失。 </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="clearArtistDialog = false">取消</v-btn>
        <v-btn
          color="warning"
          :loading="artistBuilding"
          @click="confirmClearAndRebuildArtistLibrary"
        >
          确定
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
