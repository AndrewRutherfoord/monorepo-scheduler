<script setup lang="ts">
import { RouterView, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth';

const auth = useAuthStore()
const router = useRouter()

const handleLogout = () => {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <div class="max-w-6xl mx-auto px-4 py-6">
      <header class="flex justify-between items-center mb-6 bg-white rounded-lg shadow-sm p-4">
        <h1 class="text-2xl font-bold text-gray-900">Monorepo Scheduler</h1>
        <div class="flex items-center gap-3">
          <span class="text-sm text-gray-600">{{ auth.username }}</span>
          <button 
            @click="handleLogout"
            class="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded text-sm transition-colors"
          >
            Logout
          </button>
        </div>
      </header>
      <main>
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style>

body {
  font-family: system-ui, sans-serif;
  color: #333;
}
</style>
