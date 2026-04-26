<script setup lang="ts">
import { computed } from 'vue';
import type { IRCode, ReceivedCode } from '../types';
import { getProtocolColor, getCodeFields } from '../utils';

const props = defineProps({
  code: {
    type: Object as () => IRCode | ReceivedCode | null | undefined,
    required: true
  },
  showProtocol: {
    type: Boolean,
    default: false
  }
});

const fields = computed(() => getCodeFields(props.code));
const protoColor = computed(() => getProtocolColor(props.code?.protocol));
</script>

<template>
  <div
    v-if="code"
    class="flex flex-col gap-1 w-full"
  >
    <div
      v-if="showProtocol"
      class="flex items-center gap-2 mb-1 w-full"
    >
      <span
        class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border bg-gray-800 font-mono"
        :class="protoColor"
      >{{ code.protocol || '?' }}</span>
      <slot name="header-extra" />
    </div>
    <div class="flex flex-wrap gap-x-3 gap-y-0.5">
      <span
        v-for="field in fields"
        :key="field.label"
        class="text-[10px] font-mono"
      >
        <span class="text-gray-500">{{ field.label }}:</span>
        <span class="text-gray-300 ml-0.5">{{ field.value }}</span>
      </span>
    </div>
  </div>
</template>