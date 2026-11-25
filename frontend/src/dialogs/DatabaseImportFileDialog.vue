<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  databaseImporting,
  databaseImportFileDialog,
  databaseImportSecondConfirm,
  databaseImportDragging,
  databaseImportFileInput,
  selectedDatabaseImportFile,
  openDatabaseImportFilePicker,
  handleDatabaseImportFileChange,
  handleDatabaseImportDrop,
  closeDatabaseImportFileDialog,
  confirmDatabaseImport
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="databaseImportFileDialog" max-width="560">
    <v-card title="导入数据库">
      <v-card-text class="dialog-stack">
        <input
          ref="databaseImportFileInput"
          accept=".zip,application/zip"
          class="hidden-file-input"
          type="file"
          @change="handleDatabaseImportFileChange"
        />
        <button
          class="database-import-dropzone"
          :class="{ 'database-import-dropzone-active': databaseImportDragging }"
          type="button"
          @click="openDatabaseImportFilePicker"
          @dragenter.prevent="databaseImportDragging = true"
          @dragover.prevent="databaseImportDragging = true"
          @dragleave.prevent="databaseImportDragging = false"
          @drop.prevent="handleDatabaseImportDrop"
        >
          <v-icon icon="mdi-file-upload-outline" size="36" />
          <span>{{ selectedDatabaseImportFile()?.name || '拖放数据库导出包到这里' }}</span>
          <small>点击选择 zip 文件</small>
        </button>
        <div v-if="databaseImportSecondConfirm" class="database-import-warning">
          导入数据库将会清空本地数据，并使用目标数据，是否确认操作？
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" :disabled="databaseImporting" @click="closeDatabaseImportFileDialog">
          取消
        </v-btn>
        <v-btn
          color="warning"
          :disabled="!selectedDatabaseImportFile()"
          :loading="databaseImporting"
          @click="confirmDatabaseImport"
        >
          {{ databaseImportSecondConfirm ? '确认导入' : '确认' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
