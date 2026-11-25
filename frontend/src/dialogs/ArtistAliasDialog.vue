<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { artistAliasDialog, artistAliasForm, saveArtistAlias } = useWorkspace()
</script>

<template>
  <v-dialog v-model="artistAliasDialog" max-width="460">
    <v-card title="添加别名">
      <v-card-text class="dialog-stack">
        <v-text-field
          v-model="artistAliasForm.alias"
          label="别名"
          placeholder="例如：Jay Chou / G.E.M."
          autofocus
          @keyup.enter="saveArtistAlias"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="artistAliasDialog = false">取消</v-btn>
        <v-btn color="primary" :disabled="!artistAliasForm.alias.trim()" @click="saveArtistAlias">
          保存
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
