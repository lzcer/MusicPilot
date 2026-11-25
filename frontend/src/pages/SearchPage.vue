<script setup lang="ts">
import { useWorkspace } from '../workspace'

const {
  searchDialog,
  metadataSearchLoading,
  torrentSearchLoading,
  searchResultView,
  metadataCandidates,
  metadataHasMore,
  metadataPageLoading,
  metadataPageLoadFailed,
  selectedMedia,
  searchStats,
  hasSearchedTorrents,
  searchSiteFilter,
  searchPage,
  searchPageSize,
  torrentSearchConditionText,
  displayedSearchResults,
  resultSiteOptions,
  resultSortOptions,
  sortedSearchResults,
  pagedSearchResults,
  toggleSearchSort,
  selectSearchResultView,
  searchSortIcon,
  searchSortTitle,
  isActiveSearchSort,
  loadMoreMetadataCandidates,
  onMetadataLoadMoreIntersect,
  openSiteConfirm,
  mediaSummary,
  albumList,
  viewResult,
  searchResultType,
  openDownloadConfirm,
  formatSize
} = useWorkspace()
</script>

<template>
  <section class="page-stack">
    <div class="toolbar-row">
      <v-btn color="primary" prepend-icon="mdi-magnify" @click="searchDialog = true"> 搜索 </v-btn>
      <v-chip v-if="metadataSearchLoading" class="loading-chip" color="info" variant="tonal">
        <v-progress-circular indeterminate size="16" width="2" />
        搜索媒体信息
      </v-chip>
      <div v-if="torrentSearchLoading || hasSearchedTorrents" class="torrent-status-panel">
        <div class="torrent-status-counts">
          <v-progress-circular v-if="torrentSearchLoading" indeterminate size="16" width="2" />
          <div class="search-result-view-toggle" role="group" aria-label="结果范围">
            <v-btn
              :class="{ 'search-result-view-button--active': searchResultView === 'raw' }"
              :disabled="torrentSearchLoading"
              size="small"
              variant="text"
              @click="selectSearchResultView('raw')"
            >
              原始 {{ searchStats.raw_count }}
            </v-btn>
            <v-btn
              :class="{
                'search-result-view-button--active': searchResultView === 'filtered'
              }"
              size="small"
              variant="text"
              @click="selectSearchResultView('filtered')"
            >
              过滤后 {{ searchStats.filtered_count }}
            </v-btn>
          </div>
        </div>
        <div v-if="torrentSearchLoading" class="torrent-status-condition">
          {{ torrentSearchConditionText }}
        </div>
      </div>
      <div v-if="selectedMedia" class="selected-media-summary">
        {{ mediaSummary(selectedMedia) }}
      </div>
    </div>

    <div v-if="metadataSearchLoading" class="loading-panel">
      <v-progress-circular indeterminate color="primary" size="34" width="3" />
      <span>正在搜索媒体信息</span>
    </div>

    <div
      v-if="metadataCandidates.length && !metadataSearchLoading"
      class="result-card-grid media-card-grid"
    >
      <article
        v-for="candidate in metadataCandidates"
        :key="`${candidate.source}-${candidate.external_id}-${candidate.title}-${candidate.artist}`"
        :class="{ 'media-card--in-library': candidate.exists_in_library }"
        class="media-card"
        @click="openSiteConfirm(candidate)"
      >
        <span
          v-if="candidate.exists_in_library"
          class="media-card-library-mark"
          role="img"
          aria-label="已在库"
          title="已在库"
        >
          <v-icon color="success" icon="mdi-check-circle" size="30" />
        </span>
        <img
          v-if="candidate.cover_url"
          :src="candidate.cover_url"
          alt=""
          class="media-cover"
          loading="lazy"
        />
        <div class="media-card-body">
          <h3>{{ candidate.title }}</h3>
          <p>{{ candidate.artist || '未知艺人' }}</p>
          <div class="media-album-list">
            <div v-for="album in albumList(candidate)" :key="album" class="media-album">
              {{ album }}
            </div>
            <div v-if="!albumList(candidate).length" class="media-album">未知专辑</div>
          </div>
          <div class="media-card-tags">
            <v-chip size="small" variant="tonal">{{ candidate.release_date || '-' }}</v-chip>
            <v-chip size="small" variant="tonal">{{ albumList(candidate).length }} 个专辑</v-chip>
          </div>
        </div>
      </article>
    </div>
    <div
      v-if="
        metadataCandidates.length &&
        !metadataSearchLoading &&
        (metadataHasMore || metadataPageLoading || metadataPageLoadFailed)
      "
      v-intersect="onMetadataLoadMoreIntersect"
      class="metadata-load-more"
    >
      <v-progress-circular
        v-if="metadataPageLoading"
        indeterminate
        color="primary"
        size="24"
        width="2"
      />
      <v-btn
        v-else-if="metadataPageLoadFailed"
        prepend-icon="mdi-refresh"
        variant="text"
        @click="loadMoreMetadataCandidates"
      >
        重新加载
      </v-btn>
    </div>

    <v-card class="search-panel">
      <div v-if="displayedSearchResults.length" class="search-result-controls">
        <v-select
          v-model="searchSiteFilter"
          :items="resultSiteOptions"
          label="站点"
          hide-details
          density="compact"
          variant="outlined"
          class="site-result-filter"
        />
        <div class="result-sort-field" aria-label="排序">
          <span class="result-sort-label">排序</span>
          <v-btn
            v-for="option in resultSortOptions"
            :key="option.value"
            :class="{ 'result-sort-button--active': isActiveSearchSort(option.value) }"
            :title="searchSortTitle(option.value)"
            class="result-sort-button"
            size="small"
            variant="text"
            @click="toggleSearchSort(option.value)"
          >
            <span>{{ option.title }}</span>
            <v-icon
              v-if="searchSortIcon(option.value)"
              :icon="searchSortIcon(option.value)"
              class="result-sort-icon"
              size="16"
            />
          </v-btn>
        </div>
      </div>
      <div v-if="torrentSearchLoading && !sortedSearchResults.length" class="loading-panel">
        <v-progress-circular indeterminate color="primary" size="34" width="3" />
        <span>正在搜索种子资源</span>
      </div>
      <div v-else-if="sortedSearchResults.length" class="result-card-grid">
        <article
          v-for="row in pagedSearchResults"
          :key="row.download_url"
          class="result-card"
          @click="openDownloadConfirm(row)"
        >
          <div class="result-card-body">
            <div class="result-card-head">
              <h3>{{ row.title }}</h3>
            </div>
            <div class="result-card-source">
              <v-icon icon="mdi-server-network" size="22" />
              <span>{{ row.source }}</span>
            </div>
            <p class="result-card-subtitle">{{ row.subtitle || row.title }}</p>
            <div class="result-card-meta">
              <span
                ><v-icon icon="mdi-clock-outline" size="16" />{{ row.published_at || '-' }}</span
              >
              <span class="seeders"><v-icon icon="mdi-arrow-up" size="18" />{{ row.seeders }}</span>
              <span class="leechers"
                ><v-icon icon="mdi-arrow-down" size="18" />{{ row.leechers || 0 }}</span
              >
            </div>
            <div class="result-card-tags">
              <v-chip v-if="row.promotion" color="success" size="small" variant="flat">
                {{ row.promotion }}
              </v-chip>
              <v-chip color="secondary" size="small" variant="tonal">{{ row.source }}</v-chip>
              <v-chip
                v-if="searchResultType(row)"
                class="result-type-chip"
                color="info"
                size="small"
                variant="tonal"
              >
                类型 {{ searchResultType(row) }}
              </v-chip>
            </div>
          </div>
          <div class="result-card-footer">
            <v-chip color="primary" size="small" variant="flat">
              {{ formatSize(row.size_bytes) }}
            </v-chip>
            <v-btn
              icon="mdi-information-outline"
              color="primary"
              variant="text"
              size="small"
              title="查看原站点"
              @click.stop="viewResult(row)"
            />
          </div>
        </article>
      </div>
      <div v-else-if="hasSearchedTorrents" class="empty-cell">暂无搜索结果</div>
      <div v-if="sortedSearchResults.length" class="pagination-row">
        <v-select
          v-model="searchPageSize"
          :items="[10, 20, 50, 100]"
          label="每页"
          hide-details
          class="page-size"
        />
        <v-pagination
          v-model="searchPage"
          :length="Math.max(1, Math.ceil(sortedSearchResults.length / searchPageSize))"
          density="comfortable"
        />
      </div>
    </v-card>
  </section>
</template>
