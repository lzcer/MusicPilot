import { createApp } from 'vue'
import { createVuetify } from 'vuetify'
import {
  VApp,
  VAppBar,
  VAppBarNavIcon,
  VBtn,
  VCard,
  VCardActions,
  VCardText,
  VCardTitle,
  VCheckbox,
  VChip,
  VDialog,
  VForm,
  VIcon,
  VList,
  VListItem,
  VMain,
  VNavigationDrawer,
  VPagination,
  VProgressCircular,
  VProgressLinear,
  VSelect,
  VSnackbar,
  VSpacer,
  VSwitch,
  VTab,
  VTable,
  VTabs,
  VTextField,
  VTextarea,
  VToolbarTitle,
  VWindow,
  VWindowItem,
} from 'vuetify/components'
import { Ripple } from 'vuetify/directives'
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import './style.css'
import App from './App.vue'

const vuetify = createVuetify({
  components: {
    VApp,
    VAppBar,
    VAppBarNavIcon,
    VBtn,
    VCard,
    VCardActions,
    VCardText,
    VCardTitle,
    VCheckbox,
    VChip,
    VDialog,
    VForm,
    VIcon,
    VList,
    VListItem,
    VMain,
    VNavigationDrawer,
    VPagination,
    VProgressCircular,
    VProgressLinear,
    VSelect,
    VSnackbar,
    VSpacer,
    VSwitch,
    VTab,
    VTable,
    VTabs,
    VTextField,
    VTextarea,
    VToolbarTitle,
    VWindow,
    VWindowItem,
  },
  directives: {
    Ripple,
  },
  theme: {
    defaultTheme: 'musicpilot',
    themes: {
      musicpilot: {
        dark: false,
        colors: {
          primary: '#2563eb',
          secondary: '#475569',
          background: '#f6f8fb',
          surface: '#ffffff',
          error: '#dc2626',
          warning: '#d97706',
          success: '#059669',
          info: '#0284c7'
        }
      }
    }
  },
  defaults: {
    VBtn: { rounded: 'lg' },
    VCard: { rounded: 'lg', elevation: 0 },
    VTextField: { variant: 'outlined', density: 'compact' },
    VTextarea: { variant: 'outlined', density: 'compact' },
    VSelect: { variant: 'outlined', density: 'compact' }
  }
})

createApp(App).use(vuetify).mount('#app')
