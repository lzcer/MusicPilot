<script setup lang="ts">
import { useWorkspace } from '../workspace'
import DirectoryPickerField from '../components/DirectoryPickerField.vue'

const {
  settingsLoading,
  settingsErrors,
  loadSettingsTab,
  settingsTab,
  downloaders,
  notifiers,
  mediaServerTesting,
  systemSaving,
  directoryMonitorActionLoading,
  aboutInfo,
  databaseExporting,
  databaseImporting,
  activeConfigMenu,
  mediaServerForm,
  systemForm,
  scrapingModeOptions,
  autoOrganizeOptions,
  autoOrganizeDescription,
  directoryMonitorFailed,
  scrapingModeDescription,
  scrapingRequiredMetadataOptions,
  scrapingClassifyOptions,
  duplicateHandlingOptions,
  mediaServerUserAccounts,
  updateMediaServerPassword,
  openNewDownloaderDialog,
  editDownloader,
  openDeleteDownloader,
  openNewMediaServerUserDialog,
  editMediaServerUser,
  testMediaServer,
  saveMediaServer,
  openDeleteMediaServer,
  openNewNotifierDialog,
  editNotifier,
  openDeleteNotifier,
  configMenuKey,
  toggleConfigMenu,
  openDirectoryMonitorFailureDialog,
  updateAutoOrganize,
  saveSystemSettings,
  retryNativeDirectoryMonitor,
  exportDatabase,
  openDatabaseImportStartDialog
} = useWorkspace()

async function retrySettings() {
  try {
    await loadSettingsTab(settingsTab.value)
  } catch {
    // The current tab displays the load error and retry action.
  }
}
</script>

<template>
  <section class="page-stack">
    <v-tabs v-model="settingsTab" color="primary">
      <v-tab value="downloaders">下载器</v-tab>
      <v-tab value="mediaServers">音乐库</v-tab>
      <v-tab value="notifiers">通知</v-tab>
      <v-tab value="system">系统设置</v-tab>
      <v-tab value="about">关于</v-tab>
    </v-tabs>

    <v-skeleton-loader v-if="settingsLoading" type="article" />
    <v-alert v-else-if="settingsErrors[settingsTab]" type="error" variant="tonal">
      设置加载失败：{{ settingsErrors[settingsTab] }}
      <v-btn variant="text" @click="retrySettings">重新加载</v-btn>
    </v-alert>
    <v-window v-else v-model="settingsTab" class="settings-window">
      <v-window-item value="downloaders">
        <div class="toolbar-row">
          <v-btn color="primary" prepend-icon="mdi-plus" @click="openNewDownloaderDialog"
            >新增下载器</v-btn
          >
        </div>
        <div class="card-grid">
          <v-card
            v-for="downloader in downloaders"
            :key="downloader.id || downloader.base_url"
            class="config-card"
            @click="editDownloader(downloader)"
          >
            <v-card-title class="config-card-title d-flex align-center">
              <span>{{ downloader.name }}</span>
              <v-spacer />
              <div v-if="downloader.id" class="config-card-menu" @click.stop>
                <v-btn
                  icon="mdi-dots-vertical"
                  size="small"
                  variant="text"
                  @click.stop="toggleConfigMenu('downloader', downloader.id)"
                />
                <v-card
                  v-if="activeConfigMenu === configMenuKey('downloader', downloader.id)"
                  class="config-card-menu-panel"
                  elevation="0"
                  @click.stop
                >
                  <button
                    class="config-card-menu-item"
                    type="button"
                    @click="openDeleteDownloader(downloader)"
                  >
                    删除
                  </button>
                </v-card>
              </div>
            </v-card-title>
            <v-card-text>
              <div class="muted">{{ downloader.base_url }}</div>
              <div class="muted">{{ downloader.download_path || '未设置下载目录' }}</div>
              <div class="muted">{{ downloader.local_path || '未设置本机对应目录' }}</div>
              <v-chip v-if="downloader.is_default" color="success" size="small" variant="tonal"
                >默认</v-chip
              >
              <v-chip v-if="!downloader.enabled" color="warning" size="small" variant="tonal"
                >停用</v-chip
              >
            </v-card-text>
          </v-card>
        </div>
      </v-window-item>

      <v-window-item value="mediaServers">
        <v-card class="settings-card">
          <v-card-title>音乐库配置</v-card-title>
          <v-card-text class="settings-grid">
            <v-select v-model="mediaServerForm.type" :items="['navidrome']" label="类型" />
            <v-text-field v-model="mediaServerForm.name" label="名称" />
            <v-text-field v-model="mediaServerForm.base_url" label="地址" />
            <v-text-field v-model="mediaServerForm.api_key" label="API Token" />
            <v-text-field v-model="mediaServerForm.username" label="默认用户名" />
            <v-text-field
              :model-value="mediaServerForm.password"
              label="默认用户密码"
              type="password"
              :placeholder="mediaServerForm.id ? '留空则保持原密码' : ''"
              @update:model-value="updateMediaServerPassword"
            />
            <v-switch
              v-model="mediaServerForm.enabled"
              class="compact-switch"
              color="primary"
              density="compact"
              hide-details
              inset
              label="启用"
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn :loading="mediaServerTesting" variant="tonal" @click="testMediaServer">
              测试
            </v-btn>
            <v-btn color="primary" @click="saveMediaServer"> 保存 </v-btn>
          </v-card-actions>
        </v-card>

        <v-card class="settings-card mt-4">
          <v-card-title class="d-flex align-center">
            <span>用户账号</span>
            <v-spacer />
            <v-btn
              color="primary"
              prepend-icon="mdi-account-plus"
              variant="tonal"
              @click="openNewMediaServerUserDialog"
            >
              新增用户
            </v-btn>
          </v-card-title>
          <v-table>
            <thead>
              <tr>
                <th>用户名</th>
                <th>状态</th>
                <th>类型</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!mediaServerUserAccounts.length">
                <td colspan="4" class="empty-cell">保存音乐库配置后会生成默认用户</td>
              </tr>
              <tr v-for="server in mediaServerUserAccounts" :key="server.id || server.username">
                <td>
                  <div class="font-weight-medium">{{ server.username || '-' }}</div>
                  <div class="muted">{{ server.is_default ? '默认账号' : server.name }}</div>
                </td>
                <td>
                  <v-chip
                    :color="server.enabled ? 'success' : 'warning'"
                    size="small"
                    variant="tonal"
                  >
                    {{ server.enabled ? '启用' : '停用' }}
                  </v-chip>
                </td>
                <td>{{ server.type }}</td>
                <td class="table-actions">
                  <v-btn
                    icon="mdi-pencil-outline"
                    color="primary"
                    variant="text"
                    size="small"
                    :title="server.is_default ? '默认账号请在上方编辑' : '编辑用户'"
                    :disabled="server.is_default"
                    @click="editMediaServerUser(server)"
                  />
                  <v-btn
                    icon="mdi-delete-outline"
                    color="error"
                    variant="text"
                    size="small"
                    title="删除用户"
                    :disabled="server.is_default"
                    @click="openDeleteMediaServer(server)"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card>
      </v-window-item>

      <v-window-item value="notifiers">
        <div class="toolbar-row">
          <v-btn color="primary" prepend-icon="mdi-plus" @click="openNewNotifierDialog"
            >新增通知</v-btn
          >
        </div>
        <div class="card-grid">
          <v-card
            v-for="notifier in notifiers"
            :key="notifier.id || notifier.name"
            class="config-card"
            @click="editNotifier(notifier)"
          >
            <v-card-title class="config-card-title d-flex align-center">
              <span>{{ notifier.name }}</span>
              <v-spacer />
              <div v-if="notifier.id" class="config-card-menu" @click.stop>
                <v-btn
                  icon="mdi-dots-vertical"
                  size="small"
                  variant="text"
                  @click.stop="toggleConfigMenu('notifier', notifier.id)"
                />
                <v-card
                  v-if="activeConfigMenu === configMenuKey('notifier', notifier.id)"
                  class="config-card-menu-panel"
                  elevation="0"
                  @click.stop
                >
                  <button
                    class="config-card-menu-item"
                    type="button"
                    @click="openDeleteNotifier(notifier)"
                  >
                    删除
                  </button>
                </v-card>
              </div>
            </v-card-title>
            <v-card-text>
              <v-chip size="small" variant="tonal">{{ notifier.type }}</v-chip>
              <v-chip v-if="notifier.use_proxy" color="warning" size="small" variant="tonal"
                >代理</v-chip
              >
              <v-chip v-if="!notifier.enabled" color="warning" size="small" variant="tonal"
                >停用</v-chip
              >
              <div class="muted">{{ notifier.chat_ids || '未指定会话' }}</div>
            </v-card-text>
          </v-card>
        </div>
      </v-window-item>

      <v-window-item value="system">
        <v-card class="settings-card">
          <v-card-title>网络设置</v-card-title>
          <v-card-text class="settings-grid">
            <v-text-field
              v-model="systemForm.proxy.host"
              label="代理地址"
              placeholder="127.0.0.1 或 http://127.0.0.1:7890"
            />
            <v-text-field v-model.number="systemForm.proxy.port" label="端口" type="number" />
            <v-text-field v-model="systemForm.proxy.username" label="用户名" />
            <v-text-field v-model="systemForm.proxy.password" label="密码" type="password" />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn color="primary" :loading="systemSaving" @click="saveSystemSettings">
              保存网络设置
            </v-btn>
          </v-card-actions>
        </v-card>

        <v-card class="settings-card mt-4">
          <v-card-title>刮削设置</v-card-title>
          <v-card-text>
            <div class="settings-grid">
              <v-switch
                v-model="systemForm.scraping.enabled"
                class="compact-switch"
                color="primary"
                density="compact"
                hide-details
                inset
                label="开启刮削"
              />
              <div class="scraping-mode-field">
                <v-select
                  v-model="systemForm.scraping.mode"
                  :items="scrapingModeOptions"
                  label="刮削类型"
                />
                <div class="scraping-mode-description" aria-live="polite">
                  {{ scrapingModeDescription }}
                </div>
              </div>
              <DirectoryPickerField
                v-model="systemForm.scraping.source_directory"
                label="源文件目录"
              />
              <DirectoryPickerField
                v-if="systemForm.scraping.mode !== 'source'"
                v-model="systemForm.scraping.mapped_directory"
                :label="systemForm.scraping.mode === 'copy' ? '复制目录' : '映射目录'"
              />
            </div>

            <div class="settings-checks">
              <div class="settings-checks-label">
                <span>缺失时尝试刮削</span>
                <v-tooltip location="top" max-width="520" open-on-click>
                  <template #activator="{ props }">
                    <v-icon
                      v-bind="props"
                      class="settings-help-icon"
                      icon="mdi-information-outline"
                      size="17"
                      tabindex="0"
                      aria-label="缺失时尝试刮削说明"
                    />
                  </template>
                  <div class="settings-help-tip">
                    <div class="settings-help-tip-summary">
                      源文件缺少勾选的字段时，会尝试搜索并补齐。只在这里勾选的字段，即使没补到，也不会仅因此判定失败。
                    </div>
                    <div>
                      <strong>最大尝试：</strong
                      >开启后，当一个源刮削失败时，会尝试其他源继续刮削，直到刮削成功或所有源均已尝试。开启后会降低整体刮削速度。
                    </div>
                  </div>
                </v-tooltip>
              </div>
              <div class="settings-checks-row">
                <v-checkbox
                  v-for="item in scrapingRequiredMetadataOptions"
                  :key="item.value"
                  v-model="systemForm.scraping.scrape_when_missing"
                  :label="item.title"
                  :value="item.value"
                  hide-details
                />
                <v-switch
                  v-model="systemForm.scraping.max_scrape_attempt"
                  class="compact-switch"
                  color="primary"
                  density="compact"
                  hide-details
                  inset
                  label="最大尝试"
                />
              </div>
            </div>

            <div class="settings-checks">
              <div class="settings-checks-label">
                <span>缺失则判定失败</span>
                <v-tooltip location="top" max-width="520" open-on-click>
                  <template #activator="{ props }">
                    <v-icon
                      v-bind="props"
                      class="settings-help-icon"
                      icon="mdi-information-outline"
                      size="17"
                      tabindex="0"
                      aria-label="缺失则判定失败说明"
                    />
                  </template>
                  <div class="settings-help-tip">
                    勾选的字段是必填项。缺失时也会尝试补齐，无需在上面重复勾选；刮削结束后仍缺少任一必填字段，本次判定失败。「最大尝试」不会放宽这个要求。
                  </div>
                </v-tooltip>
              </div>
              <div class="settings-checks-row">
                <v-checkbox
                  v-for="item in scrapingRequiredMetadataOptions"
                  :key="item.value"
                  v-model="systemForm.scraping.required_metadata"
                  :label="item.title"
                  :value="item.value"
                  hide-details
                />
              </div>
            </div>

            <div class="settings-grid">
              <v-switch
                v-model="systemForm.scraping.auto_rename"
                class="compact-switch"
                color="primary"
                density="compact"
                hide-details
                inset
                label="自动重命名"
              />
              <v-switch
                v-model="systemForm.scraping.auto_classify"
                class="compact-switch"
                color="primary"
                density="compact"
                hide-details
                inset
                label="自动分类"
              />
              <div class="track-version-control-setting">
                <v-switch
                  v-model="systemForm.scraping.track_version_control"
                  class="compact-switch"
                  color="primary"
                  density="compact"
                  hide-details
                  inset
                  label="歌曲版本控制"
                />
                <v-tooltip location="top" max-width="520" open-on-click>
                  <template #activator="{ props }">
                    <v-icon
                      v-bind="props"
                      class="settings-help-icon"
                      icon="mdi-information-outline"
                      size="17"
                      tabindex="0"
                    />
                  </template>
                  <div class="settings-help-tip">
                    <div class="settings-help-tip-summary">
                      控制刮削、重复文件和“已在库”判断是否严格区分歌曲版本（如 live、demo、feat）。
                    </div>
                    <div class="track-version-control-tip-options">
                      <div class="track-version-control-tip-row">
                        <strong>开启时</strong>
                        <span
                          >版本不匹配会判定为刮削失败；重复文件和“已在库”状态判断也会严格区分版本。</span
                        >
                      </div>
                      <div class="track-version-control-tip-row">
                        <strong>关闭时</strong>
                        <span
                          >版本数据仅参与候选评分，优先选择正确版本；没有对应版本时，会选择其他匹配度较高的版本。</span
                        >
                      </div>
                    </div>
                  </div>
                </v-tooltip>
              </div>
              <v-select
                v-if="systemForm.scraping.auto_classify"
                v-model="systemForm.scraping.classify_by"
                :items="scrapingClassifyOptions"
                label="分类方式"
              />
              <v-select
                v-model="systemForm.scraping.duplicate_handling"
                :items="duplicateHandlingOptions"
                label="重复文件处理"
              />
            </div>

            <div class="settings-grid mt-4">
              <div class="scraping-mode-field">
                <div class="auto-organize-control">
                  <v-select
                    class="auto-organize-select"
                    :model-value="systemForm.scraping.auto_organize"
                    :items="autoOrganizeOptions"
                    label="自动整理"
                    @update:model-value="updateAutoOrganize"
                  />
                  <v-btn
                    v-if="directoryMonitorFailed"
                    aria-label="目录监听故障"
                    color="error"
                    icon="mdi-alert-circle"
                    variant="text"
                    @click.stop="openDirectoryMonitorFailureDialog"
                  />
                </div>
                <div class="scraping-mode-description" aria-live="polite">
                  {{ autoOrganizeDescription }}
                </div>
              </div>
              <div
                v-if="systemForm.scraping.auto_organize === 'directory'"
                class="scraping-mode-field"
              >
                <v-text-field
                  v-model.number="systemForm.scraping.directory_monitor_notification_delay_seconds"
                  label="通知延迟（秒）"
                  type="number"
                  min="1"
                  hint="在设定时间内持续有文件入库时，将重新计时并合并为一条通知。"
                  persistent-hint
                />
              </div>
              <div
                v-if="
                  systemForm.scraping.auto_organize === 'directory' &&
                  systemForm.scraping.directory_monitor_mode === 'polling'
                "
                class="scraping-mode-field"
              >
                <v-text-field
                  v-model.number="systemForm.scraping.directory_monitor_poll_interval_seconds"
                  label="轮询间隔（秒）"
                  type="number"
                  min="30"
                  hint="最短 30 秒；目录越大，建议设置更长的间隔。"
                  persistent-hint
                />
                <v-btn
                  :loading="directoryMonitorActionLoading"
                  prepend-icon="mdi-radar"
                  size="small"
                  variant="tonal"
                  @click="retryNativeDirectoryMonitor"
                >
                  重新检测原生监听
                </v-btn>
              </div>
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn color="primary" :loading="systemSaving" @click="saveSystemSettings">
              保存刮削设置
            </v-btn>
          </v-card-actions>
        </v-card>

        <v-card class="settings-card mt-4">
          <v-card-title>搜索设置</v-card-title>
          <v-card-text>
            <div class="settings-grid">
              <v-textarea
                v-model="systemForm.search.exclude_keywords"
                label="排除关键词"
                placeholder="试听|sample|preview|acoustic"
                hint="用 | 分隔多个关键词。标题中包含任一关键词的种子会被过滤掉。"
                persistent-hint
                auto-grow
                rows="2"
              />
              <v-text-field
                v-model.number="systemForm.search.minimum_seeders"
                label="最少做种人数"
                type="number"
                min="0"
                hint="仅显示做种人数不少于此值的种子。设为 0 可关闭筛选；默认 1。"
                persistent-hint
              />
              <v-text-field
                v-model.number="systemForm.search.metadata_concurrency"
                label="元数据搜索并发数"
                type="number"
                min="1"
                max="20"
                hint="限制同时访问元数据源的搜索任务数量。默认 3；遇到频率限制可降到 1 或 2。"
                persistent-hint
              />
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn color="primary" :loading="systemSaving" @click="saveSystemSettings">
              保存搜索设置
            </v-btn>
          </v-card-actions>
        </v-card>

        <v-card class="settings-card mt-4">
          <v-card-title>数据库管理</v-card-title>
          <v-card-actions>
            <v-btn
              color="primary"
              prepend-icon="mdi-database-export-outline"
              :loading="databaseExporting"
              @click="exportDatabase"
            >
              导出数据库
            </v-btn>
            <v-spacer />
            <v-btn
              color="warning"
              prepend-icon="mdi-database-import-outline"
              :loading="databaseImporting"
              @click="openDatabaseImportStartDialog"
            >
              导入数据库
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-window-item>

      <v-window-item value="about">
        <v-card class="settings-card">
          <v-card-title>关于</v-card-title>
          <v-card-text>
            <div class="about-info-list">
              <div class="about-info-row">
                <span>系统名称</span>
                <strong>{{ aboutInfo?.app || 'MusicPilot' }}</strong>
              </div>
              <div class="about-info-row">
                <span>系统版本号</span>
                <div class="about-version">
                  <strong>{{ aboutInfo?.version || '-' }}</strong>
                  <a
                    v-if="aboutInfo?.latest_version && aboutInfo.latest_release_url"
                    :href="aboutInfo.latest_release_url"
                    rel="noreferrer"
                    target="_blank"
                  >
                    <v-chip color="primary" size="small" variant="tonal">
                      最新版 {{ aboutInfo.latest_version }}
                    </v-chip>
                  </a>
                </div>
              </div>
              <div class="about-info-row">
                <span>GitHub</span>
                <a
                  :href="aboutInfo?.repository_url || 'https://github.com/lzcer/MusicPilot'"
                  rel="noreferrer"
                  target="_blank"
                >
                  {{ aboutInfo?.repository_name || 'lzcer/MusicPilot' }}
                </a>
              </div>
              <div class="about-info-row">
                <span>发布频道</span>
                <a href="https://telegram.me/musicpilot_channel" rel="noreferrer" target="_blank">
                  @musicpilot_channel
                </a>
              </div>
              <div class="about-info-row">
                <span>许可证</span>
                <strong>{{ aboutInfo?.license || '-' }}</strong>
              </div>
              <div class="about-info-row about-info-row-block">
                <span>项目说明</span>
                <p>{{ aboutInfo?.description || '-' }}</p>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>
  </section>
</template>
