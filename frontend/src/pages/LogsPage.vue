<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  refreshData,
  LOG_LEVEL_OPTIONS,
  logsLoading,
  logPaused,
  logLevel,
  logQuery,
  debugLoggingEnabled,
  debugLoggingLoading,
  filteredLogs,
  loadLogs,
  setDebugLoggingEnabled,
  formatTime,
  logColor
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <v-card>
      <v-card-text class="log-toolbar">
        <v-select
          v-model="logLevel"
          :items="LOG_LEVEL_OPTIONS"
          label="最低级别"
          hide-details
          class="log-level"
        />
        <v-switch
          :model-value="debugLoggingEnabled"
          :loading="debugLoggingLoading"
          :disabled="debugLoggingLoading"
          color="primary"
          density="compact"
          hide-details
          inset
          label="记录 DEBUG"
          class="log-debug-switch"
          @update:model-value="setDebugLoggingEnabled"
        />
        <v-text-field
          v-model="logQuery"
          label="搜索日志"
          prepend-inner-icon="mdi-magnify"
          hide-details
        />
        <v-btn
          :prepend-icon="logPaused ? 'mdi-play' : 'mdi-pause'"
          variant="tonal"
          @click="logPaused = !logPaused"
        >
          {{ logPaused ? '继续' : '暂停' }}
        </v-btn>
        <v-btn
          prepend-icon="mdi-refresh"
          :loading="logsLoading"
          variant="tonal"
          @click="refreshData(loadLogs)"
        >
          刷新
        </v-btn>
      </v-card-text>
      <div class="log-list">
        <div v-if="!filteredLogs.length" class="empty-cell">暂无日志</div>
        <div
          v-for="entry in filteredLogs"
          :key="`${entry.timestamp}-${entry.message}`"
          class="log-line"
        >
          <span class="log-time">{{ formatTime(entry.timestamp) }}</span>
          <v-chip :color="logColor(entry.level)" size="x-small" variant="tonal">{{
            entry.level
          }}</v-chip>
          <span class="log-category">{{ entry.category }}</span>
          <span class="log-message">{{ entry.message }}</span>
        </div>
      </div>
    </v-card>
  </section>
</template>
