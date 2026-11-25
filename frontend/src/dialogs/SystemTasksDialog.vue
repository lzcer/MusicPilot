<script setup lang="ts">
import { useWorkspace } from '../workspace'
import ScrollableTable from '../components/ScrollableTable.vue'
import TruncatedTableCell from '../components/TruncatedTableCell.vue'

const {
  systemTasksDialog,
  systemTaskStatus,
  systemTasks,
  selectedSystemTaskIds,
  systemTasksLoading,
  systemTasksInterrupting,
  interruptibleSystemTaskIds,
  allSystemTasksSelected,
  someSystemTasksSelected,
  systemTasksDialogTitle,
  systemTaskInterruptButtonText,
  loadSystemTasks,
  canInterruptSystemTask,
  interruptSystemTask,
  interruptSelectedSystemTasks,
  formatOptionalTime,
  systemTaskElapsedText,
  systemTaskStatusText,
  systemTaskStatusColor,
  systemTaskTypeText
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="systemTasksDialog" max-width="1120">
    <v-card :title="systemTasksDialogTitle">
      <v-card-text>
        <div class="toolbar-row mb-4">
          <v-btn
            prepend-icon="mdi-refresh"
            variant="tonal"
            :loading="systemTasksLoading"
            @click="loadSystemTasks"
          >
            刷新
          </v-btn>
          <v-btn
            prepend-icon="mdi-stop-circle-outline"
            color="warning"
            variant="tonal"
            :disabled="!selectedSystemTaskIds.length || systemTasksInterrupting"
            :loading="systemTasksInterrupting"
            @click="interruptSelectedSystemTasks"
          >
            {{ systemTaskInterruptButtonText }}
          </v-btn>
        </div>
        <v-progress-linear v-if="systemTasksLoading" indeterminate class="mb-4" />
        <ScrollableTable class="fixed-table system-task-table" :min-width="1240">
          <thead>
            <tr>
              <th class="select-cell">
                <v-checkbox
                  v-model="allSystemTasksSelected"
                  :disabled="!interruptibleSystemTaskIds.length"
                  :indeterminate="someSystemTasksSelected"
                  density="compact"
                  hide-details
                />
              </th>
              <th class="system-task-id-col">ID</th>
              <th class="system-task-type-col">类型</th>
              <th class="system-task-status-col">状态</th>
              <th class="system-task-attempts-col">尝试</th>
              <th class="system-task-elapsed-col">耗时</th>
              <th class="system-task-time-col">可执行时间</th>
              <th class="system-task-time-col">创建时间</th>
              <th class="system-task-error-col">错误</th>
              <th class="system-task-action-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!systemTasks.length">
              <td colspan="10" class="empty-cell">暂无队列任务</td>
            </tr>
            <tr v-for="task in systemTasks" :key="task.id">
              <td class="select-cell">
                <v-checkbox
                  v-if="canInterruptSystemTask(task)"
                  v-model="selectedSystemTaskIds"
                  :value="task.id"
                  density="compact"
                  hide-details
                />
              </td>
              <td>{{ task.id }}</td>
              <td>
                <TruncatedTableCell :value="systemTaskTypeText(task.task_type)" />
              </td>
              <td>
                <v-chip :color="systemTaskStatusColor(task.status)" size="small" variant="tonal">
                  {{ systemTaskStatusText(task.status) }}
                </v-chip>
              </td>
              <td>{{ task.attempts }} / {{ task.max_attempts }}</td>
              <td>{{ systemTaskElapsedText(task) }}</td>
              <td>
                <TruncatedTableCell :value="formatOptionalTime(task.available_at)" />
              </td>
              <td>
                <TruncatedTableCell :value="formatOptionalTime(task.created_at)" />
              </td>
              <td>
                <TruncatedTableCell :value="task.error_message || '-'" />
              </td>
              <td class="table-actions">
                <v-btn
                  icon="mdi-stop-circle-outline"
                  color="warning"
                  variant="text"
                  size="small"
                  :title="systemTaskStatus === 'SLOW' ? '强制中止任务' : '中断任务'"
                  :disabled="!canInterruptSystemTask(task) || systemTasksInterrupting"
                  @click="interruptSystemTask(task)"
                />
              </td>
            </tr>
          </tbody>
        </ScrollableTable>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="systemTasksDialog = false">关闭</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
