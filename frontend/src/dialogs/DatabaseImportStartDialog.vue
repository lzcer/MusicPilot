<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { databaseImportStartDialog, confirmDatabaseImportStart } = useWorkspace()
</script>

<template>
  <v-dialog v-model="databaseImportStartDialog" max-width="460">
    <v-card title="确认导入数据库">
      <v-card-text> 导入数据库将会清空本地数据，并使用目标数据，是否确认操作？ </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="databaseImportStartDialog = false">取消</v-btn>
        <v-btn color="warning" @click="confirmDatabaseImportStart">确认</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
