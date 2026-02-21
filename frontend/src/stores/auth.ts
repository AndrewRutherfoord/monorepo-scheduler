import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const COOKIE_NAME = 'scheduler_auth'
const COOKIE_DAYS = 30

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : null
}

function setCookie(name: string, value: string, days: number) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString()
  document.cookie = `${name}=${encodeURIComponent(value)};expires=${expires};path=/;SameSite=Strict`
}

function deleteCookie(name: string) {
  document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;SameSite=Strict`
}

export const useAuthStore = defineStore('auth', () => {
  const savedToken = getCookie(COOKIE_NAME)

  const token = ref<string>(savedToken ?? '')
  const username = ref<string>('')

  if (savedToken) {
    try {
      username.value = atob(savedToken).split(':')[0]
    } catch {
      token.value = ''
    }
  }

  const isAuthenticated = computed(() => token.value !== '')

  function getAuthHeader(): string {
    return `Basic ${token.value}`
  }

  function login(user: string, pass: string) {
    token.value = btoa(`${user}:${pass}`)
    username.value = user
    setCookie(COOKIE_NAME, token.value, COOKIE_DAYS)
  }

  function logout() {
    token.value = ''
    username.value = ''
    deleteCookie(COOKIE_NAME)
  }

  return { username, isAuthenticated, getAuthHeader, login, logout }
})
