<script setup lang="ts">
import type { HTMLAttributes } from "vue"
import { cn } from "@/lib/utils"

const props = defineProps<{
  class?: HTMLAttributes["class"]
}>()
</script>

<template>
  <div data-slot="table-container" class="relative w-full overflow-x-auto bg-white rounded-lg shadow-sm border border-border">
    <table data-slot="table" :class="cn('w-full caption-bottom text-sm min-w-[600px]', props.class)">
      <slot />
    </table>
  </div>
</template>
