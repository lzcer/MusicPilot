<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'

type ResourceType = 'songs' | 'albums' | 'playlists'
type LoadState = 'idle' | 'loading' | 'success' | 'empty' | 'error'
type CatalogSource = 'apple_music' | 'qq_music' | 'netease_music'

type ChartItem = {
  id: string
  resource_type: ResourceType
  rank: number
  name: string
  artist_name?: string | null
  artwork_url?: string | null
  release_date?: string | null
  genres: string[]
  playcount?: number | null
}

type ChartResponse = {
  resource_type: ResourceType
  items: ChartItem[]
  next_offset?: number | null
  has_more: boolean
}

type DetailTrack = {
  id: string
  position: number
  name: string
  artist_name?: string | null
  album_name?: string | null
  artwork_url?: string | null
  duration_seconds?: number | null
}

type ItemDetail = {
  id: string
  resource_type: ResourceType
  name: string
  artist_name?: string | null
  album_name?: string | null
  description?: string | null
  artwork_url?: string | null
  external_url?: string | null
  release_date?: string | null
  genres: string[]
  duration_seconds?: number | null
  track_count?: number | null
  tracks: DetailTrack[]
}

type SongAction = {
  name: string
  artist_name?: string | null
}

type AlbumAction = SongAction & {
  id: string
  album_name: string
  artwork_url?: string | null
  release_date?: string | null
}

type PlaylistAction = {
  id: string
  name: string
  external_url: string
}

const props = defineProps<{ playlistAddingId?: string | null }>()
const emit = defineEmits<{
  'search-song': [item: SongAction]
  'search-album': [item: AlbumAction]
  'add-playlist': [item: PlaylistAction]
}>()

type ChartSection = {
  state: LoadState
  items: ChartItem[]
  error: string
  nextOffset: number | null
  hasMore: boolean
  loadingMore: boolean
  loadMoreError: string
  requestId: number
}

const resourceTypes: ResourceType[] = ['songs', 'albums', 'playlists']
function emptyChartSections(): Record<ResourceType, ChartSection> {
  return {
    songs: { state: 'idle', items: [], error: '', nextOffset: null, hasMore: false, loadingMore: false, loadMoreError: '', requestId: 0 },
    albums: { state: 'idle', items: [], error: '', nextOffset: null, hasMore: false, loadingMore: false, loadMoreError: '', requestId: 0 },
    playlists: { state: 'idle', items: [], error: '', nextOffset: null, hasMore: false, loadingMore: false, loadMoreError: '', requestId: 0 }
  }
}

const sourceChartSections = ref<Record<CatalogSource, Record<ResourceType, ChartSection>>>(
  {
    apple_music: emptyChartSections(),
    qq_music: emptyChartSections(),
    netease_music: emptyChartSections()
  }
)

const chartDialog = ref(false)
const chartDialogType = ref<ResourceType>('songs')
const detailDialog = ref(false)
const detailState = ref<LoadState>('idle')
const detailItem = ref<ChartItem | null>(null)
const detail = ref<ItemDetail | null>(null)
const detailError = ref('')
let detailRequestId = 0
const activeSource = ref<CatalogSource>('qq_music')

const chartLabels: Record<ResourceType, string> = {
  songs: '热门歌曲',
  albums: '热门专辑',
  playlists: '热门歌单'
}

const sourceConfig: Record<CatalogSource, { label: string; apiPath: string }> = {
  apple_music: { label: 'Apple Music', apiPath: 'apple-music' },
  qq_music: { label: 'QQ 音乐', apiPath: 'qq-music' },
  netease_music: { label: '网易云音乐', apiPath: 'netease-music' }
}

const chartIcons: Record<ResourceType, string> = {
  songs: 'mdi-music-note',
  albums: 'mdi-album',
  playlists: 'mdi-playlist-music'
}

const catalogSource = computed<CatalogSource>(() => activeSource.value)
const chartSections = computed(() => sourceChartSections.value[catalogSource.value])
const currentSource = computed(() => sourceConfig[catalogSource.value])
const chartDialogItems = computed(() => chartSections.value[chartDialogType.value].items)

function chartLabel(resourceType: ResourceType) {
  if (
    resourceType === 'albums' &&
    (catalogSource.value === 'qq_music' || catalogSource.value === 'netease_music')
  ) return '新碟'
  return chartLabels[resourceType]
}

function artwork(url?: string | null, size = 600) {
  if (!url) return ''
  const resolved = url
    .replace(/\/\d+x\d+bb\.(jpg|png)$/i, `/${size}x${size}bb.$1`)
    .replace('{w}', String(size))
    .replace('{h}', String(size))
    .replace('{f}', 'jpg')
  if (resolved.includes('.music.126.net/')) {
    return `${resolved}${resolved.includes('?') ? '&' : '?'}param=${size}y${size}`
  }
  return resolved
}

function formatDuration(seconds?: number | null) {
  if (seconds == null) return '-'
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

function detailSubtitle(item: ItemDetail) {
  if (item.resource_type === 'songs') return item.artist_name || '未知歌手'
  if (item.resource_type === 'albums') return item.artist_name || '未知歌手'
  return item.artist_name || currentSource.value.label
}

function detailMeta(item: ItemDetail) {
  const values: string[] = []
  if (item.release_date) values.push(item.release_date)
  if (item.genres.length) values.push(item.genres.slice(0, 2).join(' / '))
  if (item.duration_seconds != null) values.push(formatDuration(item.duration_seconds))
  if (item.track_count != null) values.push(`${item.track_count} 首歌曲`)
  return values
}

async function loadChart(resourceType: ResourceType, source = catalogSource.value) {
  const section = sourceChartSections.value[source][resourceType]
  const requestId = ++section.requestId
  section.state = 'loading'
  section.error = ''
  section.loadMoreError = ''
  try {
    const response = await api<ChartResponse>(
      `/api/discovery/${sourceConfig[source].apiPath}/charts/${resourceType}?offset=0&limit=20`
    )
    if (requestId !== section.requestId) return
    section.items = response.items
    section.nextOffset = response.next_offset ?? null
    section.hasMore = response.has_more
    section.state = response.items.length ? 'success' : 'empty'
  } catch (error) {
    if (requestId !== section.requestId) return
    section.state = 'error'
    section.error = error instanceof Error ? error.message : '发现内容加载失败'
  }
}

async function loadMoreChart() {
  if (!chartDialog.value) return
  const source = catalogSource.value
  const resourceType = chartDialogType.value
  const section = sourceChartSections.value[source][resourceType]
  if (!section.hasMore || section.loadingMore || section.nextOffset == null) return
  const requestId = section.requestId
  section.loadingMore = true
  section.loadMoreError = ''
  try {
    const response = await api<ChartResponse>(
      `/api/discovery/${sourceConfig[source].apiPath}/charts/${resourceType}?offset=${section.nextOffset}&limit=20`
    )
    if (requestId !== section.requestId || source !== catalogSource.value || resourceType !== chartDialogType.value) return
    const existing = new Set(section.items.map(chartItemKey))
    const added = response.items.filter((item) => !existing.has(chartItemKey(item)))
    section.items.push(...added)
    section.nextOffset = response.next_offset ?? null
    section.hasMore = response.has_more && added.length > 0
  } catch (error) {
    if (requestId !== section.requestId) return
    section.loadMoreError = error instanceof Error ? error.message : '更多内容加载失败'
  } finally {
    if (requestId === section.requestId) section.loadingMore = false
  }
}

function onChartLoadMoreIntersect(isIntersecting: boolean) {
  if (isIntersecting) void loadMoreChart()
}

function openChart(resourceType: ResourceType) {
  chartDialogType.value = resourceType
  chartDialog.value = true
}

function openDetail(item: ChartItem) {
  detailItem.value = item
  detail.value = null
  detailError.value = ''
  detailDialog.value = true
  void loadDetail(item)
}

function openTrackDetail(track: DetailTrack) {
  openDetail({
    id: track.id,
    resource_type: 'songs',
    rank: track.position,
    name: track.name,
    artist_name: track.artist_name || detail.value?.artist_name,
    artwork_url: track.artwork_url,
    genres: []
  })
}

function searchCurrentSong() {
  if (!detail.value || detail.value.resource_type !== 'songs') return
  detailDialog.value = false
  emit('search-song', {
    name: detail.value.name,
    artist_name: detail.value.artist_name
  })
}

function searchCurrentAlbum() {
  if (!detail.value || detail.value.resource_type !== 'albums') return
  detailDialog.value = false
  emit('search-album', {
    id: detail.value.id,
    name: detail.value.name,
    album_name: detail.value.name,
    artist_name: detail.value.artist_name,
    artwork_url: detail.value.artwork_url,
    release_date: detail.value.release_date
  })
}

function addCurrentPlaylist() {
  if (
    !detail.value ||
    detail.value.resource_type !== 'playlists' ||
    !detail.value.external_url
  ) return
  emit('add-playlist', {
    id: detail.value.id,
    name: detail.value.name,
    external_url: detail.value.external_url
  })
}

async function loadDetail(item = detailItem.value) {
  if (!item) return
  const requestId = ++detailRequestId
  detailState.value = 'loading'
  detailError.value = ''
  const source = catalogSource.value
  try {
    const response = await api<ItemDetail>(
      `/api/discovery/${sourceConfig[source].apiPath}/items/${item.resource_type}/${encodeURIComponent(item.id)}`
    )
    if (requestId !== detailRequestId) return
    detail.value = response
    detailState.value = 'success'
  } catch (error) {
    if (requestId !== detailRequestId) return
    detailState.value = 'error'
    detailError.value = error instanceof Error ? error.message : '详情加载失败'
  }
}

function chartItemKey(item: ChartItem) {
  return `${item.resource_type}:${item.id}`
}

onMounted(() => {
  for (const resourceType of resourceTypes) void loadChart(resourceType, 'qq_music')
})

watch(activeSource, (source) => {
  detailDialog.value = false
  chartDialog.value = false
  for (const resourceType of resourceTypes) {
    if (sourceChartSections.value[source][resourceType].state === 'idle') {
      void loadChart(resourceType, source)
    }
  }
})
</script>

<template>
  <section class="discovery-page page-stack">
    <v-tabs v-model="activeSource" class="discovery-source-tabs" color="primary">
      <v-tab prepend-icon="mdi-music-note" value="qq_music">QQ 音乐</v-tab>
      <v-tab prepend-icon="mdi-music-circle" value="netease_music">网易云音乐</v-tab>
      <v-tab prepend-icon="mdi-apple" value="apple_music">Apple Music</v-tab>
    </v-tabs>

    <section v-for="resourceType in resourceTypes" :key="resourceType" class="discovery-section">
      <header class="discovery-section-head">
        <div>
          <v-icon :icon="chartIcons[resourceType]" size="20" />
          <h2>{{ chartLabel(resourceType) }}</h2>
        </div>
        <v-btn
          v-if="chartSections[resourceType].items.length"
          append-icon="mdi-arrow-right"
          size="small"
          variant="text"
          @click="openChart(resourceType)"
        >
          查看全部
        </v-btn>
      </header>

      <div v-if="chartSections[resourceType].state === 'loading'" :class="resourceType === 'songs' ? 'discovery-song-list' : 'discovery-cover-grid'">
        <template v-if="resourceType === 'songs'">
          <div v-for="index in 5" :key="index" class="discovery-song-row discovery-skeleton-row">
            <v-skeleton-loader type="text" width="24" />
            <v-skeleton-loader type="image" width="48" height="48" />
            <v-skeleton-loader type="list-item-two-line" />
          </div>
        </template>
        <template v-else>
          <div v-for="index in 5" :key="index" class="discovery-cover-item">
            <v-skeleton-loader class="discovery-cover-skeleton" type="image" />
            <v-skeleton-loader type="list-item-two-line" />
          </div>
        </template>
      </div>

      <v-alert
        v-else-if="chartSections[resourceType].state === 'error'"
        color="error"
        icon="mdi-alert-circle-outline"
        variant="tonal"
      >
        <div class="discovery-error-content">
          <span>{{ chartSections[resourceType].error }}</span>
          <v-btn size="small" variant="text" @click="loadChart(resourceType)">重试</v-btn>
        </div>
      </v-alert>

      <div v-else-if="chartSections[resourceType].state === 'empty'" class="discovery-empty">
        暂无{{ chartLabel(resourceType) }}
      </div>

      <div v-else-if="resourceType === 'songs'" class="discovery-song-list">
        <button
          v-for="item in chartSections.songs.items.slice(0, 5)"
          :key="chartItemKey(item)"
          class="discovery-song-row"
          type="button"
          @click="openDetail(item)"
        >
          <span class="discovery-rank">{{ item.rank }}</span>
          <img v-if="item.artwork_url" :src="artwork(item.artwork_url, 160)" alt="" loading="lazy" />
          <span v-else class="discovery-artwork-placeholder"><v-icon icon="mdi-music-note" /></span>
          <span class="discovery-song-copy">
            <strong>{{ item.name }}</strong>
            <small>{{ item.artist_name || '未知歌手' }}</small>
          </span>
          <span class="discovery-song-genre">{{ item.genres[0] || '' }}</span>
          <v-icon icon="mdi-chevron-right" size="20" />
        </button>
      </div>

      <div v-else class="discovery-cover-grid">
        <button
          v-for="item in chartSections[resourceType].items.slice(0, 5)"
          :key="chartItemKey(item)"
          class="discovery-cover-item"
          type="button"
          @click="openDetail(item)"
        >
          <img v-if="item.artwork_url" :src="artwork(item.artwork_url)" alt="" loading="lazy" />
          <span v-else class="discovery-cover-placeholder">
            <v-icon :icon="chartIcons[resourceType]" size="36" />
          </span>
          <strong>{{ item.name }}</strong>
          <small>{{ item.artist_name || (resourceType === 'playlists' ? currentSource.label : '未知歌手') }}</small>
        </button>
      </div>
    </section>

    <v-dialog v-model="chartDialog" max-width="1040" scrollable>
      <v-card class="discovery-dialog-card">
        <v-card-title class="discovery-dialog-title">
          <span>{{ chartLabel(chartDialogType) }}</span>
          <v-btn icon="mdi-close" size="small" variant="text" title="关闭" @click="chartDialog = false" />
        </v-card-title>
        <v-card-text class="discovery-chart-dialog-body">
          <div v-if="chartDialogType === 'songs'" class="discovery-song-list discovery-dialog-song-list">
            <button
              v-for="item in chartDialogItems"
              :key="chartItemKey(item)"
              class="discovery-song-row"
              type="button"
              @click="openDetail(item)"
            >
              <span class="discovery-rank">{{ item.rank }}</span>
              <img v-if="item.artwork_url" :src="artwork(item.artwork_url, 160)" alt="" loading="lazy" />
              <span v-else class="discovery-artwork-placeholder"><v-icon icon="mdi-music-note" /></span>
              <span class="discovery-song-copy"><strong>{{ item.name }}</strong><small>{{ item.artist_name || '未知歌手' }}</small></span>
              <span class="discovery-song-genre">{{ item.genres[0] || '' }}</span>
              <v-icon icon="mdi-chevron-right" size="20" />
            </button>
          </div>
          <div v-else class="discovery-cover-grid discovery-dialog-grid">
            <button
              v-for="item in chartDialogItems"
              :key="chartItemKey(item)"
              class="discovery-cover-item"
              type="button"
              @click="openDetail(item)"
            >
              <img v-if="item.artwork_url" :src="artwork(item.artwork_url)" alt="" loading="lazy" />
              <span v-else class="discovery-cover-placeholder"><v-icon :icon="chartIcons[chartDialogType]" size="36" /></span>
              <strong>{{ item.name }}</strong>
              <small>{{ item.artist_name || (chartDialogType === 'playlists' ? currentSource.label : '未知歌手') }}</small>
            </button>
          </div>
          <div v-if="chartSections[chartDialogType].loadMoreError" class="discovery-load-more-error">
            <span>{{ chartSections[chartDialogType].loadMoreError }}</span>
            <v-btn size="small" variant="text" @click="loadMoreChart">重试</v-btn>
          </div>
          <div
            v-else-if="chartSections[chartDialogType].hasMore"
            v-intersect="onChartLoadMoreIntersect"
            class="discovery-load-more-sentinel"
          >
            <v-progress-circular v-if="chartSections[chartDialogType].loadingMore" indeterminate size="22" width="2" />
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="detailDialog" max-width="900" scrollable>
      <v-card class="discovery-dialog-card discovery-detail-card">
        <v-card-title class="discovery-dialog-title">
          <span>{{ detailItem ? `${chartLabel(detailItem.resource_type)}详情` : '详情' }}</span>
          <v-btn icon="mdi-close" size="small" variant="text" title="关闭" @click="detailDialog = false" />
        </v-card-title>

        <template v-if="detailState === 'loading'">
          <div class="discovery-detail-head discovery-detail-loading">
            <v-skeleton-loader type="image" class="discovery-detail-cover" />
            <v-skeleton-loader type="heading, list-item-two-line, paragraph" />
          </div>
          <v-skeleton-loader v-if="detailItem?.resource_type !== 'songs'" type="table-row-divider@6" />
        </template>

        <v-card-text v-else-if="detailState === 'error'" class="discovery-detail-error">
          <v-alert color="error" icon="mdi-alert-circle-outline" variant="tonal">
            <div class="discovery-error-content">
              <span>{{ detailError }}</span>
              <v-btn size="small" variant="text" @click="loadDetail()">重试</v-btn>
            </div>
          </v-alert>
        </v-card-text>

        <template v-else-if="detail">
          <div class="discovery-detail-head">
            <img v-if="detail.artwork_url" :src="artwork(detail.artwork_url)" alt="" class="discovery-detail-cover" />
            <span v-else class="discovery-detail-cover discovery-cover-placeholder"><v-icon :icon="chartIcons[detail.resource_type]" size="44" /></span>
            <div class="discovery-detail-copy">
              <div class="discovery-detail-kind">{{ currentSource.label }} · {{ chartLabel(detail.resource_type) }}</div>
              <h2>{{ detail.name }}</h2>
              <p class="discovery-detail-subtitle">{{ detailSubtitle(detail) }}</p>
              <p v-if="detail.description" class="discovery-detail-description">{{ detail.description }}</p>
              <div v-if="detailMeta(detail).length" class="discovery-detail-meta">
                <span v-for="item in detailMeta(detail)" :key="item">{{ item }}</span>
              </div>
              <div class="discovery-detail-actions">
                <v-btn
                  v-if="detail.resource_type === 'songs'"
                  prepend-icon="mdi-magnify"
                  color="primary"
                  size="small"
                  @click="searchCurrentSong"
                >
                  搜索资源
                </v-btn>
                <v-btn
                  v-else-if="detail.resource_type === 'albums'"
                  prepend-icon="mdi-magnify"
                  color="primary"
                  size="small"
                  @click="searchCurrentAlbum"
                >
                  搜索资源
                </v-btn>
                <v-btn
                  v-else
                  prepend-icon="mdi-playlist-plus"
                  color="primary"
                  size="small"
                  :disabled="!detail.external_url"
                  :loading="props.playlistAddingId === detail.id"
                  @click="addCurrentPlaylist"
                >
                  加入我的歌单
                </v-btn>
              </div>
            </div>
          </div>

          <v-card-text v-if="detail.resource_type === 'songs'" class="discovery-song-facts">
            <dl>
              <div><dt>歌曲</dt><dd>{{ detail.name }}</dd></div>
              <div><dt>歌手</dt><dd>{{ detail.artist_name || '-' }}</dd></div>
              <div><dt>专辑</dt><dd>{{ detail.album_name || '-' }}</dd></div>
              <div><dt>发行日期</dt><dd>{{ detail.release_date || '-' }}</dd></div>
              <div><dt>类型</dt><dd>{{ detail.genres.join(' / ') || '-' }}</dd></div>
              <div><dt>时长</dt><dd>{{ formatDuration(detail.duration_seconds) }}</dd></div>
            </dl>
          </v-card-text>

          <div v-else class="discovery-track-section">
            <div class="discovery-track-head"><span>#</span><span></span><span>歌曲</span><span>歌手</span><span>时长</span></div>
            <div class="discovery-track-list">
              <button
                v-for="track in detail.tracks"
                :key="`${track.position}:${track.id}`"
                class="discovery-track-row"
                type="button"
                @click="openTrackDetail(track)"
              >
                <span class="discovery-rank">{{ track.position }}</span>
                <img v-if="track.artwork_url" :src="artwork(track.artwork_url, 120)" alt="" loading="lazy" />
                <span v-else class="discovery-artwork-placeholder"><v-icon icon="mdi-music-note" size="18" /></span>
                <strong>{{ track.name }}</strong>
                <span>{{ track.artist_name || detail.artist_name || '-' }}</span>
                <span>{{ formatDuration(track.duration_seconds) }}</span>
              </button>
              <div v-if="!detail.tracks.length" class="discovery-empty">暂无曲目</div>
            </div>
          </div>
        </template>
      </v-card>
    </v-dialog>
  </section>
</template>

<style scoped>
.discovery-source-tabs{border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity))}
.discovery-page{gap:22px}.discovery-section{min-width:0}.discovery-section-head{align-items:center;display:flex;justify-content:space-between;margin-bottom:10px}.discovery-section-head>div{align-items:center;display:flex;gap:8px}.discovery-section-head h2{font-size:16px;letter-spacing:0;margin:0}.discovery-song-list{border-top:1px solid rgba(var(--v-border-color),var(--v-border-opacity))}.discovery-song-row{align-items:center;background:transparent;border:0;border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity));color:inherit;display:grid;font:inherit;gap:12px;grid-template-columns:32px 48px minmax(0,1.4fr) minmax(80px,.6fr) 24px;min-height:65px;padding:8px 6px;text-align:left;width:100%}.discovery-song-row:not(.discovery-skeleton-row){cursor:pointer}.discovery-song-row:not(.discovery-skeleton-row):hover{background:rgba(var(--v-theme-primary),.05)}.discovery-song-row:focus-visible,.discovery-cover-item:focus-visible{outline:2px solid rgba(var(--v-theme-primary),.65);outline-offset:2px}.discovery-song-row img,.discovery-artwork-placeholder{border-radius:6px;height:48px;object-fit:cover;width:48px}.discovery-artwork-placeholder,.discovery-cover-placeholder{align-items:center;background:rgba(var(--v-theme-on-surface),.07);color:rgba(var(--v-theme-on-surface),.45);display:flex;justify-content:center}.discovery-rank{color:rgba(var(--v-theme-on-surface),.56);font-variant-numeric:tabular-nums;text-align:center}.discovery-song-copy{display:flex;flex-direction:column;min-width:0}.discovery-song-copy strong,.discovery-song-copy small,.discovery-song-genre{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.discovery-song-copy strong{font-size:14px}.discovery-song-copy small,.discovery-song-genre{color:rgba(var(--v-theme-on-surface),.6);font-size:12px}.discovery-cover-grid{display:grid;gap:16px;grid-template-columns:repeat(5,minmax(0,1fr))}.discovery-cover-item{background:transparent;border:0;color:inherit;cursor:pointer;font:inherit;min-width:0;padding:0;text-align:left}.discovery-cover-item img,.discovery-cover-placeholder,.discovery-cover-skeleton{aspect-ratio:1;border-radius:8px;display:flex;object-fit:cover;width:100%}.discovery-cover-item:hover img,.discovery-cover-item:hover .discovery-cover-placeholder{outline:3px solid rgba(var(--v-theme-primary),.25)}.discovery-cover-item strong,.discovery-cover-item small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.discovery-cover-item strong{font-size:13px;margin-top:8px}.discovery-cover-item small{color:rgba(var(--v-theme-on-surface),.58);font-size:11px;margin-top:2px}.discovery-skeleton-row{grid-template-columns:32px 48px minmax(0,1fr)}.discovery-empty{color:rgba(var(--v-theme-on-surface),.58);padding:24px;text-align:center}.discovery-error-content{align-items:center;display:flex;gap:12px;justify-content:space-between}.discovery-dialog-card{max-height:min(86vh,900px)}.discovery-dialog-title{align-items:center;border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity));display:flex;flex:0 0 auto;font-size:17px;justify-content:space-between;min-height:56px}.discovery-chart-dialog-body{padding-top:16px}.discovery-dialog-grid{grid-template-columns:repeat(5,minmax(0,1fr))}.discovery-dialog-song-list{border-top:0}.discovery-detail-card{display:flex;flex-direction:column;height:min(86vh,900px);overflow:hidden}.discovery-detail-head{display:grid;flex:0 0 auto;gap:22px;grid-template-columns:150px minmax(0,1fr);padding:22px}.discovery-detail-cover{aspect-ratio:1;border-radius:8px;height:150px;object-fit:cover;width:150px}.discovery-detail-loading>:last-child{min-width:0}.discovery-detail-kind{color:rgb(var(--v-theme-primary));font-size:12px;font-weight:700}.discovery-detail-copy h2{font-size:24px;line-height:31px;margin:5px 0 2px;overflow-wrap:anywhere}.discovery-detail-subtitle{font-size:14px;margin:0}.discovery-detail-description{color:rgba(var(--v-theme-on-surface),.65);font-size:12px;line-height:19px;margin:10px 0 0;max-height:76px;overflow-y:auto;padding-right:6px;white-space:pre-line}.discovery-detail-meta{color:rgba(var(--v-theme-on-surface),.58);display:flex;flex-wrap:wrap;font-size:11px;gap:12px;margin-top:12px}.discovery-detail-error{padding:24px}.discovery-song-facts{border-top:1px solid rgba(var(--v-border-color),var(--v-border-opacity));flex:1 1 auto;min-height:0;overflow-y:auto;padding:0 22px 20px}.discovery-song-facts dl{margin:0}.discovery-song-facts dl>div{display:grid;font-size:13px;gap:16px;grid-template-columns:110px 1fr;padding:11px 0}.discovery-song-facts dl>div+div{border-top:1px solid rgba(var(--v-border-color),var(--v-border-opacity))}.discovery-song-facts dt{color:rgba(var(--v-theme-on-surface),.58)}.discovery-song-facts dd{font-weight:600;margin:0}.discovery-track-section{border-top:1px solid rgba(var(--v-border-color),var(--v-border-opacity));display:flex;flex:1 1 auto;flex-direction:column;min-height:180px;overflow:hidden;padding:0 22px 20px}.discovery-track-list{flex:1 1 auto;min-height:0;overflow-y:auto}.discovery-track-head,.discovery-track-row{align-items:center;display:grid;gap:10px;grid-template-columns:34px 38px minmax(0,1.35fr) minmax(0,1fr) 54px}.discovery-track-head{color:rgba(var(--v-theme-on-surface),.5);flex:0 0 34px;font-size:10px;height:34px}.discovery-track-row{border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity));font-size:12px;min-height:52px}.discovery-track-row img,.discovery-track-row .discovery-artwork-placeholder{border-radius:5px;height:34px;object-fit:cover;width:34px}.discovery-track-row strong,.discovery-track-row>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.discovery-detail-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.discovery-track-row{background:transparent;border-left:0;border-right:0;border-top:0;color:inherit;cursor:pointer;font:inherit;padding:0;text-align:left;width:100%}.discovery-track-row:hover{background:rgba(var(--v-theme-primary),.05)}.discovery-track-row:focus-visible{outline:2px solid rgba(var(--v-theme-primary),.65);outline-offset:-2px}.discovery-load-more-sentinel{align-items:center;display:flex;height:52px;justify-content:center}.discovery-load-more-error{align-items:center;color:rgba(var(--v-theme-on-surface),.62);display:flex;font-size:12px;gap:8px;justify-content:center;min-height:52px}
@media(max-width:900px){.discovery-cover-grid,.discovery-dialog-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:600px){.discovery-page{gap:18px}.discovery-source-tabs :deep(.v-slide-group__content){justify-content:space-between}.discovery-source-tabs :deep(.v-tab){font-size:12px;min-width:0;padding:0 7px}.discovery-source-tabs :deep(.v-btn__prepend){display:none}.discovery-cover-grid,.discovery-dialog-grid{gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}.discovery-song-row{gap:8px;grid-template-columns:24px 42px minmax(0,1fr) 20px}.discovery-song-row img,.discovery-artwork-placeholder{height:42px;width:42px}.discovery-song-genre{display:none}.discovery-dialog-card{height:100%;max-height:none}.discovery-detail-head{gap:14px;grid-template-columns:96px minmax(0,1fr);padding:16px}.discovery-detail-cover{height:96px;width:96px}.discovery-detail-copy h2{font-size:19px;line-height:25px}.discovery-detail-description{max-height:57px}.discovery-track-section{min-height:0;padding:0 12px 14px}.discovery-track-head,.discovery-track-row{grid-template-columns:28px 34px minmax(0,1fr) 50px}.discovery-track-head span:nth-child(4),.discovery-track-row>span:nth-child(4){display:none}.discovery-song-facts{padding:0 16px 16px}.discovery-song-facts dl>div{grid-template-columns:84px 1fr}}
</style>
