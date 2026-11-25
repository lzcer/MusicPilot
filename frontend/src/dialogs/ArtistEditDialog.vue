<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { artistEditDialog, artistEditSaving, artistEditForm, saveArtistEdit } = useWorkspace()
</script>

<template>
  <v-dialog v-model="artistEditDialog" max-width="560">
    <v-card title="编辑歌手">
      <v-card-text class="dialog-stack">
        <v-text-field
          v-model="artistEditForm.name"
          label="歌手名（权威名）"
          autofocus
          @keyup.enter="saveArtistEdit"
        />
        <v-textarea
          v-model="artistEditForm.aliases"
          auto-grow
          label="别名"
          placeholder="一行一个别名"
          rows="6"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="artistEditSaving" @click="artistEditDialog = false">
          取消
        </v-btn>
        <v-btn
          color="primary"
          :disabled="!artistEditForm.name.trim()"
          :loading="artistEditSaving"
          @click="saveArtistEdit"
        >
          保存
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
