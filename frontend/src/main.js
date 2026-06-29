import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'

import './theme' // applies saved/OS theme before first paint
import './i18n' // applies saved/browser language + RTL direction before first paint
import App from './App.vue'
import SellView from './views/SellView.vue'
import HistoryView from './views/HistoryView.vue'
import CustomersView from './views/CustomersView.vue'
import RegisterView from './views/RegisterView.vue'
import SettingsView from './views/SettingsView.vue'
import './styles.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: SellView },
    { path: '/history', component: HistoryView },
    { path: '/customers', component: CustomersView },
    { path: '/register', component: RegisterView },
    { path: '/settings', component: SettingsView },
  ],
})

createApp(App).use(createPinia()).use(router).mount('#app')
