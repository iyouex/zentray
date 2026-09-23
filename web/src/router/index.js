import { createRouter, createWebHashHistory } from 'vue-router'
import TaskList from '@/views/TaskList.vue'
import TaskForm from '@/views/TaskForm.vue'
import Settings from '@/views/Settings.vue'
import Home from '@/views/Home.vue'
import Reminder from '@/views/Reminder.vue'
import QuickAdd from '@/views/QuickAdd.vue'
import SetupWizard from '@/views/SetupWizard.vue'
import History from '@/views/History.vue'

const routes = [
  { path: '/', name: 'home', component: Home },
  { path: '/tasks', name: 'tasks', component: TaskList },
  { path: '/tasks/new', name: 'task-new', component: TaskForm },
  { path: '/tasks/:id/edit', name: 'task-edit', component: TaskForm, props: true },
  { path: '/history', name: 'history', component: History },
  { path: '/settings', name: 'settings', component: Settings },
  { path: '/reminder', name: 'reminder', component: Reminder },
  { path: '/quick-add', name: 'quick-add', component: QuickAdd },
  { path: '/setup', name: 'setup', component: SetupWizard },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
