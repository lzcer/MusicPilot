<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useWorkspace } from '../workspace'
const DirectoryMonitorDialog = defineAsyncComponent(() => import('./DirectoryMonitorDialog.vue'))
const SearchDialog = defineAsyncComponent(() => import('./SearchDialog.vue'))
const NoMetadataDialog = defineAsyncComponent(() => import('./NoMetadataDialog.vue'))
const SiteConfirmDialog = defineAsyncComponent(() => import('./SiteConfirmDialog.vue'))
const DownloadConfirmDialog = defineAsyncComponent(() => import('./DownloadConfirmDialog.vue'))
const MusicPlatformDialog = defineAsyncComponent(() => import('./MusicPlatformDialog.vue'))
const PlaylistImportDialog = defineAsyncComponent(() => import('./PlaylistImportDialog.vue'))
const PlaylistTracksDialog = defineAsyncComponent(() => import('./PlaylistTracksDialog.vue'))
const LibraryPlaylistDialog = defineAsyncComponent(() => import('./LibraryPlaylistDialog.vue'))
const LibraryDeleteDialog = defineAsyncComponent(() => import('./LibraryDeleteDialog.vue'))
const PlaylistAddDialog = defineAsyncComponent(() => import('./PlaylistAddDialog.vue'))
const PlaylistTrackEditDialog = defineAsyncComponent(() => import('./PlaylistTrackEditDialog.vue'))
const PlaylistLibrarySyncDialog = defineAsyncComponent(
  () => import('./PlaylistLibrarySyncDialog.vue')
)
const SiteDialog = defineAsyncComponent(() => import('./SiteDialog.vue'))
const DownloaderDialog = defineAsyncComponent(() => import('./DownloaderDialog.vue'))
const MediaServerDialog = defineAsyncComponent(() => import('./MediaServerDialog.vue'))
const NotifierDialog = defineAsyncComponent(() => import('./NotifierDialog.vue'))
const DeleteDialog = defineAsyncComponent(() => import('./DeleteDialog.vue'))
const DatabaseImportStartDialog = defineAsyncComponent(
  () => import('./DatabaseImportStartDialog.vue')
)
const DatabaseImportFileDialog = defineAsyncComponent(
  () => import('./DatabaseImportFileDialog.vue')
)
const SystemTasksDialog = defineAsyncComponent(() => import('./SystemTasksDialog.vue'))
const DownloadItemsDialog = defineAsyncComponent(() => import('./DownloadItemsDialog.vue'))
const DownloadDeleteDialog = defineAsyncComponent(() => import('./DownloadDeleteDialog.vue'))
const MediaDeleteDialog = defineAsyncComponent(() => import('./MediaDeleteDialog.vue'))
const MediaDeleteAllConfirmDialog = defineAsyncComponent(
  () => import('./MediaDeleteAllConfirmDialog.vue')
)
const MediaClearDialog = defineAsyncComponent(() => import('./MediaClearDialog.vue'))
const MediaClearConfirmDialog = defineAsyncComponent(() => import('./MediaClearConfirmDialog.vue'))
const MediaRetryDialog = defineAsyncComponent(() => import('./MediaRetryDialog.vue'))
const MediaManualDialog = defineAsyncComponent(() => import('./MediaManualDialog.vue'))
const MediaMetadataSearchDialog = defineAsyncComponent(
  () => import('./MediaMetadataSearchDialog.vue')
)
const FileDetailDialog = defineAsyncComponent(() => import('./FileDetailDialog.vue'))
const FileOrganizeDialog = defineAsyncComponent(() => import('./FileOrganizeDialog.vue'))
const FileDeleteDialog = defineAsyncComponent(() => import('./FileDeleteDialog.vue'))
const ArtistEditDialog = defineAsyncComponent(() => import('./ArtistEditDialog.vue'))
const ArtistAliasDialog = defineAsyncComponent(() => import('./ArtistAliasDialog.vue'))
const ArtistMergeDialog = defineAsyncComponent(() => import('./ArtistMergeDialog.vue'))
const ClearArtistDialog = defineAsyncComponent(() => import('./ClearArtistDialog.vue'))
const {
  directoryMonitorDialog,
  searchDialog,
  noMetadataDialog,
  siteConfirmDialog,
  pendingDownload,
  musicPlatformDialog,
  playlistImportDialog,
  playlistTracksDialog,
  libraryPlaylistDialog,
  libraryDeleteDialog,
  playlistAddDialog,
  playlistTrackEditDialog,
  playlistLibrarySyncDialog,
  siteDialog,
  downloaderDialog,
  mediaServerDialog,
  notifierDialog,
  deleteDialog,
  databaseImportStartDialog,
  databaseImportFileDialog,
  systemTasksDialog,
  downloadItemsDialog,
  downloadDeleteDialog,
  mediaDeleteDialog,
  mediaDeleteAllConfirmDialog,
  mediaClearDialog,
  mediaClearConfirmDialog,
  mediaRetryDialog,
  mediaManualDialog,
  mediaMetadataSearchDialog,
  fileDetailDialog,
  fileOrganizeDialog,
  fileDeleteDialog,
  artistEditDialog,
  artistAliasDialog,
  artistMergeDialog,
  clearArtistDialog
} = useWorkspace()
</script>

<template>
  <DirectoryMonitorDialog v-if="directoryMonitorDialog" />
  <SearchDialog v-if="searchDialog" />
  <NoMetadataDialog v-if="noMetadataDialog" />
  <SiteConfirmDialog v-if="siteConfirmDialog" />
  <DownloadConfirmDialog v-if="Boolean(pendingDownload)" />
  <MusicPlatformDialog v-if="musicPlatformDialog" />
  <PlaylistImportDialog v-if="playlistImportDialog" />
  <PlaylistTracksDialog v-if="playlistTracksDialog" />
  <LibraryPlaylistDialog v-if="libraryPlaylistDialog" />
  <LibraryDeleteDialog v-if="libraryDeleteDialog" />
  <PlaylistAddDialog v-if="playlistAddDialog" />
  <PlaylistTrackEditDialog v-if="playlistTrackEditDialog" />
  <PlaylistLibrarySyncDialog v-if="playlistLibrarySyncDialog" />
  <SiteDialog v-if="siteDialog" />
  <DownloaderDialog v-if="downloaderDialog" />
  <MediaServerDialog v-if="mediaServerDialog" />
  <NotifierDialog v-if="notifierDialog" />
  <DeleteDialog v-if="deleteDialog" />
  <DatabaseImportStartDialog v-if="databaseImportStartDialog" />
  <DatabaseImportFileDialog v-if="databaseImportFileDialog" />
  <SystemTasksDialog v-if="systemTasksDialog" />
  <DownloadItemsDialog v-if="downloadItemsDialog" />
  <DownloadDeleteDialog v-if="downloadDeleteDialog" />
  <MediaDeleteDialog v-if="mediaDeleteDialog" />
  <MediaDeleteAllConfirmDialog v-if="mediaDeleteAllConfirmDialog" />
  <MediaClearDialog v-if="mediaClearDialog" />
  <MediaClearConfirmDialog v-if="mediaClearConfirmDialog" />
  <MediaRetryDialog v-if="mediaRetryDialog" />
  <MediaManualDialog v-if="mediaManualDialog" />
  <MediaMetadataSearchDialog v-if="mediaMetadataSearchDialog" />
  <FileDetailDialog v-if="fileDetailDialog" />
  <FileOrganizeDialog v-if="fileOrganizeDialog" />
  <FileDeleteDialog v-if="fileDeleteDialog" />
  <ArtistEditDialog v-if="artistEditDialog" />
  <ArtistAliasDialog v-if="artistAliasDialog" />
  <ArtistMergeDialog v-if="artistMergeDialog" />
  <ClearArtistDialog v-if="clearArtistDialog" />
</template>
