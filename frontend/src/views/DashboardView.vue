<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import useJobsApi from '@/composables/api/useJobsApi'
import type { components } from '@/types/schema'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const router = useRouter()
const auth = useAuthStore()
const { getJobs, triggerJob: apiTriggerJob } = useJobsApi()

const jobs = ref<unknown>([])
const flash = ref<{ kind: string; message: string } | null>(null)
const loading = ref(true)

async function fetchJobs() {
  const res = await getJobs()
  jobs.value = res.data
  loading.value = false
}

async function triggerJob(jobId: string) {
  flash.value = null
  try {
    const res = await apiTriggerJob(jobId)
    if (res.error) {
      flash.value = { kind: 'err', message: `Failed to trigger ${jobId}` }
      return
    }
    // flash.value = { kind: 'ok', message: `Triggered ${jobId}` }
  } catch (err) {
    flash.value = { kind: 'err', message: `Failed to trigger ${jobId}` }
  }
}

onMounted(fetchJobs)
</script>

<template>
    <div v-if="loading" class="text-center py-8 text-gray-500">Loading...</div>

    <div v-else-if="jobs.length">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Job</TableHead>
            <TableHead>Target</TableHead>
            <TableHead>Schedule</TableHead>
            <TableHead></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="job in jobs" :key="job.job_id">
            <TableCell class="font-medium">
              <button 
                @click="router.push(`/jobs/${job.job_id}`)"
                class="text-blue-600 hover:text-blue-800 hover:underline"
              >
                {{ job.job_id }}
              </button>
            </TableCell>
            <TableCell>{{ job.target_name }}</TableCell>
            <TableCell>
              <span class="font-mono text-sm text-muted-foreground">
                {{ job.cron || 'API only' }}
              </span>
            </TableCell>
            <TableCell>
              <button 
                @click="triggerJob(job.job_id)" 
                class="bg-gray-600 hover:bg-gray-700 text-white py-2 px-4 rounded text-sm transition-colors"
              >
                Trigger
              </button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <p v-else class="text-center py-8 text-gray-500">No jobs available.</p>
</template>


