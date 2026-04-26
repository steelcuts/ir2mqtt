<script setup lang="ts">
import { Device } from '../stores/devices';
import { AutomationAction } from '../stores/automations';
import { useI18n } from '../i18n';

const props = defineProps({
  actions: {
    type: Array as () => AutomationAction[],
    required: true
  },
  appMode: {
    type: String,
    required: true
  },
  devices: {
    type: Array as () => Device[],
    required: true
  },
  draggingItem: {
    type: Object,
    default: null
  },
  dragOverItem: {
    type: Object,
    default: null
  }
});

const emit = defineEmits(['add-action', 'remove-action', 'action-device-change', 'drag-start', 'drop', 'drag-end', 'drag-over']);

const getButtonsForDevice = (devId: string) => {
    const dev = props.devices.find(d => d.id === devId);
    return dev ? dev.buttons : [];
};

const { t } = useI18n();

</script>

<template>
  <div class="space-y-2">
    <div 
      v-for="(action, idx) in actions" 
      :key="idx" 
      class="flex items-center gap-2 bg-gray-900 p-2 rounded border border-gray-700 cursor-move transition-all duration-200"
      :class="{
        'opacity-40': draggingItem?.type === 'action' && draggingItem?.index === idx,
        'border-blue-500': dragOverItem?.type === 'action' && dragOverItem?.index === idx && draggingItem?.index !== idx,
        'border-t-4 border-t-blue-500': dragOverItem?.type === 'action' && dragOverItem?.index === idx && draggingItem?.index > idx,
        'border-b-4 border-b-blue-500': dragOverItem?.type === 'action' && dragOverItem?.index === idx && draggingItem?.index < idx,
      }"
      draggable="true"
      @dragstart="emit('drag-start', $event, idx, 'action')"
      @dragover.prevent="emit('drag-over', idx, 'action')"
      @drop="emit('drop', $event, idx, 'action')"
      @dragend="emit('drag-end')"
    >
      <div class="text-gray-500 font-mono text-xs w-6 text-center">
        {{ idx + 1 }}
      </div>
        
      <template v-if="action.type === 'delay'">
        <div class="flex-grow flex items-center gap-2">
          <i class="mdi mdi-timer-sand text-blue-400" />
          <span class="text-sm font-bold">{{ t('actionList.delay') }}</span>
          <input
            v-model.number="action.delay_ms"
            type="number"
            class="w-20 rounded p-1 text-sm bg-gray-800 border-gray-600 text-center"
          >
          <span class="text-xs text-gray-500">ms</span>
        </div>
      </template>

      <template v-else-if="action.type === 'ir_send'">
        <div class="flex-grow grid grid-cols-2 gap-2">
          <div class="flex items-center gap-2 col-span-2 mb-1">
            <i class="mdi mdi-remote text-green-400" />
            <span class="text-sm font-bold">{{ t('actionList.sendIr') }}</span>
          </div>
          <select
            v-model="action.device_id"
            class="rounded p-1 text-xs bg-gray-800 border-gray-600"
            @change="emit('action-device-change', action)"
          >
            <option
              v-for="dev in props.devices"
              :key="dev.id"
              :value="dev.id"
            >
              {{ dev.name }}
            </option>
          </select>
          <select
            v-model="action.button_id"
            class="rounded p-1 text-xs bg-gray-800 border-gray-600"
          >
            <option
              v-for="btn in getButtonsForDevice(action.device_id || '')"
              :key="btn.id"
              :value="btn.id"
            >
              {{ btn.name }}
            </option>
          </select>
        </div>
      </template>

      <template v-else-if="action.type === 'event'">
        <!-- HA Mode Display -->
        <div
          v-if="props.appMode === 'home_assistant'"
          class="flex-grow flex items-center gap-2"
        >
          <i class="mdi mdi-home-assistant text-indigo-400" />
          <span class="text-sm font-bold">{{ t('actionList.fireHaEvent') }}</span>
          <input
            v-model="action.event_name"
            type="text"
            placeholder="event_name"
            class="w-full rounded p-1 text-sm bg-gray-800 border-gray-600"
          >
        </div>
        <!-- Standalone Mode Display -->
        <div
          v-else
          class="flex-grow flex items-center gap-2"
        >
          <i class="mdi mdi-lightning-bolt text-yellow-400" />
          <span class="text-sm font-bold">{{ t('actionList.fireEvent') }}</span>
          <input
            v-model="action.event_name"
            type="text"
            placeholder="event_name"
            class="w-full rounded p-1 text-sm bg-gray-800 border-gray-600"
          >
        </div>
      </template>

      <button
        class="text-gray-500 hover:text-red-400 p-1"
        @click="emit('remove-action', idx)"
      >
        <i class="mdi mdi-close" />
      </button>
    </div>

    <div
      class="flex gap-2 mt-4 justify-center"
      data-tour-id="action-buttons"
    >
      <button
        class="btn btn-sm btn-secondary border-dashed"
        @click="emit('add-action', 'ir_send')"
      >
        <i class="mdi mdi-remote" /> {{ t('actionList.addCommand') }}
      </button>
      <button
        class="btn btn-sm btn-secondary border-dashed"
        @click="emit('add-action', 'delay')"
      >
        <i class="mdi mdi-timer-sand" /> {{ t('actionList.addDelay') }}
      </button>
      <button
        v-if="props.appMode === 'home_assistant'"
        class="btn btn-sm btn-secondary border-dashed"
        @click="emit('add-action', 'event')"
      >
        <i class="mdi mdi-home-assistant" /> {{ t('actionList.addHaEvent') }}
      </button>
      <button
        v-if="props.appMode === 'standalone'"
        class="btn btn-sm btn-secondary border-dashed"
        @click="emit('add-action', 'event')"
      >
        <i class="mdi mdi-lightning-bolt" /> {{ t('actionList.addEvent') }}
      </button>
    </div>
  </div>
</template>