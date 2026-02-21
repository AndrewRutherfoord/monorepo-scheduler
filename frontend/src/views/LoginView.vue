<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const user = ref('')
const pass = ref('')
const error = ref('')

async function handleLogin() {
  error.value = ''
  const header = 'Basic ' + btoa(`${user.value}:${pass.value}`)
  try {
    const res = await fetch('/api/jobs', {
      headers: { Authorization: header },
    })
    if (res.status === 401) {
      error.value = 'Invalid credentials'
      return
    }
    if (!res.ok) {
      error.value = 'Server error'
      return
    }
    auth.login(user.value, pass.value)
    router.push('/')
  } catch {
    error.value = 'Cannot reach server'
  }
}
</script>

<template>
  <div class="login-wrapper">
    <form class="login-form" @submit.prevent="handleLogin">
      <h1>Scheduler</h1>
      <div v-if="error" class="flash flash-err">{{ error }}</div>
      <label>
        Username
        <input v-model="user" type="text" autocomplete="username" required />
      </label>
      <label>
        Password
        <input v-model="pass" type="password" autocomplete="current-password" required />
      </label>
      <button type="submit">Sign in</button>
    </form>
  </div>
</template>

<style scoped>
.login-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
}
.login-form {
  background: #fff;
  padding: 2rem;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 360px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.login-form h1 {
  margin-bottom: 0.5rem;
}
label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.9rem;
  color: #555;
}
input {
  padding: 0.5rem 0.75rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 1rem;
}
</style>
