import { createApp } from 'vue'
import { createVuetify } from 'vuetify'

import { Intersect, Ripple } from 'vuetify/directives'
import 'vuetify/styles'
import { icons } from './plugins/icons'
import { createPinia } from 'pinia'
import router from './router'
import './style.css'
import App from './App.vue'

const vuetify = createVuetify({
  icons,
  directives: {
    Intersect,
    Ripple
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
    VAutocomplete: { variant: 'outlined', density: 'compact' },
    VSelect: { variant: 'outlined', density: 'compact' }
  }
})

createApp(App).use(createPinia()).use(vuetify).use(router).mount('#app')
