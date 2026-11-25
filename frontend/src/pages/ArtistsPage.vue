<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  refreshData,
  artists,
  artistQuery,
  artistPage,
  artistPageSize,
  artistTotal,
  artistLoading,
  artistBuilding,
  artistPageLength,
  loadArtists,
  applyArtistFilters,
  buildArtistLibrary,
  clearAndRebuildArtistLibrary,
  openArtistEditDialog,
  openArtistAliasDialog,
  openArtistMergeDialog
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <div class="toolbar-row">
      <v-btn
        prepend-icon="mdi-refresh"
        variant="tonal"
        :loading="artistLoading"
        @click="refreshData(loadArtists)"
      >
        刷新
      </v-btn>
      <v-btn
        color="primary"
        prepend-icon="mdi-database-plus"
        :loading="artistBuilding"
        @click="buildArtistLibrary"
      >
        从曲库构建
      </v-btn>
      <v-btn
        color="warning"
        prepend-icon="mdi-database-refresh"
        :loading="artistBuilding"
        @click="clearAndRebuildArtistLibrary"
      >
        清空并重建
      </v-btn>
      <v-text-field
        v-model="artistQuery"
        label="搜索歌手或别名"
        prepend-inner-icon="mdi-magnify"
        hide-details
        clearable
        class="table-search"
        @keyup.enter="applyArtistFilters"
        @click:clear="applyArtistFilters"
      />
      <v-btn prepend-icon="mdi-magnify" variant="tonal" @click="applyArtistFilters"> 搜索 </v-btn>
      <v-chip v-if="artistTotal" color="primary" variant="tonal">
        共 {{ artistTotal }} 个歌手
      </v-chip>
    </div>
    <v-card>
      <v-progress-linear v-if="artistLoading" indeterminate color="primary" />
      <v-table>
        <thead>
          <tr>
            <th>歌手名（权威名）</th>
            <th>归一化名</th>
            <th>别名</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!artists.length">
            <td colspan="4" class="empty-cell">暂无歌手数据，点击「从曲库构建」按钮自动生成</td>
          </tr>
          <tr v-for="artist in artists" :key="artist.id">
            <td>
              <strong>{{ artist.name }}</strong>
            </td>
            <td class="muted">{{ artist.normalized_name }}</td>
            <td>
              <div v-if="artist.aliases.length" class="alias-list">
                <v-chip
                  v-for="alias in artist.aliases"
                  :key="alias.alias"
                  size="x-small"
                  variant="tonal"
                  class="alias-chip"
                >
                  {{ alias.alias }}
                </v-chip>
              </div>
              <span v-else class="muted">-</span>
            </td>
            <td>
              <v-btn
                icon="mdi-pencil-outline"
                color="primary"
                variant="text"
                size="small"
                title="编辑"
                @click="openArtistEditDialog(artist)"
              />
              <v-btn
                icon="mdi-book-plus"
                color="primary"
                variant="text"
                size="small"
                title="添加别名"
                @click="openArtistAliasDialog(artist)"
              />
              <v-btn
                icon="mdi-call-merge"
                color="warning"
                variant="text"
                size="small"
                title="合并到此歌手"
                @click="openArtistMergeDialog(artist)"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
      <div class="pagination-row">
        <v-select
          v-model="artistPageSize"
          :items="[20, 50, 100]"
          label="每页"
          density="compact"
          hide-details
          class="page-size-select"
          @update:model-value="applyArtistFilters"
        />
        <v-pagination
          v-model="artistPage"
          :length="artistPageLength"
          density="comfortable"
          total-visible="7"
          @update:model-value="loadArtists"
        />
      </div>
    </v-card>
  </section>
</template>
