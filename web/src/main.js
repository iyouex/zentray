import { createApp } from 'vue'
import ArcoVue from '@arco-design/web-vue'
import '@arco-design/web-vue/dist/arco.css'
import App from './App.vue'
import router from './router'
import { vStagger } from './directives/stagger'
import './styles.css'
import './themes/neo.css'
import './themes/aurora.css'

const app = createApp(App)
app.use(ArcoVue)
app.directive('stagger', vStagger)
app.use(router)
app.mount('#app')
