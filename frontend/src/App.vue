<script setup lang="ts">
import { onMounted, computed, defineAsyncComponent, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useDeviceStore } from './stores/devices';
import { useAutomationsStore } from './stores/automations';
import { useCommonStore } from './stores/common';
import { useSettingsStore } from './stores/settings';
import { useIrdbStore } from './stores/irdb';
import { useBridgeStore } from './stores/bridges';
import { startAutomationTour, startDevicesTour, startBridgesTour, startSettingsTour } from './tour';
import { useI18n } from './i18n';

import SideNav from './components/SideNav.vue';
import DeviceModal from './components/DeviceModal.vue';
import ButtonModal from './components/ButtonModal.vue';
import AutomationModal from './components/AutomationModal.vue';
import FlashMessages from './components/FlashMessages.vue';
import ConfirmModal from './components/ConfirmModal.vue';
import IrDbPicker from './components/IrDbPicker.vue';

const deviceStore = useDeviceStore();
const automationsStore = useAutomationsStore();
const commonStore = useCommonStore();
const settingsStore = useSettingsStore();
const irdbStore = useIrdbStore();
const bridgeStore = useBridgeStore();

const { editingDevice, editingButton } = storeToRefs(deviceStore);
const { editingAutomation } = storeToRefs(automationsStore);
const { activeView } = storeToRefs(commonStore);
const { settings, isFactoryResetting } = storeToRefs(settingsStore);
const { showIrDbBrowser } = storeToRefs(irdbStore);
const { bridges } = storeToRefs(bridgeStore);

const { t } = useI18n();

const protocols = [
  // Common
  'nec', 'samsung', 'samsung36', 'sony', 'panasonic', 'rc5', 'rc6', 'jvc', 'lg',
  'coolix', 'pioneer', 'dish', 'midea', 'haier', 'pronto', 'raw',
  // Legacy (keep for existing buttons)
  'sharp', 'sanyo', 'toshiba', 'whynter', 'rca',
  // New
  'aeha', 'abbwelcome', 'beo4', 'byronsx',
  'canalsat', 'canalsat_ld', 'dooya', 'drayton', 'dyson',
  'gobox', 'keeloq', 'magiquest', 'mirage',
  'nexa', 'rc_switch', 'roomba', 'symphony', 'toshiba_ac', 'toto',
];

const views: Record<string, import('vue').Component> = {
  Devices: defineAsyncComponent(() => import('./views/Devices.vue')),
  Automations: defineAsyncComponent(() => import('./views/Automations.vue')),
  Bridges: defineAsyncComponent(() => import('./views/Bridges.vue')),
  Settings: defineAsyncComponent(() => import('./views/Settings.vue')),
  Status: defineAsyncComponent(() => import('./views/Status.vue')),
};

const currentView = computed(() => views[activeView.value]);

watch(
  () => settings.value.theme,
  (theme, prevTheme) => {
    const bodyClassList = document.body.classList;
    if (prevTheme) {
      bodyClassList.remove(prevTheme);
    }
    bodyClassList.add(theme);
  },
  { immediate: true }
);

watch(activeView, (newView) => {
  window.history.pushState({ view: newView }, '', `#${newView}`);
  document.title = `IR2MQTT - ${t('nav.' + newView.toLowerCase().replace(' ', ''))}`;
});

onMounted(() => {
    deviceStore.fetchDevices();
    automationsStore.fetchAutomations();
    bridgeStore.fetchBridges();
    settingsStore.fetchAppMode();
    commonStore.connectWs();

    window.addEventListener('popstate', (event) => {
        if (event.state && event.state.view) {
            activeView.value = event.state.view;
        } else {
            // Handle initial page load with hash
            const hash = window.location.hash.replace(/^#/, '');
            if (views[hash]) {
                activeView.value = hash;
            }
        }
    });

    // Set initial view based on hash or default
    const hash = window.location.hash.replace(/^#/, '');
    if (views[hash]) {
        activeView.value = hash;
    } else {
        history.replaceState({ view: activeView.value }, '', `#${activeView.value}`);
    }
});

</script>

<template>
  <div class="flex h-screen">
    <FlashMessages />
    <SideNav />
    <main class="flex-1 p-6 overflow-auto">
      <header class="flex justify-between items-center mb-5">
        <h1
          class="text-2xl font-medium text-ha-500 flex items-center gap-2"
          data-tour-id="view-title"
        >
          {{ t('nav.' + activeView.toLowerCase().replace(' ', '')) }}
          <button
            v-if="activeView === 'Devices'"
            class="text-gray-500 hover:text-gray-300 transition-colors"
            :title="t('app.startTour', { tour: t('nav.devices') })"
            @click="startDevicesTour"
          >
            <i class="mdi mdi-help-circle-outline text-lg" />
          </button>
          <button
            v-if="activeView === 'Automations'"
            class="text-gray-500 hover:text-gray-300 transition-colors"
            :title="t('app.startTour', { tour: t('nav.automations') })"
            @click="startAutomationTour"
          >
            <i class="mdi mdi-help-circle-outline text-lg" />
          </button>
          <button
            v-if="activeView === 'Bridges'"
            class="text-gray-500 hover:text-gray-300 transition-colors"
            :title="t('app.startTour', { tour: t('nav.bridges') })"
            @click="startBridgesTour"
          >
            <i class="mdi mdi-help-circle-outline text-lg" />
          </button>
          <button
            v-if="activeView === 'Settings'"
            class="text-gray-500 hover:text-gray-300 transition-colors"
            :title="t('app.startTour', { tour: t('nav.settings') })"
            @click="startSettingsTour"
          >
            <i class="mdi mdi-help-circle-outline text-lg" />
          </button>
        </h1>
        <div
          id="header-actions"
          class="flex items-center gap-3"
        />
      </header>
      <component :is="currentView" />
    </main>

    <!-- MODALS -->
    <IrDbPicker 
      :show="showIrDbBrowser"
      selection-mode="browse"
      @close="showIrDbBrowser = false"
    />

    <DeviceModal 
      :show="!!editingDevice" 
      :device="editingDevice"
      :bridges="bridges"
      @close="editingDevice = null"
    />

    <ButtonModal
      :show="!!editingButton"
      :button="editingButton"
      :protocols="protocols"
      @close="editingButton = null"
    />

    <AutomationModal
      :show="!!editingAutomation"
      :automation="editingAutomation"
      @close="editingAutomation = null"
    />

    <ConfirmModal />

    <div
      v-if="isFactoryResetting"
      class="fixed inset-0 !m-0 bg-gray-900/60 z-[100] flex flex-col items-center justify-center text-center backdrop-blur-sm"
    >
      <i class="mdi mdi-nuke text-6xl text-red-500 animate-pulse mb-4" />
      <h2 class="text-2xl font-bold text-gray-200 mb-2">
        {{ t('app.factoryResettingTitle') }}
      </h2>
      <p class="text-gray-400">
        {{ t('app.factoryResettingDesc') }}
      </p>
    </div>
  </div>
</template>