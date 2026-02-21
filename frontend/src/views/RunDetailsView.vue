<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import useJobsApi from '@/composables/api/useJobsApi'

const route = useRoute()
const router = useRouter()
const { getJobRun, getJobRunLogs } = useJobsApi()

const run = ref<any>(null)
const logs = ref<string>('')
const loading = ref(true)
const logsLoading = ref(false)

const jobId = route.params.jobId as string
const runId = route.params.runId as string

async function fetchRunDetails() {
  try {
    const res = await getJobRun(jobId, runId)
    
    if (res.error) {
      router.push(`/jobs/${jobId}`)
      return
    }
    
    run.value = res.data
    await fetchLogs()
  } catch (error) {
    router.push(`/jobs/${jobId}`)
  } finally {
    loading.value = false
  }
}

async function fetchLogs() {
  logsLoading.value = true
  try {
    const res = await getJobRunLogs(jobId, runId)
    logs.value = res.data || 'No logs available'
  } catch (error) {
    logs.value = 'Failed to load logs'
  } finally {
    logsLoading.value = false
  }
}

function formatDate(dateString: string) {
  return new Date(dateString).toLocaleString()
}

function getStatusClass(status: string) {
  switch (status?.toLowerCase()) {
    case 'success':
    case 'completed':
      return 'text-green-600 bg-green-50 px-3 py-1 rounded-full text-sm font-medium'
    case 'failed':
    case 'error':
      return 'text-red-600 bg-red-50 px-3 py-1 rounded-full text-sm font-medium'
    case 'running':
      return 'text-blue-600 bg-blue-50 px-3 py-1 rounded-full text-sm font-medium'
    default:
      return 'text-gray-600 bg-gray-50 px-3 py-1 rounded-full text-sm font-medium'
  }
}

onMounted(fetchRunDetails)
</script>

<template>
  <div v-if="loading" class="text-center py-8 text-gray-500">Loading...</div>
  
  <div v-else-if="run" class="space-y-6">
    <!-- Run Header -->
    <div class="bg-white rounded-lg shadow-sm p-6">
      <div class="flex justify-between items-start mb-6">
        <div>
          <div class="flex items-center gap-3 mb-2">
            <h1 class="text-2xl font-bold text-gray-900">Run Details</h1>
            <span :class="getStatusClass(run.status)">{{ run.status }}</span>
          </div>
          <p class="text-gray-600">{{ jobId }} → {{ run.run_id }}</p>
        </div>
        <div class="flex gap-3">
          <button 
            @click="router.push(`/jobs/${jobId}`)"
            class="bg-gray-500 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors"
          >
            Back to Job
          </button>
          <button 
            @click="fetchLogs"
            class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm transition-colors"
          >
            Refresh Logs
          </button>
        </div>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div>
          <span class="text-sm text-gray-500">Run ID</span>
          <p class="font-mono text-sm font-medium">{{ run.run_id }}</p>
        </div>
        <div>
          <span class="text-sm text-gray-500">Started</span>
          <p class="text-sm">{{ formatDate(run.created_at) }}</p>
        </div>
        <div>
          <span class="text-sm text-gray-500">Finished</span>
          <p class="text-sm">{{ run.finished_at ? formatDate(run.finished_at) : 'Still running' }}</p>
        </div>
        <div>
          <span class="text-sm text-gray-500">Duration</span>
          <p class="text-sm">{{ run.duration ? `${Math.round(run.duration)}ms` : 'N/A' }}</p>
        </div>
      </div>

      <div v-if="run.error" class="mt-6 p-4 bg-red-50 border border-red-200 rounded-lg">
        <h3 class="text-sm font-medium text-red-800 mb-2">Error</h3>
        <pre class="text-sm text-red-700 whitespace-pre-wrap">{{ run.error }}</pre>
      </div>

      <div v-if="run.result" class="mt-6 p-4 bg-green-50 border border-green-200 rounded-lg">
        <h3 class="text-sm font-medium text-green-800 mb-2">Result</h3>
        <pre class="text-sm text-green-700 whitespace-pre-wrap">{{ run.result }}</pre>
      </div>
    </div>

    <!-- Logs Section -->
    <div class="bg-white rounded-lg shadow-sm">
      <div class="flex justify-between items-center p-6 border-b border-gray-200">
        <h2 class="text-lg font-semibold text-gray-900">Logs</h2>
        <div v-if="logsLoading" class="text-sm text-gray-500">Loading...</div>
      </div>
      
      <div class="p-6">
        <div class="bg-gray-900 rounded-lg p-4 overflow-auto max-h-96">
          <pre 
            class="text-green-400 text-sm font-mono whitespace-pre-wrap"
            v-if="!logsLoading"
          >{{ logs }}</pre>
          <div v-else class="text-gray-400 text-sm">Loading logs...</div>
        </div>
      </div>
    </div>
  </div>
</template>