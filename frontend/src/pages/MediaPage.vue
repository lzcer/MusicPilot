<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  refreshData,
  mediaFiles,
  mediaQuery,
  mediaPage,
  mediaPageSize,
  mediaTotal,
  selectedMediaIds,
  mediaStatusFilter,
  mediaRetrying,
  mediaManualSubmitting,
  mediaTableHeaders,
  mediaClearDialog,
  mediaClearing,
  mediaPageLength,
  allMediaSelected,
  someMediaSelected,
  mediaStatusFilterOptions,
  loadMedia,
  applyMediaFilters,
  deleteMediaFile,
  deleteSelectedMediaFiles,
  retrySingleMedia,
  openManualOrganize,
  retrySelectedMedia,
  formatTime,
  mediaStatusColor,
  mediaStatusText,
  mediaOperationTypeText,
  mediaOperationReason,
  mediaRemark,
  mediaTableRow,
  mediaDisplayPath
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <div class="toolbar-row">
      <v-btn prepend-icon="mdi-refresh" variant="tonal" @click="refreshData(loadMedia)">刷新</v-btn>
      <v-btn
        prepend-icon="mdi-refresh"
        variant="tonal"
        :disabled="!selectedMediaIds.length || mediaRetrying"
        :loading="mediaRetrying"
        @click="retrySelectedMedia"
      >
        重试
      </v-btn>
      <v-btn
        prepend-icon="mdi-delete"
        color="error"
        variant="tonal"
        :disabled="!selectedMediaIds.length"
        @click="deleteSelectedMediaFiles"
      >
        删除
      </v-btn>
      <v-btn
        prepend-icon="mdi-delete-sweep"
        color="error"
        variant="tonal"
        :disabled="mediaClearing"
        :loading="mediaClearing"
        @click="mediaClearDialog = true"
      >
        清空记录
      </v-btn>
      <v-text-field
        v-model="mediaQuery"
        label="搜索整理记录"
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        class="table-search"
        @keyup.enter="applyMediaFilters"
        @click:clear="applyMediaFilters"
      />
      <v-btn prepend-icon="mdi-magnify" variant="tonal" @click="applyMediaFilters"> 搜索 </v-btn>
      <v-select
        v-model="mediaStatusFilter"
        :items="mediaStatusFilterOptions"
        item-title="title"
        item-value="value"
        label="状态筛选"
        hide-details
        density="compact"
        class="status-filter-select"
        clearable
        @update:model-value="applyMediaFilters"
      />
    </div>
    <v-card>
      <v-data-table
        :headers="mediaTableHeaders"
        :items="mediaFiles"
        :items-per-page="-1"
        class="media-table"
        density="comfortable"
        hide-default-footer
        item-value="id"
      >
        <template #header.select>
          <v-checkbox
            v-model="allMediaSelected"
            :indeterminate="someMediaSelected"
            density="compact"
            hide-details
          />
        </template>
        <template #item.select="{ item }">
          <v-checkbox
            v-model="selectedMediaIds"
            :value="mediaTableRow(item).id"
            density="compact"
            hide-details
          />
        </template>
        <template #item.title="{ item }">
          <v-tooltip location="top" max-width="420">
            <template #activator="{ props }">
              <span v-bind="props" class="media-single-line-text">
                {{ mediaTableRow(item).title || '-' }}
              </span>
            </template>
            <span class="media-tooltip-text">{{ mediaTableRow(item).title || '-' }}</span>
          </v-tooltip>
        </template>
        <template #item.artist="{ item }">
          <v-tooltip location="top" max-width="420">
            <template #activator="{ props }">
              <span v-bind="props" class="media-single-line-text">
                {{ mediaTableRow(item).artist || '-' }}
              </span>
            </template>
            <span class="media-tooltip-text">{{ mediaTableRow(item).artist || '-' }}</span>
          </v-tooltip>
        </template>
        <template #item.album="{ item }">
          <v-tooltip location="top" max-width="420">
            <template #activator="{ props }">
              <span v-bind="props" class="media-single-line-text">
                {{ mediaTableRow(item).album || '-' }}
              </span>
            </template>
            <span class="media-tooltip-text">{{ mediaTableRow(item).album || '-' }}</span>
          </v-tooltip>
        </template>
        <template #item.operation_time="{ item }">
          {{ formatTime(mediaTableRow(item).operation_time) }}
        </template>
        <template #item.operation_type="{ item }">
          <v-tooltip location="top" max-width="420">
            <template #activator="{ props }">
              <v-chip v-bind="props" size="small" variant="tonal">
                {{ mediaOperationTypeText(mediaTableRow(item).operation_type) }}
              </v-chip>
            </template>
            <span class="media-tooltip-text">
              {{ mediaOperationReason(mediaTableRow(item)) }}
            </span>
          </v-tooltip>
        </template>
        <template #item.status="{ item }">
          <v-chip
            :color="mediaStatusColor(mediaTableRow(item).status)"
            size="small"
            variant="tonal"
          >
            {{ mediaStatusText(mediaTableRow(item).status) }}
          </v-chip>
        </template>
        <template #item.path="{ item }">
          <div class="media-cell-clip media-path-clip">
            <v-tooltip location="top" max-width="640">
              <template #activator="{ props }">
                <span v-bind="props" class="media-path-text">
                  {{ mediaDisplayPath(mediaTableRow(item)) }}
                </span>
              </template>
              <span class="media-tooltip-text">{{ mediaDisplayPath(mediaTableRow(item)) }}</span>
            </v-tooltip>
          </div>
        </template>
        <template #item.remark="{ item }">
          <div class="media-cell-clip media-remark-clip">
            <v-tooltip location="top" max-width="420">
              <template #activator="{ props }">
                <span v-bind="props" class="media-remark-text">
                  {{ mediaRemark(mediaTableRow(item)) }}
                </span>
              </template>
              <span class="media-tooltip-text">{{ mediaRemark(mediaTableRow(item)) }}</span>
            </v-tooltip>
          </div>
        </template>
        <template #item.actions="{ item }">
          <div class="media-actions">
            <v-btn
              icon="mdi-pencil-box-outline"
              color="primary"
              variant="text"
              size="small"
              title="手动整理"
              :disabled="mediaManualSubmitting"
              @click="openManualOrganize(mediaTableRow(item))"
            />
            <v-btn
              icon="mdi-refresh"
              color="primary"
              variant="text"
              size="small"
              title="重试"
              :disabled="mediaRetrying"
              @click="retrySingleMedia(mediaTableRow(item))"
            />
            <v-btn
              icon="mdi-delete"
              color="error"
              variant="text"
              size="small"
              title="删除整理记录"
              @click="deleteMediaFile(mediaTableRow(item))"
            />
          </div>
        </template>
        <template #no-data>
          <div class="empty-cell">暂无整理记录</div>
        </template>
        <template #bottom></template>
      </v-data-table>
      <div class="pagination-row">
        <v-select
          v-model="mediaPageSize"
          :items="[20, 50, 100]"
          label="每页"
          density="compact"
          hide-details
          class="page-size-select"
          @update:model-value="applyMediaFilters"
        />
        <v-pagination
          v-model="mediaPage"
          :length="mediaPageLength"
          density="comfortable"
          total-visible="7"
          @update:model-value="loadMedia"
        />
        <v-chip color="secondary" variant="tonal">共 {{ mediaTotal }} 条</v-chip>
      </div>
    </v-card>
  </section>
</template>
