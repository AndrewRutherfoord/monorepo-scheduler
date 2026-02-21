<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import useJobsApi from '@/composables/api/useJobsApi'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const route = useRoute()
const router = useRouter()
const { getJob, getJobRuns, triggerJob: apiTriggerJob } = useJobsApi()

const job = ref<any>(null)
const runs = ref<any[]>([])
const loading = ref(true)
const flash = ref<{ kind: string; message: string } | null>(null)

const jobId = route.params.jobId as string

async function fetchData() {
  try {
    const [jobRes, runsRes] = await Promise.all([
      getJob(jobId),
      getJobRuns(jobId)
    ])
    
    if (jobRes.error) {
      router.push('/dashboard')
      return
    }
    
    job.value = jobRes.data
    runs.value = runsRes.data || []
  } catch (error) {
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
}

async function triggerJob() {
  flash.value = null
  try {
    const res = await apiTriggerJob(jobId)
    if (res.error) {
      flash.value = { kind: 'err', message: `Failed to trigger ${jobId}` }
      return
    }
    flash.value = { kind: 'ok', message: `Triggered ${jobId}` }
    // Refresh runs after a short delay
    setTimeout(fetchData, 1000)
  } catch {
    flash.value = { kind: 'err', message: `Failed to trigger ${jobId}` }
  }
}

function formatDate(dateString: string) {
  return new Date(dateString).toLocaleString()
}

function getStatusClass(status: string) {
  switch (status?.toLowerCase()) {
    case 'success':
    case 'completed':
      return 'text-green-600 bg-green-50 px-2 py-1 rounded text-xs'
    case 'failed':
    case 'error':
      return 'text-red-600 bg-red-50 px-2 py-1 rounded text-xs'
    case 'running':
      return 'text-blue-600 bg-blue-50 px-2 py-1 rounded text-xs'
    default:
      return 'text-gray-600 bg-gray-50 px-2 py-1 rounded text-xs'
  }
}

onMounted(fetchData)
</script>

<template>
  <div v-if="loading" class="text-center py-8 text-gray-500">Loading...</div>
  
  <div v-else-if="job" class="space-y-6">
    <!-- Job Header -->
    <div class="bg-white rounded-lg shadow-sm p-6">
      <div class="flex justify-between items-start mb-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">{{ job.job_id }}</h1>
          <p class="text-gray-600 mt-1">Target: {{ job.target_name }}</p>
        </div>
        <div class="flex gap-3">
          <button 
            @click="router.push('/dashboard')"
            class="bg-gray-500 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors"
          >
            Back to Dashboard
          </button>
          <button 
            @click="triggerJob"
            class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm transition-colors"
          >
            Trigger Job
          </button>
        </div>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <span class="text-sm text-gray-500">Schedule</span>
          <p class="font-mono text-sm">{{ job.cron || 'API only' }}</p>
        </div>
        <div>
          <span class="text-sm text-gray-500">Total Runs</span>
          <p class="font-semibold">{{ runs.length }}</p>
        </div>
        <div>
          <span class="text-sm text-gray-500">Last Run</span>
          <p class="text-sm">{{ runs[0] ? formatDate(runs[0].created_at) : 'Never' }}</p>
        </div>
      </div>
    </div>

    <!-- Flash Messages -->
    <div v-if="flash" :class="flash.kind === 'ok' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'" class="px-4 py-3 rounded">
      {{ flash.message }}
    </div>

    <!-- Job Runs -->
    <div class="bg-white rounded-lg shadow-sm">
      <div class="p-6 border-b border-gray-200">
        <h2 class="text-lg font-semibold text-gray-900">Recent Runs</h2>
      </div>
      
      <div v-if="runs.length" class="p-6">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Run ID</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="run in runs" :key="run.run_id">
              <TableCell class="font-medium font-mono text-sm">{{ run.run_id }}</TableCell>
              <TableCell>
                <span :class="getStatusClass(run.status)">{{ run.status }}</span>
              </TableCell>
              <TableCell class="text-sm">{{ formatDate(run.created_at) }}</TableCell>
              <TableCell class="text-sm">
                {{ run.duration ? `${Math.round(run.duration)}ms` : '-' }}
              </TableCell>
              <TableCell>
                <button 
                  @click="router.push(`/jobs/${jobId}/runs/${run.run_id}`)"
                  class="text-blue-600 hover:text-blue-800 text-sm"
                >
                  View Details
                </button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
      
      <div v-else class="p-6 text-center text-gray-500">
        No runs found for this job.
      </div>
    </div>
  </div>
</template>