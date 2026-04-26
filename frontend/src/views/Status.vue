<script setup lang="ts">
import { onMounted, computed, ref, watch, nextTick } from 'vue';
import { storeToRefs } from 'pinia';
import { useCommonStore } from '../stores/common';
import { useDeviceStore, type Device } from '../stores/devices';
import { useIrdbStore } from '../stores/irdb';
import { useSettingsStore } from '../stores/settings';
import { useI18n } from '../i18n';

const commonStore = useCommonStore();
const deviceStore = useDeviceStore();
const irdbStore = useIrdbStore();
const settingsStore = useSettingsStore();

const { logs, mqttConnected } = storeToRefs(commonStore);
const { devices } = storeToRefs(deviceStore);
const { irdbStatus } = storeToRefs(irdbStore);
const { version } = storeToRefs(settingsStore);

const { t } = useI18n();

const logBoxRef = ref<HTMLElement | null>(null);
const autoScroll = ref(true);

onMounted(() => {
    irdbStore.fetchIrdbStatus();
});

watch(logs, async () => {
    if (autoScroll.value && logBoxRef.value) {
        await nextTick();
        logBoxRef.value.scrollTop = logBoxRef.value.scrollHeight;
    }
}, { deep: true });

const buttonCount = computed(() => {
    return devices.value.reduce((acc: number, dev: Device) => acc + (dev.buttons?.length || 0), 0);
});

const lastUpdated = computed(() => {
    if (!irdbStatus.value.last_updated) return 'N/A';
    return new Date(irdbStatus.value.last_updated).toLocaleString();
});

</script>

<template>
  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6 mb-8">
    <!-- MQTT Status -->
    <div class="card p-6 flex items-center gap-4">
      <i
        class="mdi text-4xl"
        :class="mqttConnected ? 'mdi-lan-connect text-green-500' : 'mdi-lan-disconnect text-red-500'"
      />
      <div>
        <div class="font-semibold text-sm">
          {{ t('status.mqtt') }}
        </div>
        <div
          class="text-gray-500"
          :class="mqttConnected ? 'text-green-500' : 'text-red-500'"
        >
          {{ mqttConnected ? t('status.connected') : t('status.disconnected') }}
        </div>
      </div>
    </div>

    <!-- Devices -->
    <div class="card p-6 flex items-center gap-4">
      <i class="mdi mdi-remote-tv text-4xl text-blue-500" />
      <div>
        <div class="font-semibold text-sm">
          {{ t('status.devices') }}
        </div>
        <div class="text-gray-500">
          {{ devices.length }}
        </div>
      </div>
    </div>

    <!-- Buttons -->
    <div class="card p-6 flex items-center gap-4">
      <i class="mdi mdi-gesture-tap-button text-4xl text-purple-500" />
      <div>
        <div class="font-semibold text-sm">
          {{ t('status.buttons') }}
        </div>
        <div class="text-gray-500">
          {{ buttonCount }}
        </div>
      </div>
    </div>

    <!-- IRDB Status -->
    <div class="card p-6 flex items-center gap-4 relative group">
      <i class="mdi mdi-database text-4xl text-yellow-500" />
      <div>
        <div class="font-semibold text-sm">
          {{ t('status.irdb') }}
        </div>
        <div
          class="text-gray-500"
          :class="irdbStatus.exists ? 'text-green-500' : 'text-red-500'"
        >
          {{ irdbStatus.exists ? t('status.loaded') : t('status.notFound') }}
        </div>
      </div>
      <!-- Tooltip -->
      <div
        v-if="irdbStatus.exists"
        class="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 w-max bg-gray-800 text-gray-200 text-xs rounded py-2 px-3 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-lg z-10"
      >
        <div class="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1">
          <span class="font-semibold text-gray-400">{{ t('status.remotes') }}</span> 
          <span class="text-right">{{ irdbStatus.total_remotes }}</span>
          <span class="font-semibold text-gray-400">{{ t('status.codesTooltip') }}</span>
          <span class="text-right">{{ irdbStatus.total_codes }}</span>
          <span class="font-semibold text-gray-400">{{ t('status.updated') }}</span>
          <span class="text-right">{{ lastUpdated }}</span>
        </div>
      </div>
    </div>

    <!-- App Version -->
    <div class="card p-6 flex items-center gap-4">
      <i class="mdi mdi-information-outline text-4xl text-indigo-500" />
      <div>
        <div class="font-semibold text-sm">
          {{ t('status.version') }}
        </div>
        <div class="text-gray-500">
          {{ version }}
        </div>
      </div>
    </div>
  </div>

  <div class="card h-full flex flex-col mt-8">
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-lg font-semibold">
        {{ t('status.logs') }}
      </h2>
      <div class="flex gap-2">
        <button
          class="btn btn-sm"
          :class="autoScroll ? 'btn-primary' : 'btn-secondary'"
          :title="autoScroll ? 'Disable Auto-Scroll' : 'Enable Auto-Scroll'"
          @click="autoScroll = !autoScroll"
        >
          <i
            class="mdi"
            :class="autoScroll ? 'mdi-lock-outline' : 'mdi-lock-open-variant-outline'"
          /> {{ t('status.autoScroll') }}
        </button>
        <button
          class="btn btn-sm btn-secondary"
          @click="commonStore.clearLogs"
        >
          <i class="mdi mdi-delete-sweep-outline" /> {{ t('status.clear') }}
        </button>
      </div>
    </div>
    <div
      id="log-box"
      ref="logBoxRef"
      class="log-console flex-grow"
    >
      <div
        v-for="(log, i) in logs"
        :key="i"
        :class="['log-entry', log.special ? `log-entry--${log.special}` : `log-entry--${log.level}`]"
      >
        <span class="log-timestamp">{{ new Date(log.timestamp).toLocaleTimeString() }}</span>
        <span class="log-level">{{ log.level }}</span>
        <span class="log-message">{{ log.message }}</span>
      </div>
    </div>
  </div>
</template>