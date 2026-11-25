<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  playlistAddDialog,
  playlistAddSource,
  playlistAddQuery,
  playlistAddArtist,
  playlistAddCandidates,
  playlistAddPage,
  playlistAddTotal,
  playlistAddNextOffset,
  playlistAddLoading,
  playlistAddSearched,
  playlistAddSavingKey,
  playlistAddedKeys,
  playlistAddDuplicates,
  playlistAddDuplicate,
  playlistAddPageSize,
  trimmedInput,
  playlistTrackLabel,
  locatePlaylistTrack,
  searchPlaylistAddCandidates,
  loadPlaylistAddCandidates,
  addPlaylistCandidate
} = useWorkspace()
</script>

<template>
  <v-dialog v-model="playlistAddDialog" :persistent="playlistAddSavingKey !== null" max-width="820">
    <v-card :title="playlistAddSource === 'library' ? '从音乐库添加' : '从网络添加'">
      <v-card-text>
        <v-form class="toolbar-row dialog-filter-row" @submit.prevent="searchPlaylistAddCandidates">
          <v-text-field
            v-model="playlistAddQuery"
            :label="playlistAddSource === 'library' ? '歌名、歌手或专辑' : '歌名'"
            prepend-inner-icon="mdi-magnify"
            density="compact"
            hide-details
            clearable
          />
          <v-text-field
            v-if="playlistAddSource === 'network'"
            v-model="playlistAddArtist"
            label="歌手"
            density="compact"
            hide-details
            clearable
          />
          <v-btn
            type="submit"
            variant="tonal"
            :disabled="
              playlistAddSource === 'network' &&
              !trimmedInput(playlistAddQuery) &&
              !trimmedInput(playlistAddArtist)
            "
          >
            搜索
          </v-btn>
        </v-form>
        <v-alert
          v-if="playlistAddDuplicate"
          color="primary"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          <div class="d-flex align-center justify-space-between flex-wrap ga-2">
            <span>歌单中已存在：{{ playlistTrackLabel(playlistAddDuplicate) }}</span>
            <v-btn variant="text" size="small" @click="locatePlaylistTrack(playlistAddDuplicate)">
              在歌单中查看
            </v-btn>
          </div>
        </v-alert>
        <v-progress-linear v-if="playlistAddLoading" indeterminate color="primary" />
        <v-table
          class="playlist-add-table fixed-table"
          fixed-header
          height="min(48vh, 420px)"
          density="compact"
        >
          <thead>
            <tr>
              <th>歌名</th>
              <th>歌手</th>
              <th>专辑</th>
              <th class="sticky-action-col playlist-add-action-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="candidate in playlistAddCandidates" :key="candidate.key">
              <td class="truncate-cell" :title="candidate.title">{{ candidate.title }}</td>
              <td class="truncate-cell" :title="candidate.artist ?? undefined">
                {{ candidate.artist || '-' }}
              </td>
              <td class="truncate-cell" :title="candidate.album ?? undefined">
                {{ candidate.album || '-' }}
              </td>
              <td class="sticky-action-col playlist-add-action-col">
                <v-btn
                  size="small"
                  variant="text"
                  color="primary"
                  :loading="playlistAddSavingKey === candidate.key"
                  :disabled="
                    playlistAddedKeys.has(candidate.key) ||
                    (playlistAddSavingKey !== null && playlistAddSavingKey !== candidate.key)
                  "
                  @click="addPlaylistCandidate(candidate)"
                >
                  {{
                    playlistAddedKeys.has(candidate.key)
                      ? '已添加'
                      : playlistAddDuplicates.has(candidate.key)
                        ? '已存在'
                        : '添加'
                  }}
                </v-btn>
              </td>
            </tr>
            <tr v-if="!playlistAddCandidates.length && !playlistAddLoading">
              <td colspan="4" class="empty-cell">
                {{ playlistAddSearched ? '没有找到歌曲' : '输入歌名或歌手搜索歌曲' }}
              </td>
            </tr>
          </tbody>
        </v-table>
        <div v-if="playlistAddSource === 'library' && playlistAddTotal" class="pagination-row">
          <v-pagination
            v-model="playlistAddPage"
            :length="Math.ceil(playlistAddTotal / playlistAddPageSize)"
            density="comfortable"
            total-visible="5"
            @update:model-value="loadPlaylistAddCandidates()"
          />
          <v-chip color="secondary" variant="tonal">共 {{ playlistAddTotal }} 首</v-chip>
        </div>
        <div
          v-else-if="playlistAddSource === 'network' && playlistAddNextOffset !== null"
          class="pagination-row"
        >
          <v-btn
            variant="text"
            :loading="playlistAddLoading"
            @click="loadPlaylistAddCandidates(playlistAddNextOffset ?? 0)"
          >
            加载更多
          </v-btn>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn
          variant="text"
          :disabled="playlistAddSavingKey !== null"
          @click="playlistAddDialog = false"
          >关闭</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
