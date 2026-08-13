<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const emit = defineEmits<{
  configure: []
  'search-song': [item: { name: string; artist_name?: string | null }]
}>()

type ResourceType = 'songs' | 'artists' | 'tags'
type LoadState = 'idle' | 'loading' | 'success' | 'empty' | 'error'

type ChartItem = {
  id: string
  resource_type: ResourceType
  rank: number
  name: string
  artist_name?: string | null
  artwork_url?: string | null
  listeners?: number | null
  playcount?: number | null
}

type ChartResponse = {
  items: ChartItem[]
  next_offset?: number | null
  has_more: boolean
}

type DetailTrack = {
  id: string
  position: number
  name: string
  artist_name?: string | null
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
  genres: string[]
  duration_seconds?: number | null
  track_count?: number | null
  listeners?: number | null
  playcount?: number | null
  tracks: DetailTrack[]
}

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

function emptySection(): ChartSection {
  return { state: 'idle', items: [], error: '', nextOffset: null, hasMore: false, loadingMore: false, loadMoreError: '', requestId: 0 }
}

const resourceTypes: ResourceType[] = ['songs', 'artists', 'tags']
const labels: Record<ResourceType, string> = {
  songs: '热门歌曲',
  artists: '热门歌手',
  tags: '热门标签'
}
const icons: Record<ResourceType, string> = {
  songs: 'mdi-music-note',
  artists: 'mdi-account-music-outline',
  tags: 'mdi-tag-multiple-outline'
}

const configured = ref<boolean | null>(null)
const sections = ref<Record<ResourceType, ChartSection>>({
  songs: emptySection(),
  artists: emptySection(),
  tags: emptySection()
})
const chartDialog = ref(false)
const chartType = ref<ResourceType>('songs')
const detailDialog = ref(false)
const detailState = ref<LoadState>('idle')
const selectedItem = ref<ChartItem | null>(null)
const detail = ref<ItemDetail | null>(null)
const detailError = ref('')
let detailRequestId = 0
const artworkRequests = new Map<string, Promise<void>>()

const chartItems = computed(() => sections.value[chartType.value].items)

function formatDuration(seconds?: number | null) {
  if (seconds == null) return '-'
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function formatCount(value?: number | null) {
  if (value == null) return '-'
  return new Intl.NumberFormat('zh-CN').format(value)
}

function itemMetric(item: ChartItem) {
  if (item.resource_type === 'songs') return item.playcount ? `${formatCount(item.playcount)} 次播放` : ''
  if (item.resource_type === 'artists') return item.listeners ? `${formatCount(item.listeners)} 位听众` : ''
  return item.playcount ? `${formatCount(item.playcount)} 次标记` : ''
}

function detailMeta(item: ItemDetail) {
  const values: string[] = []
  if (item.genres.length) values.push(item.genres.slice(0, 3).join(' / '))
  if (item.listeners != null) values.push(`${formatCount(item.listeners)} 位听众`)
  if (item.playcount != null) values.push(`${formatCount(item.playcount)} 次播放`)
  if (item.track_count != null) values.push(`${item.track_count} 首歌曲`)
  return values
}

async function loadStatus() {
  const response = await api<{ configured: boolean }>('/api/discovery/lastfm/status')
  configured.value = response.configured
  if (response.configured) resourceTypes.forEach((type) => void loadChart(type))
}

async function loadChart(resourceType: ResourceType) {
  const section = sections.value[resourceType]
  const requestId = ++section.requestId
  section.state = 'loading'
  section.error = ''
  section.loadMoreError = ''
  try {
    const response = await api<ChartResponse>(
      `/api/discovery/lastfm/charts/${resourceType}?offset=0&limit=20`
    )
    if (requestId !== section.requestId) return
    section.items = response.items
    section.nextOffset = response.next_offset ?? null
    section.hasMore = response.has_more
    section.state = response.items.length ? 'success' : 'empty'
    if (resourceType === 'songs') void hydrateSongArtwork(section.items.slice(0, 5))
  } catch (error) {
    if (requestId !== section.requestId) return
    section.state = 'error'
    section.error = error instanceof Error ? error.message : 'Last.fm 内容加载失败'
  }
}

async function loadMoreChart() {
  if (!chartDialog.value) return
  const resourceType = chartType.value
  const section = sections.value[resourceType]
  if (!section.hasMore || section.loadingMore || section.nextOffset == null) return
  const requestId = section.requestId
  section.loadingMore = true
  section.loadMoreError = ''
  try {
    const response = await api<ChartResponse>(
      `/api/discovery/lastfm/charts/${resourceType}?offset=${section.nextOffset}&limit=20`
    )
    if (requestId !== section.requestId || resourceType !== chartType.value) return
    const existing = new Set(section.items.map((item) => item.id))
    const added = response.items.filter((item) => !existing.has(item.id))
    section.items.push(...added)
    section.nextOffset = response.next_offset ?? null
    section.hasMore = response.has_more && added.length > 0
    if (resourceType === 'songs') void hydrateSongArtwork(added)
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
  chartType.value = resourceType
  chartDialog.value = true
  if (resourceType === 'songs') void hydrateSongArtwork(sections.value.songs.items)
}

async function hydrateSongArtwork(items: ChartItem[]) {
  const pending = items.filter((item) => !item.artwork_url)
  let nextIndex = 0
  const worker = async () => {
    while (nextIndex < pending.length) {
      const item = pending[nextIndex++]
      await hydrateSongArtworkItem(item)
    }
  }
  await Promise.all(Array.from({ length: Math.min(4, pending.length) }, worker))
}

async function hydrateSongArtworkItem(item: ChartItem) {
  let request = artworkRequests.get(item.id)
  if (!request) {
    request = api<ItemDetail>(
      `/api/discovery/lastfm/items/songs/${encodeURIComponent(item.id)}`
    )
      .then((response) => {
        if (response.artwork_url) item.artwork_url = response.artwork_url
      })
      .catch(() => undefined)
      .finally(() => artworkRequests.delete(item.id))
    artworkRequests.set(item.id, request)
  }
  await request
}

function openDetail(item: ChartItem) {
  selectedItem.value = item
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
    artwork_url: track.artwork_url
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

async function loadDetail(item = selectedItem.value) {
  if (!item) return
  const requestId = ++detailRequestId
  detailState.value = 'loading'
  detailError.value = ''
  try {
    const response = await api<ItemDetail>(
      `/api/discovery/lastfm/items/${item.resource_type}/${encodeURIComponent(item.id)}`
    )
    if (requestId !== detailRequestId) return
    detail.value = response
    detailState.value = 'success'
  } catch (error) {
    if (requestId !== detailRequestId) return
    detailState.value = 'error'
    detailError.value = error instanceof Error ? error.message : 'Last.fm 详情加载失败'
  }
}

onMounted(() => void loadStatus())
</script>

<template>
  <section class="lastfm-page page-stack">
    <v-skeleton-loader v-if="configured === null" type="heading, paragraph" />
    <v-alert v-else-if="!configured" color="info" icon="mdi-key-outline" variant="tonal">
      <div class="error-row">
        <span>请先在系统设置中配置 Last.fm API Key。</span>
        <v-btn size="small" variant="text" @click="emit('configure')">前往设置</v-btn>
      </div>
    </v-alert>

    <template v-else>
      <section v-for="resourceType in resourceTypes" :key="resourceType" class="chart-section">
        <header class="section-head">
          <div><v-icon :icon="icons[resourceType]" size="20" /><h2>{{ labels[resourceType] }}</h2></div>
          <v-btn v-if="sections[resourceType].items.length" append-icon="mdi-arrow-right" size="small" variant="text" @click="openChart(resourceType)">查看全部</v-btn>
        </header>

        <div v-if="sections[resourceType].state === 'loading'" :class="resourceType === 'songs' ? 'item-list' : 'item-grid'">
          <v-skeleton-loader v-for="index in 5" :key="index" :type="resourceType === 'songs' ? 'list-item-avatar-two-line' : 'image, list-item-two-line'" />
        </div>
        <v-alert v-else-if="sections[resourceType].state === 'error'" color="error" icon="mdi-alert-circle-outline" variant="tonal">
          <div class="error-row"><span>{{ sections[resourceType].error }}</span><v-btn size="small" variant="text" @click="loadChart(resourceType)">重试</v-btn></div>
        </v-alert>
        <div v-else-if="sections[resourceType].state === 'empty'" class="empty">暂无{{ labels[resourceType] }}</div>
        <div v-else :class="resourceType === 'songs' ? 'item-list' : 'item-grid'">
          <button v-for="item in sections[resourceType].items.slice(0, 5)" :key="item.id" :class="resourceType === 'songs' ? 'list-item' : 'grid-item'" type="button" @click="openDetail(item)">
            <span class="rank">{{ item.rank }}</span>
            <img v-if="item.artwork_url" :src="item.artwork_url" alt="" loading="lazy" />
            <span v-else class="placeholder"><v-icon :icon="icons[resourceType]" :size="resourceType === 'songs' ? 20 : 38" /></span>
            <span class="item-copy"><strong>{{ item.name }}</strong><small>{{ item.artist_name || itemMetric(item) }}</small></span>
            <span v-if="resourceType === 'songs'" class="metric">{{ itemMetric(item) }}</span>
            <v-icon v-if="resourceType === 'songs'" icon="mdi-chevron-right" size="20" />
          </button>
        </div>
      </section>
    </template>

    <v-dialog v-model="chartDialog" max-width="1040" scrollable>
      <v-card class="dialog-card">
        <v-card-title class="dialog-title"><span>{{ labels[chartType] }}</span><v-btn icon="mdi-close" size="small" title="关闭" variant="text" @click="chartDialog = false" /></v-card-title>
        <v-card-text>
          <div :class="chartType === 'songs' ? 'item-list' : 'item-grid dialog-grid'">
            <button v-for="item in chartItems" :key="item.id" :class="chartType === 'songs' ? 'list-item' : 'grid-item'" type="button" @click="openDetail(item)">
              <span class="rank">{{ item.rank }}</span>
              <img v-if="item.artwork_url" :src="item.artwork_url" alt="" loading="lazy" />
              <span v-else class="placeholder"><v-icon :icon="icons[chartType]" :size="chartType === 'songs' ? 20 : 38" /></span>
              <span class="item-copy"><strong>{{ item.name }}</strong><small>{{ item.artist_name || itemMetric(item) }}</small></span>
              <span v-if="chartType === 'songs'" class="metric">{{ itemMetric(item) }}</span>
              <v-icon v-if="chartType === 'songs'" icon="mdi-chevron-right" size="20" />
            </button>
          </div>
          <div v-if="sections[chartType].loadMoreError" class="load-more-error"><span>{{ sections[chartType].loadMoreError }}</span><v-btn size="small" variant="text" @click="loadMoreChart">重试</v-btn></div>
          <div v-else-if="sections[chartType].hasMore" v-intersect="onChartLoadMoreIntersect" class="load-more-sentinel"><v-progress-circular v-if="sections[chartType].loadingMore" indeterminate size="22" width="2" /></div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="detailDialog" max-width="900" scrollable>
      <v-card class="dialog-card detail-card">
        <v-card-title class="dialog-title"><span>{{ selectedItem ? `${labels[selectedItem.resource_type]}详情` : '详情' }}</span><v-btn icon="mdi-close" size="small" title="关闭" variant="text" @click="detailDialog = false" /></v-card-title>
        <template v-if="detailState === 'loading'">
          <div class="detail-head"><v-skeleton-loader type="image" class="detail-cover" /><v-skeleton-loader type="heading, list-item-two-line, paragraph" /></div>
        </template>
        <v-card-text v-else-if="detailState === 'error'"><v-alert color="error" variant="tonal"><div class="error-row"><span>{{ detailError }}</span><v-btn size="small" variant="text" @click="loadDetail()">重试</v-btn></div></v-alert></v-card-text>
        <template v-else-if="detail">
          <div class="detail-head">
            <img v-if="detail.artwork_url" :src="detail.artwork_url" alt="" class="detail-cover" />
            <span v-else class="detail-cover placeholder"><v-icon :icon="icons[detail.resource_type]" size="48" /></span>
            <div class="detail-copy"><div class="detail-kind">Last.fm · {{ labels[detail.resource_type] }}</div><h2>{{ detail.name }}</h2><p v-if="detail.artist_name && detail.resource_type === 'songs'">{{ detail.artist_name }}</p><p v-if="detail.description" class="description">{{ detail.description }}</p><div class="detail-meta"><span v-for="value in detailMeta(detail)" :key="value">{{ value }}</span></div><div v-if="detail.resource_type === 'songs'" class="detail-actions"><v-btn prepend-icon="mdi-magnify" color="primary" size="small" @click="searchCurrentSong">搜索资源</v-btn></div></div>
          </div>
          <v-card-text v-if="detail.resource_type === 'songs'" class="facts">
            <dl><div><dt>歌手</dt><dd>{{ detail.artist_name || '-' }}</dd></div><div><dt>专辑</dt><dd>{{ detail.album_name || '-' }}</dd></div><div><dt>时长</dt><dd>{{ formatDuration(detail.duration_seconds) }}</dd></div><div><dt>标签</dt><dd>{{ detail.genres.join(' / ') || '-' }}</dd></div><div><dt>听众数</dt><dd>{{ formatCount(detail.listeners) }}</dd></div><div><dt>播放数</dt><dd>{{ formatCount(detail.playcount) }}</dd></div></dl>
          </v-card-text>
          <v-card-text v-else class="track-list">
            <div class="track-head"><span>#</span><span></span><span>歌曲</span><span>歌手</span><span>时长</span></div>
            <button v-for="track in detail.tracks" :key="`${track.position}:${track.id}`" class="track-row" type="button" @click="openTrackDetail(track)"><span class="rank">{{ track.position }}</span><img v-if="track.artwork_url" :src="track.artwork_url" alt="" loading="lazy" /><span v-else class="track-placeholder"><v-icon icon="mdi-music-note" size="18" /></span><strong>{{ track.name }}</strong><span>{{ track.artist_name || '-' }}</span><span>{{ formatDuration(track.duration_seconds) }}</span></button>
            <div v-if="!detail.tracks.length" class="empty">暂无歌曲</div>
          </v-card-text>
        </template>
      </v-card>
    </v-dialog>
  </section>
</template>

<style scoped>
.lastfm-page{gap:22px}.section-head,.section-head>div,.error-row,.dialog-title{align-items:center;display:flex}.section-head,.error-row,.dialog-title{justify-content:space-between}.section-head{margin-bottom:10px}.section-head>div{gap:8px}.section-head h2{font-size:16px;letter-spacing:0;margin:0}.item-list{border-top:1px solid rgba(var(--v-border-color),var(--v-border-opacity))}.list-item{align-items:center;background:transparent;border:0;border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity));color:inherit;cursor:pointer;display:grid;font:inherit;gap:12px;grid-template-columns:32px 48px minmax(0,1fr) minmax(100px,.5fr) 24px;min-height:65px;padding:8px 6px;text-align:left;width:100%}.list-item:hover{background:rgba(var(--v-theme-primary),.05)}.list-item img,.list-item .placeholder{border-radius:6px;height:48px;object-fit:cover;width:48px}.rank{color:rgba(var(--v-theme-on-surface),.56);font-variant-numeric:tabular-nums;text-align:center}.item-copy{display:flex;flex-direction:column;min-width:0}.item-copy strong,.item-copy small,.metric{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.item-copy strong{font-size:14px}.item-copy small,.metric{color:rgba(var(--v-theme-on-surface),.58);font-size:12px}.item-grid{display:grid;gap:16px;grid-template-columns:repeat(5,minmax(0,1fr))}.grid-item{background:transparent;border:0;color:inherit;cursor:pointer;font:inherit;min-width:0;padding:0;text-align:left}.grid-item>.rank{display:none}.grid-item img,.grid-item>.placeholder{aspect-ratio:1;border-radius:8px;display:flex;object-fit:cover;width:100%}.grid-item strong,.grid-item small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.grid-item strong{font-size:13px;margin-top:8px}.grid-item small{color:rgba(var(--v-theme-on-surface),.58);font-size:11px;margin-top:2px}.placeholder,.track-placeholder{align-items:center;background:rgba(var(--v-theme-on-surface),.07);color:rgba(var(--v-theme-on-surface),.45);display:flex;justify-content:center}.empty{color:rgba(var(--v-theme-on-surface),.58);padding:24px;text-align:center}.dialog-card{max-height:min(86vh,900px)}.dialog-title{border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity));font-size:17px;min-height:56px}.dialog-grid{grid-template-columns:repeat(5,minmax(0,1fr))}.detail-head{display:grid;gap:22px;grid-template-columns:150px minmax(0,1fr);padding:22px}.detail-cover{aspect-ratio:1;border-radius:8px;height:150px;object-fit:cover;width:150px}.detail-copy{min-width:0}.detail-kind{color:rgb(var(--v-theme-primary));font-size:12px;font-weight:700}.detail-copy h2{font-size:24px;line-height:31px;margin:5px 0 2px;overflow-wrap:anywhere}.detail-copy>p{font-size:14px;margin:0}.detail-copy .description{color:rgba(var(--v-theme-on-surface),.65);font-size:12px;line-height:19px;margin-top:10px;white-space:pre-line}.detail-meta{color:rgba(var(--v-theme-on-surface),.58);display:flex;flex-wrap:wrap;font-size:11px;gap:12px;margin-top:12px}.facts{border-top:1px solid rgba(var(--v-border-color),var(--v-border-opacity));padding:0 22px 20px}.facts dl{margin:0}.facts dl>div{display:grid;font-size:13px;gap:16px;grid-template-columns:110px 1fr;padding:11px 0}.facts dl>div+div{border-top:1px solid rgba(var(--v-border-color),var(--v-border-opacity))}.facts dt{color:rgba(var(--v-theme-on-surface),.58)}.facts dd{font-weight:600;margin:0}.track-list{padding:0 22px 20px}.track-head,.track-row{align-items:center;display:grid;gap:10px;grid-template-columns:34px 38px minmax(0,1.35fr) minmax(0,1fr) 54px}.track-head{border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity));color:rgba(var(--v-theme-on-surface),.5);font-size:10px;height:34px}.track-row{border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity));font-size:12px;min-height:52px}.track-row img,.track-placeholder{border-radius:5px;height:34px;object-fit:cover;width:34px}.track-row strong,.track-row>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.detail-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.track-row{background:transparent;border-left:0;border-right:0;border-top:0;color:inherit;cursor:pointer;font:inherit;padding:0;text-align:left;width:100%}.track-row:hover{background:rgba(var(--v-theme-primary),.05)}.track-row:focus-visible{outline:2px solid rgba(var(--v-theme-primary),.65);outline-offset:-2px}.load-more-sentinel{align-items:center;display:flex;height:52px;justify-content:center}.load-more-error{align-items:center;color:rgba(var(--v-theme-on-surface),.62);display:flex;font-size:12px;gap:8px;justify-content:center;min-height:52px}
@media(max-width:900px){.item-grid,.dialog-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:600px){.lastfm-page{gap:18px}.item-grid,.dialog-grid{gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}.list-item{gap:8px;grid-template-columns:24px 42px minmax(0,1fr) 20px}.list-item img,.list-item .placeholder{height:42px;width:42px}.metric{display:none}.dialog-card{height:100%;max-height:none}.detail-head{gap:14px;grid-template-columns:96px minmax(0,1fr);padding:16px}.detail-cover{height:96px;width:96px}.detail-copy h2{font-size:19px;line-height:25px}.detail-copy .description{display:none}.track-list{padding:0 12px 14px}.track-head,.track-row{grid-template-columns:28px 34px minmax(0,1fr) 50px}.track-head span:nth-child(4),.track-row>span:nth-child(4){display:none}.facts{padding:0 16px 16px}.facts dl>div{grid-template-columns:84px 1fr}}
</style>
