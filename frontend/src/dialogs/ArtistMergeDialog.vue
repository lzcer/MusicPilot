<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { artists, artistMergeDialog, artistMergeForm, confirmMergeArtists } = useWorkspace()
</script>

<template>
  <v-dialog v-model="artistMergeDialog" max-width="480">
    <v-card title="合并歌手">
      <v-card-text class="dialog-stack">
        <p class="mb-2">
          将另一个歌手合并到
          <strong>{{ artistMergeForm.target_name }}</strong> 中。
          被合并歌手的全部别名会转移到目标歌手，被合并歌手删除。
        </p>
        <v-select
          v-model.number="artistMergeForm.source_id"
          :items="
            artists
              .filter((a) => a.id !== artistMergeForm.target_id)
              .map((a) => ({
                title: `${a.name} (${a.aliases.length} 个别名)`,
                value: a.id
              }))
          "
          label="被合并的歌手"
          item-title="title"
          item-value="value"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="artistMergeDialog = false">取消</v-btn>
        <v-btn color="warning" :disabled="!artistMergeForm.source_id" @click="confirmMergeArtists">
          合并
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
