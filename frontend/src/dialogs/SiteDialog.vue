<script setup lang="ts">
import { useWorkspace } from '../workspace'

const { siteDialog, siteTesting, editingSiteId, siteForm, saveSite, testSite } = useWorkspace()
</script>

<template>
  <v-dialog v-model="siteDialog" max-width="820">
    <v-card :title="editingSiteId ? '编辑站点' : '新增站点'">
      <v-card-text class="dialog-stack">
        <v-text-field v-model="siteForm.name" label="站点名称" />
        <v-text-field v-model="siteForm.base_url" label="站点地址" />
        <v-tabs v-model="siteForm.auth_type" color="primary" grow>
          <v-tab prepend-icon="mdi-cookie" value="cookie">Cookie</v-tab>
          <v-tab prepend-icon="mdi-api" value="api_key">API Key</v-tab>
        </v-tabs>
        <v-window v-model="siteForm.auth_type">
          <v-window-item value="cookie">
            <v-textarea
              v-model="siteForm.cookie"
              class="mt-3"
              label="Cookie"
              rows="3"
              @update:focused="
                (focused) => {
                  if (!focused) siteForm.cookie = siteForm.cookie.trim()
                }
              "
            />
          </v-window-item>
          <v-window-item value="api_key">
            <v-text-field
              v-model="siteForm.api_key"
              autocomplete="new-password"
              class="mt-3"
              hint="M-Team 可在用户控制面板的实验室页面获取 API Key"
              label="API Key"
              persistent-hint
              type="password"
            />
          </v-window-item>
        </v-window>
        <v-text-field v-model="siteForm.user_agent" label="User-Agent" />
        <v-text-field
          v-model.number="siteForm.priority"
          label="优先级（数字越小越靠前）"
          type="number"
          min="0"
        />
        <v-text-field v-model.number="siteForm.max_concurrency" label="最大并发" type="number" />
        <v-switch
          v-model="siteForm.enabled"
          color="primary"
          density="compact"
          hide-details
          inset
          label="启用站点"
        />
        <v-switch
          v-model="siteForm.use_proxy"
          color="primary"
          density="compact"
          hide-details
          inset
          label="使用系统代理"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="siteDialog = false">取消</v-btn>
        <v-btn :loading="siteTesting" variant="tonal" @click="testSite">测试</v-btn>
        <v-btn color="primary" @click="saveSite">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
