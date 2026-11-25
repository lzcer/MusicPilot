<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  refreshData,
  dashboard,
  dashboardLoading,
  systemForm,
  dashboardMetricCards,
  loadDashboard,
  openSystemTasks,
  progressPercent,
  formatOptionalTime,
  downloadStatusText,
  downloadStatusColor,
  mediaStatusColor,
  mediaStatusText,
  mediaOperationTypeText,
  displayRelativePath
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <div class="toolbar-row">
      <v-btn
        prepend-icon="mdi-refresh"
        variant="tonal"
        :loading="dashboardLoading"
        @click="refreshData(loadDashboard)"
      >
        刷新
      </v-btn>
      <v-chip v-if="dashboard?.library.last_synced_at" color="primary" variant="tonal">
        曲库同步 {{ formatOptionalTime(dashboard.library.last_synced_at) }}
      </v-chip>
    </div>

    <div v-if="dashboardLoading && !dashboard" class="loading-panel">
      <v-progress-circular indeterminate color="primary" size="34" width="3" />
      <span>正在加载仪表盘</span>
    </div>

    <template v-else-if="dashboard">
      <div class="dashboard-metric-grid">
        <v-card
          v-for="metric in dashboardMetricCards"
          :key="metric.title"
          class="dashboard-metric-card"
        >
          <div class="dashboard-metric-icon" :class="`text-${metric.color}`">
            <v-icon :icon="metric.icon" size="30" />
          </div>
          <div>
            <div class="dashboard-metric-title">
              <span>{{ metric.title }}</span>
              <v-tooltip v-if="metric.help" location="top" max-width="320" open-on-click>
                <template #activator="{ props }">
                  <v-icon
                    v-bind="props"
                    class="dashboard-metric-help"
                    icon="mdi-information-outline"
                    size="16"
                    tabindex="0"
                  />
                </template>
                {{ metric.help }}
              </v-tooltip>
            </div>
            <div class="dashboard-metric-value">{{ metric.value }}</div>
            <div v-if="metric.subtitleLines?.length" class="dashboard-metric-subtitle">
              <div v-for="line in metric.subtitleLines" :key="line">{{ line }}</div>
            </div>
            <div v-else class="dashboard-metric-subtitle">{{ metric.subtitle }}</div>
          </div>
          <v-tooltip v-if="metric.error" location="top">
            <template #activator="{ props }">
              <v-icon
                v-bind="props"
                class="dashboard-metric-error"
                color="error"
                icon="mdi-alert-circle"
                size="18"
                tabindex="0"
              />
            </template>
            {{ metric.error }}
          </v-tooltip>
        </v-card>
      </div>

      <div class="dashboard-panel-grid">
        <v-card class="dashboard-panel">
          <v-card-title class="dashboard-panel-title">
            <span>最近下载</span>
            <v-chip size="small" color="warning" variant="tonal">
              活跃 {{ dashboard.downloads.active }}
            </v-chip>
          </v-card-title>
          <v-list density="compact" lines="two">
            <v-list-item
              v-for="item in dashboard.downloads.recent"
              :key="item.id || item.name"
              :title="item.name"
              :subtitle="formatOptionalTime(item.updated_at)"
            >
              <template #prepend>
                <v-progress-circular
                  :model-value="progressPercent(item.progress)"
                  color="primary"
                  size="36"
                  width="4"
                >
                  <span class="dashboard-progress-text">{{ progressPercent(item.progress) }}</span>
                </v-progress-circular>
              </template>
              <template #append>
                <v-chip :color="downloadStatusColor(item.state)" size="small" variant="tonal">
                  {{ downloadStatusText(item.state) }}
                </v-chip>
              </template>
            </v-list-item>
            <div v-if="!dashboard.downloads.recent.length" class="empty-cell">暂无下载任务</div>
          </v-list>
        </v-card>

        <v-card class="dashboard-panel">
          <v-card-title class="dashboard-panel-title">
            <span>最近整理</span>
          </v-card-title>
          <v-list density="compact" lines="two">
            <v-list-item
              v-for="item in dashboard.media.recent"
              :key="item.id"
              :title="
                item.title ||
                displayRelativePath(item.source_path, systemForm.scraping.source_directory)
              "
              :subtitle="`${item.artist || '-'} / ${formatOptionalTime(item.updated_at)}`"
            >
              <template #prepend>
                <v-icon icon="mdi-file-music-outline" size="28" />
              </template>
              <template #append>
                <div class="dashboard-chip-stack">
                  <v-chip size="small" variant="tonal">
                    {{ mediaOperationTypeText(item.operation_type) }}
                  </v-chip>
                  <v-chip :color="mediaStatusColor(item.status)" size="small" variant="tonal">
                    {{ mediaStatusText(item.status) }}
                  </v-chip>
                </div>
              </template>
            </v-list-item>
            <div v-if="!dashboard.media.recent.length" class="empty-cell">暂无整理记录</div>
          </v-list>
        </v-card>

        <v-card class="dashboard-panel">
          <v-card-title class="dashboard-panel-title">队列健康</v-card-title>
          <div class="dashboard-health-grid">
            <button class="dashboard-health-card" type="button" @click="openSystemTasks('RUNNING')">
              <div class="dashboard-health-value">{{ dashboard.tasks.running }}</div>
              <div class="dashboard-health-label">运行中</div>
            </button>
            <button class="dashboard-health-card" type="button" @click="openSystemTasks('WAIT')">
              <div class="dashboard-health-value">{{ dashboard.tasks.waiting }}</div>
              <div class="dashboard-health-label">等待中</div>
            </button>
            <button class="dashboard-health-card" type="button" @click="openSystemTasks('FAILED')">
              <div class="dashboard-health-value">{{ dashboard.tasks.failed }}</div>
              <div class="dashboard-health-label">失败</div>
            </button>
            <button class="dashboard-health-card" type="button" @click="openSystemTasks('SLOW')">
              <div class="dashboard-health-value">{{ dashboard.tasks.slow }}</div>
              <div class="dashboard-health-label">耗时异常</div>
            </button>
          </div>
          <div class="dashboard-status-row">
            <v-chip color="success" variant="tonal">
              已在库 {{ dashboard.playlists.existing_tracks }}
            </v-chip>
            <v-chip color="error" variant="tonal">
              歌单失败 {{ dashboard.playlists.failed_tracks }}
            </v-chip>
            <v-chip color="warning" variant="tonal">
              下载失败 {{ dashboard.downloads.failed }}
            </v-chip>
            <v-chip color="info" variant="tonal">
              近 7 天整理 {{ dashboard.media.recent_7d }}
            </v-chip>
          </div>
        </v-card>
      </div>
    </template>
  </section>
</template>
