<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { noMetadataDialog, runDirectSearch } = useWorkspace()
</script>

<template>
  <v-dialog v-model="noMetadataDialog" max-width="460">
    <v-card title="未找到媒体信息">
      <v-card-text>未找到媒体信息，是否直接使用站点搜索？</v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="noMetadataDialog = false">取消</v-btn>
        <v-btn color="primary" @click="runDirectSearch">直接搜索</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
