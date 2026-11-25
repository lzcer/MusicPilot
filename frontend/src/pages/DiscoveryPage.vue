<script setup lang="ts">
import { useWorkspace } from '../workspace'
import DiscoveryPage from '../components/DiscoveryPage.vue'

const {
  discoveryPlaylistAddingId,
  startDiscoverySongSearch,
  startDiscoveryAlbumSearch,
  addDiscoveryPlaylist
} = useWorkspace()
</script>

<template>
  <DiscoveryPage
    :playlist-adding-id="discoveryPlaylistAddingId"
    @search-song="startDiscoverySongSearch"
    @search-album="startDiscoveryAlbumSearch"
    @add-playlist="addDiscoveryPlaylist"
  />
</template>
