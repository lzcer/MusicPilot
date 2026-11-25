<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  fileDetailDialog,
  fileDetailLoading,
  fileDetailError,
  fileDetail,
  fileDetailCoverSource,
  formatSize,
  formatAudioDuration,
  formatAudioBitrate,
  formatAudioSampleRate,
  formatAudioChannels,
  formatTime
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="fileDetailDialog" max-width="900" scrollable>
    <v-card :title="fileDetail?.name || '音频详情'">
      <v-progress-linear v-if="fileDetailLoading" indeterminate color="primary" />
      <v-card-text class="file-detail-body">
        <div v-if="fileDetailLoading" class="file-detail-loading">正在读取音频详情...</div>
        <v-alert v-else-if="fileDetailError" type="error" variant="tonal">
          {{ fileDetailError }}
        </v-alert>
        <div v-else-if="fileDetail" class="file-detail-content">
          <div class="file-detail-cover-panel">
            <img
              v-if="fileDetailCoverSource"
              class="file-detail-cover"
              :src="fileDetailCoverSource"
              :alt="`${fileDetail.title} 封面`"
            />
            <div v-else class="file-detail-cover-empty">
              <v-icon icon="mdi-album" size="64" />
              <span>无内嵌封面</span>
            </div>
          </div>

          <div class="file-detail-sections">
            <section class="file-detail-section">
              <h3>基本信息</h3>
              <dl class="file-detail-list">
                <div>
                  <dt>文件名</dt>
                  <dd>{{ fileDetail.name }}</dd>
                </div>
                <div>
                  <dt>相对路径</dt>
                  <dd>{{ fileDetail.path }}</dd>
                </div>
                <div>
                  <dt>格式</dt>
                  <dd>{{ fileDetail.format }}（{{ fileDetail.extension }}）</dd>
                </div>
                <div>
                  <dt>大小</dt>
                  <dd>{{ formatSize(fileDetail.size) }}</dd>
                </div>
                <div>
                  <dt>修改时间</dt>
                  <dd>{{ formatTime(fileDetail.modified_at) }}</dd>
                </div>
              </dl>
            </section>

            <section class="file-detail-section">
              <h3>元数据</h3>
              <dl class="file-detail-list">
                <div>
                  <dt>标题</dt>
                  <dd>{{ fileDetail.title || '-' }}</dd>
                </div>
                <div>
                  <dt>歌手</dt>
                  <dd>{{ fileDetail.artist || '-' }}</dd>
                </div>
                <div>
                  <dt>专辑</dt>
                  <dd>{{ fileDetail.album || '-' }}</dd>
                </div>
                <div>
                  <dt>专辑歌手</dt>
                  <dd>{{ fileDetail.album_artist || '-' }}</dd>
                </div>
                <div>
                  <dt>年份</dt>
                  <dd>{{ fileDetail.year ?? '-' }}</dd>
                </div>
                <div>
                  <dt>音轨</dt>
                  <dd>{{ fileDetail.track_number ?? '-' }}</dd>
                </div>
              </dl>
            </section>

            <section class="file-detail-section">
              <h3>音频参数</h3>
              <dl class="file-detail-list">
                <div>
                  <dt>时长</dt>
                  <dd>{{ formatAudioDuration(fileDetail.duration) }}</dd>
                </div>
                <div>
                  <dt>码率</dt>
                  <dd>{{ formatAudioBitrate(fileDetail.bitrate) }}</dd>
                </div>
                <div>
                  <dt>采样率</dt>
                  <dd>{{ formatAudioSampleRate(fileDetail.sample_rate) }}</dd>
                </div>
                <div>
                  <dt>声道</dt>
                  <dd>{{ formatAudioChannels(fileDetail.channels) }}</dd>
                </div>
              </dl>
            </section>

            <section class="file-detail-section file-detail-lyrics-section">
              <h3>歌词</h3>
              <pre v-if="fileDetail.lyrics" class="file-detail-lyrics">{{ fileDetail.lyrics }}</pre>
              <div v-else class="file-detail-empty-value">-</div>
            </section>
          </div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="fileDetailDialog = false">关闭</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
