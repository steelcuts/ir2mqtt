import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import './shepherd-theme.css'
import '@mdi/font/css/materialdesignicons.css'
import App from './App.vue'

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
app.mount('#app')