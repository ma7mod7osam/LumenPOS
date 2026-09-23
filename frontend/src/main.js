// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'

import './theme' // applies saved/OS theme before first paint
import './i18n' // applies saved/browser language + RTL direction before first paint
import App from './App.vue'
import SellView from './views/SellView.vue'
import HistoryView from './views/HistoryView.vue'
import CustomersView from './views/CustomersView.vue'
import HoldsView from './views/HoldsView.vue'
import RegisterView from './views/RegisterView.vue'
import InsightsView from './views/InsightsView.vue'
import SettingsView from './views/SettingsView.vue'
import CustomerDisplayView from './views/CustomerDisplayView.vue'
import './styles.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: SellView },
    { path: '/history', component: HistoryView },
    { path: '/customers', component: CustomersView },
    { path: '/holds', component: HoldsView },
    { path: '/register', component: RegisterView },
    { path: '/insights', component: InsightsView },
    { path: '/settings', component: SettingsView },
    // Second-screen customer-facing display, chrome-free, no bootstrap.
    { path: '/display', component: CustomerDisplayView },
  ],
})

createApp(App).use(createPinia()).use(router).mount('#app')
