import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'TenderList',
    component: () => import('@/pages/TenderList.vue'),
  },
  {
    path: '/tender/:name',
    name: 'TenderReview',
    component: () => import('@/pages/TenderReview.vue'),
    props: true,
  },
]

const router = createRouter({
  history: createWebHistory('/estimator'),
  routes,
})

export default router
