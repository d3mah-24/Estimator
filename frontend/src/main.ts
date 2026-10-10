import { createApp } from 'vue'
import router from './router'
import App from './App.vue'
import { i18n } from './i18n'
import './index.css'

import { Button, setConfig, frappeRequest, resourcesPlugin } from 'frappe-ui'

let app = createApp(App)
setConfig('resourceFetcher', frappeRequest)

app.use(router)
app.use(resourcesPlugin)
app.use(i18n)

app.component('Button', Button)
app.mount('#app')
