<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  systemSaving,
  directoryMonitorStatus,
  directoryMonitorDialog,
  directoryMonitorDialogContext,
  directoryMonitorDialogMessage,
  directoryMonitorPollingAvailable,
  directoryMonitorActionLoading,
  systemForm,
  retryNativeDirectoryMonitor,
  useDirectoryMonitorPolling,
  switchToDownloaderMonitor
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="directoryMonitorDialog" max-width="620">
    <v-card
      :title="directoryMonitorDialogContext === 'save' ? '原生目录监听不可用' : '目录监听已停止'"
    >
      <v-card-text class="dialog-stack">
        <v-alert type="error" variant="tonal">
          {{ directoryMonitorDialogMessage }}
        </v-alert>
        <div>
          <strong>源目录：</strong>
          {{
            directoryMonitorDialogContext === 'save'
              ? systemForm.scraping.source_directory || '-'
              : directoryMonitorStatus.source_directory || '-'
          }}
        </div>
        <div v-if="directoryMonitorDialogContext === 'failure'">
          <strong>失败时间：</strong>{{ directoryMonitorStatus.failed_at || '-' }}
        </div>
        <v-alert v-if="directoryMonitorPollingAvailable" type="warning" variant="tonal">
          轮询会定期递归检查整个源目录。文件越多、间隔越短，CPU、磁盘和 NAS 网络 I/O
          越高；新增文件最多延迟一个轮询周期后才会进入稳定检查。
        </v-alert>
        <v-text-field
          v-if="directoryMonitorPollingAvailable"
          v-model.number="systemForm.scraping.directory_monitor_poll_interval_seconds"
          label="轮询间隔（秒）"
          type="number"
          min="30"
          hint="最短 30 秒，默认 60 秒。"
          persistent-hint
        />
      </v-card-text>
      <v-card-actions class="flex-wrap">
        <v-btn variant="text" @click="directoryMonitorDialog = false">取消</v-btn>
        <v-spacer />
        <v-btn
          :disabled="directoryMonitorActionLoading || systemSaving"
          variant="tonal"
          @click="switchToDownloaderMonitor"
        >
          切换到下载器监听
        </v-btn>
        <v-btn
          :loading="directoryMonitorActionLoading"
          variant="tonal"
          @click="retryNativeDirectoryMonitor"
        >
          重新检测原生监听
        </v-btn>
        <v-btn
          v-if="directoryMonitorPollingAvailable"
          color="warning"
          :loading="systemSaving"
          @click="useDirectoryMonitorPolling"
        >
          改用轮询监听
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
