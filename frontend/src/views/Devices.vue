<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { storeToRefs } from 'pinia';
import DeviceModal from '../components/DeviceModal.vue';
import LearnModal from '../components/LearnModal.vue';
import { useDeviceStore, isButtonValid, isSameCode, Device } from '../stores/devices';
import { useLearnStore } from '../stores/learn';
import { useBridgeStore } from '../stores/bridges';
import { useCommonStore } from '../stores/common';
import { useSettingsStore } from '../stores/settings';
import { useDragDrop } from '../composables/useDragDrop';
import IrCodeDetails from '../components/IrCodeDetails.vue';
import { useI18n } from '../i18n';
import type { IRCode } from '../types';

interface ButtonDropData {
    type: 'button';
    devId: string;
    index: number;
}

const deviceStore = useDeviceStore();
const learnStore = useLearnStore();
const bridgeStore = useBridgeStore();
const commonStore = useCommonStore();
const settingsStore = useSettingsStore();
const { t } = useI18n();

const { devices, flashingSendButtons, flashingReceiveButtons, flashingIgnoredButtons, topicsVisibleForDevice } = storeToRefs(deviceStore);
const { learn, hasNewCode } = storeToRefs(learnStore);
const { bridges, onlineBridges, hasOnlineBridges } = storeToRefs(bridgeStore);
const { settings } = storeToRefs(settingsStore);

const showDeviceModal = ref(false);
const showLearnModal = ref(false);
const deviceToEdit = ref<Device | null>(null);

const isMounted = ref(false);
onMounted(() => { 
  if (document.getElementById('header-actions')) {
    isMounted.value = true;
  }
});

const toggleTopics = (id: string) => {
    if (topicsVisibleForDevice.value.has(id)) {
        topicsVisibleForDevice.value.delete(id);
    } else {
        topicsVisibleForDevice.value.add(id);
    }
};

const isTopicsVisible = (id: string) => {
    return topicsVisibleForDevice.value.has(id);
};

const openAddDeviceModal = () => {
    deviceToEdit.value = null;
    showDeviceModal.value = true;
};

const openEditDeviceModal = (dev: Device) => {
    deviceToEdit.value = dev;
    showDeviceModal.value = true;
};

// Device Drag & Drop
const { 
    draggingIndex: draggingDeviceIndex, 
    dragOverIndex: dragOverDeviceIndex, 
    onDragStart: onDeviceDragStart, 
    onDragOver: onDeviceDragOver, 
    onDrop: onDeviceDrop, 
    onDragEnd: onDeviceDragEnd 
} = useDragDrop((fromIndex: number, toIndex: number) => {
    const newOrder = [...devices.value];
    const [moved] = newOrder.splice(fromIndex, 1);
    newOrder.splice(toIndex, 0, moved);
    deviceStore.reorderDevices(newOrder.map(d => d.id));
});

// Button Drag & Drop (Custom implementation needed due to nested structure)
const draggingButton = ref<{ devId: string; index: number } | null>(null);
const dragOverButton = ref<{ devId: string; index: number } | null>(null);

const onButtonDragStart = (event: DragEvent, devId: string, index: number) => {
    draggingButton.value = { devId, index };
    if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.dropEffect = 'move';
        event.dataTransfer.setData('application/json', JSON.stringify({ type: 'button', devId, index }));
        event.stopPropagation();
        const target = event.target as HTMLElement;
        const buttonCard = target.closest('.group');
        if (buttonCard) {
            const rect = buttonCard.getBoundingClientRect();
            event.dataTransfer.setDragImage(buttonCard, event.clientX - rect.left, event.clientY - rect.top);
        }
    }
};

const onButtonDrop = (event: DragEvent, devId: string, toIndex: number) => {
    draggingButton.value = null;
    dragOverButton.value = null;

    if (!event.dataTransfer) return;
    const dataStr = event.dataTransfer.getData('application/json');
    if (!dataStr) return;
    const data = JSON.parse(dataStr) as ButtonDropData;
    
    if (data.type !== 'button' || data.devId !== devId || data.index === toIndex) return;
    event.stopPropagation();

    const device = devices.value.find(d => d.id === devId);
    if (!device) return;

    const newOrder = [...device.buttons];
    const [moved] = newOrder.splice(data.index, 1);
    newOrder.splice(toIndex, 0, moved);
    
    deviceStore.reorderButtons(devId, newOrder.map(b => b.id));
};

const onButtonDragOver = (devId: string, index: number) => {
    if (draggingButton.value?.devId === devId) {
        dragOverButton.value = { devId, index };
    }
};

const onButtonDragEnd = () => {
    draggingButton.value = null;
    dragOverButton.value = null;
};

const onDeviceCreated = (deviceId: string) => {
    if (deviceId && !deviceStore.isDeviceExpanded(deviceId)) {
        deviceStore.toggleDevice(deviceId);
    }
};

const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
        commonStore.addFlashMessage(t('store.topicCopied'), 'success');
    }).catch(() => {
        commonStore.addFlashMessage(t('store.topicCopyFailed'), 'error');
    });
};

const findExistingCodeMatch = (code: IRCode | null) => {
    if (!code) return null;
    for (const device of devices.value) {
        for (const button of device.buttons) {
            if (button.code && isSameCode(button.code, code)) {
                return { device, button };
            }
        }
    }
    return null;
};

const receivedCodesWithMatches = computed(() =>
    learn.value.received_codes.map(code => ({
        code,
        match: findExistingCodeMatch(code),
    }))
);

const lastCodeBridgeLabel = computed(() => {
    const id = learn.value.last_code_bridge;
    if (!id) return id;
    const bridge = bridges.value.find(b => b.id === id);
    return bridge && bridge.name && bridge.name !== id ? `${bridge.name} (${id})` : id;
});

const learnPanelMinimized = ref(false);

const canSendToDevice = (dev: Device) => {
    if (!hasOnlineBridges.value) return false;
    if (!dev.target_bridges || dev.target_bridges.length === 0) return true;
    return dev.target_bridges.some(targetId => onlineBridges.value.some(b => b.id === targetId || b.id === targetId.split(':')[0]));
};
</script>
<template>
  <div class="space-y-4 pb-20">
    <!-- Floating received-code panel -->
    <Transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 translate-y-4 scale-95"
      enter-to-class="opacity-100 translate-y-0 scale-100"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 translate-y-0 scale-100"
      leave-to-class="opacity-0 translate-y-4 scale-95"
    >
      <div
        v-if="hasNewCode"
        class="fixed bottom-4 right-4 z-40 w-80 rounded-xl border border-green-700 bg-gray-900/95 shadow-2xl backdrop-blur-sm pointer-events-none"
        style="max-height: calc(100vh - 2rem);"
      >
        <!-- Header -->
        <div class="flex items-center gap-2 px-3 py-2 border-b border-green-800/60 pointer-events-auto">
          <span class="w-2 h-2 rounded-full bg-green-400 shrink-0 animate-pulse" />
          <span class="flex-1 font-semibold text-sm text-green-400 truncate">
            {{ learn.received_codes.length > 1 ? t('devices.codesReceived', { count: learn.received_codes.length }) : t('devices.codeReceived') }}
          </span>
          <button
            class="text-gray-400 hover:text-gray-200 transition-colors p-0.5"
            :title="learnPanelMinimized ? t('devices.expand') : t('devices.minimize')"
            @click="learnPanelMinimized = !learnPanelMinimized"
          >
            <i :class="learnPanelMinimized ? 'mdi mdi-chevron-up' : 'mdi mdi-chevron-down'" />
          </button>
          <button
            class="text-gray-400 hover:text-red-400 transition-colors p-0.5"
            :title="t('devices.dismiss')"
            data-testid="learn-panel-dismiss"
            @click="learn.received_codes = []; learn.last_code = null; learnPanelMinimized = false"
          >
            <i class="mdi mdi-close" />
          </button>
        </div>

        <!-- Body -->
        <Transition
          enter-active-class="transition-all duration-200 ease-out"
          enter-from-class="opacity-0"
          enter-to-class="opacity-100"
          leave-active-class="transition-all duration-150 ease-in"
          leave-from-class="opacity-100"
          leave-to-class="opacity-0"
        >
          <div
            v-if="!learnPanelMinimized"
            class="flex flex-col overflow-hidden pointer-events-none"
            style="max-height: calc(100vh - 8rem);"
          >
            <p class="px-3 pt-2 pb-1 text-xs text-gray-400">
              {{ t('devices.receivedFrom', { bridge: lastCodeBridgeLabel }) }}
            </p>
            <div class="overflow-y-auto px-3 pb-3 space-y-2 pointer-events-auto">
              <div
                v-for="({ code, match }, idx) in receivedCodesWithMatches"
                :key="idx"
                class="p-2 rounded-lg border cursor-pointer transition-colors pointer-events-auto"
                :class="learn.last_code === code ? 'bg-green-900/30 border-green-500' : 'bg-gray-800/60 border-gray-700 hover:border-gray-500'"
                @click="learn.last_code = code"
              >
                <div class="flex items-center gap-2 mb-1">
                  <div
                    class="w-3.5 h-3.5 rounded-full border flex items-center justify-center shrink-0"
                    :class="learn.last_code === code ? 'border-green-400' : 'border-gray-500'"
                  >
                    <div
                      v-if="learn.last_code === code"
                      class="w-1.5 h-1.5 rounded-full bg-green-400"
                    />
                  </div>
                  <span class="text-xs font-bold text-gray-400">{{ t('devices.option', { num: idx + 1 }) }}</span>
                </div>
                <IrCodeDetails
                  :code="code"
                  show-protocol
                  class="mt-1"
                />
                <div
                  v-if="match"
                  class="mt-1.5 flex items-center gap-1 text-xs text-yellow-400"
                >
                  <i class="mdi mdi-information-outline" />
                  <span class="truncate">{{ match.device.name }} › {{ match.button.name }}</span>
                </div>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>

    <div
      v-if="learn.active"
      class="fixed inset-0 !m-0 bg-gray-900/60 flex items-center justify-center z-50 backdrop-blur-sm"
      @click.self="learnStore.cancelLearn"
    >
      <div
        class="bg-gray-900 border border-gray-700 rounded-lg p-8 w-[600px] max-w-full text-center shadow-2xl animate-in fade-in scale-95 duration-200"
        style="animation: slideInUp 0.3s ease-out;"
      >
        <i class="mdi mdi-radio-tower text-6xl text-ha-500 pulse mb-4" />
        <h2 class="text-2xl font-bold mb-2">
          {{ t('devices.learningModeActive') }}
        </h2>
        <div
          v-if="learn.mode === 'smart'"
          class="mb-6"
        >
          <p class="text-lg font-semibold text-yellow-400 mb-2">
            {{ t('devices.pressMore', { count: learn.target - learn.progress }) }}
          </p>
          <div class="w-full bg-gray-700 rounded-full h-4 overflow-hidden">
            <div
              class="bg-ha-500 h-4 rounded-full transition-all duration-300"
              :style="{ width: (learn.progress / learn.target * 100) + '%' }"
            />
          </div>
          <p class="text-xs text-gray-500 mt-2">
            {{ t('devices.analyzing') }}
          </p>
        </div>
        <p
          v-else
          class="text-gray-400 mb-6"
        >
          {{ t('devices.pointRemotePrefix') }}<span class="font-bold text-gray-200">{{ learn.activeOn.join(', ') }}</span>{{ t('devices.pointRemoteSuffix') }}
        </p>
        <button
          class="btn btn-danger"
          @click="learnStore.cancelLearn"
        >
          {{ t('devices.cancelLearning') }}
        </button>
      </div>
    </div>

    <LearnModal
      :show="showLearnModal"
      @close="showLearnModal = false"
    />
    <DeviceModal
      :show="showDeviceModal"
      :device="deviceToEdit"
      :bridges="bridges"
      @close="showDeviceModal = false"
      @device-created="onDeviceCreated"
    />

    <div
      v-if="devices.length == 0"
      class="text-center text-gray-500 mt-10"
      data-tour-id="no-devices-message"
    >
      <i class="mdi mdi-remote-tv-off text-6xl mb-2" />
      <p class="font-bold">
        {{ t('devices.noDevices') }}
      </p>
      <p class="text-sm">
        {{ t('devices.noDevicesDesc') }}
      </p>
    </div>

    <!-- VIEW MODE TOGGLE -->
    <Teleport
      v-if="isMounted"
      to="#header-actions"
    >
      <div
        v-if="devices.length > 0"
        class="flex bg-gray-900 rounded-lg p-1 border border-gray-700 shadow-sm"
      >
        <button
          class="px-3 py-1 rounded-md text-sm transition-colors"
          :class="settings.deviceViewMode === 'compact' ? 'bg-gray-700 text-gray-200' : 'text-gray-400 hover:text-gray-200'"
          :title="t('devices.viewCompact')"
          @click="settings.deviceViewMode = 'compact'"
        >
          <i class="mdi mdi-view-comfy" />
        </button>
        <button
          class="px-3 py-1 rounded-md text-sm transition-colors"
          :class="settings.deviceViewMode === 'normal' ? 'bg-gray-700 text-gray-200' : 'text-gray-400 hover:text-gray-200'"
          :title="t('devices.viewNormal')"
          @click="settings.deviceViewMode = 'normal'"
        >
          <i class="mdi mdi-view-module" />
        </button>
        <button
          class="px-3 py-1 rounded-md text-sm transition-colors"
          :class="settings.deviceViewMode === 'large' ? 'bg-gray-700 text-gray-200' : 'text-gray-400 hover:text-gray-200'"
          :title="t('devices.viewLarge')"
          @click="settings.deviceViewMode = 'large'"
        >
          <i class="mdi mdi-view-grid" />
        </button>
      </div>
    </Teleport>

    <div
      v-if="devices.length > 0"
      class="grid grid-cols-1 gap-4 items-start"
    >
      <div 
        v-for="(dev, index) in devices" 
        :key="dev.id" 
        class="card relative transition-all duration-200 flex flex-col gap-0 overflow-hidden p-0"
        data-tour-id="device-card"
        :class="{
          'opacity-40': draggingDeviceIndex === index,
          'border-blue-500 bg-gray-800/50': dragOverDeviceIndex === index && draggingDeviceIndex !== index,
          'border-t-4 border-t-blue-500': dragOverDeviceIndex === index && (draggingDeviceIndex ?? -1) > index,
          'border-b-4 border-b-blue-500': dragOverDeviceIndex === index && (draggingDeviceIndex ?? -1) < index
        }"
        @dragover.prevent="onDeviceDragOver(index)"
        @drop="onDeviceDrop($event, index, 'device')"
        @dragend="onDeviceDragEnd"
      >
        <div
          class="flex justify-between items-center px-4 py-3 border-b border-gray-700 bg-gray-800/20"
          data-tour-id="device-card-header"
        >
          <div class="flex items-center gap-2">
            <h3
              class="text-lg font-semibold flex items-center gap-2 cursor-pointer"
              data-tour-id="device-expand-toggle"
              @click="deviceStore.toggleDevice(dev.id)"
            >
              <i
                class="mdi mdi-chevron-down transition-transform transform"
                :class="deviceStore.isDeviceExpanded(dev.id) ? '' : '-rotate-90'"
              />
              <i
                class="mdi"
                :class="`mdi-${dev.icon || 'help-box'}`"
              />
              <span>{{ dev.name }}</span>
            </h3>
          </div>
          <div
            class="flex items-center gap-2"
            data-tour-id="device-action-buttons"
          >
            <button
              :class="isTopicsVisible(dev.id) ? 'text-blue-400' : 'text-gray-500 hover:text-blue-400'" 
              :title="isTopicsVisible(dev.id) ? t('devices.hideTopics') : t('devices.showTopics')"
              data-tour-id="device-show-topics"
              @click="toggleTopics(dev.id)"
            >
              <i
                class="mdi"
                :class="isTopicsVisible(dev.id) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
              />
            </button>
            <button
              class="text-gray-500 hover:text-blue-400"
              :title="t('devices.editDevice')"
              data-tour-id="device-edit-button"
              @click="openEditDeviceModal(dev)"
            >
              <i class="mdi mdi-pencil-outline" />
            </button>
            <button
              class="text-gray-500 hover:text-green-400"
              :title="t('devices.duplicateDevice')"
              data-tour-id="device-duplicate-button"
              @click="deviceStore.duplicateDevice(dev.id)"
            >
              <i class="mdi mdi-content-copy" />
            </button>
            <button
              class="text-gray-500 hover:text-red-400"
              :title="t('devices.deleteDevice')"
              data-tour-id="device-delete-button"
              @click="deviceStore.deleteDevice(dev.id, $event)"
            >
              <i class="mdi mdi-delete-outline" />
            </button>
          </div>
        </div>

        <div
          v-if="isTopicsVisible(dev.id)"
          class="p-4 bg-gray-800 border-b border-gray-700"
        >
          <h4 class="text-sm font-semibold mb-2">
            {{ t('devices.mqttTopics') }}
          </h4>
          <div class="space-y-4">
            <div
              v-for="btn in dev.buttons"
              :key="btn.id"
            >
              <p class="font-bold text-ha-500">
                {{ btn.name }}
              </p>
              <div class="text-sm space-y-1 mt-1">
                <p>
                  <strong>{{ t('devices.commandTopic') }}:</strong> <code
                    class="text-yellow-300 bg-gray-900 p-1 rounded cursor-pointer hover:bg-gray-700 transition-colors"
                    :title="t('devices.clickToCopy')"
                    @click="copyToClipboard(deviceStore.getCommandTopic(dev, btn))"
                  >{{ deviceStore.getCommandTopic(dev, btn) }}</code> ({{ t('devices.payloadLabel') }}: <code class="text-yellow-300 bg-gray-900 p-1 rounded">PRESS</code>)
                </p>
                <p v-if="btn.is_input">
                  <strong>{{ t('devices.stateTopic') }}:</strong> <code
                    class="text-yellow-300 bg-gray-900 p-1 rounded cursor-pointer hover:bg-gray-700 transition-colors"
                    :title="t('devices.clickToCopy')"
                    @click="copyToClipboard(deviceStore.getStateTopic(dev, btn))"
                  >{{ deviceStore.getStateTopic(dev, btn) }}</code> ({{ t('devices.payloadLabel') }}: <code class="text-yellow-300 bg-gray-900 p-1 rounded">ON</code> / <code class="text-yellow-300 bg-gray-900 p-1 rounded">OFF</code>)
                </p>
                <p v-if="btn.is_event">
                  <strong>{{ t('devices.eventTopic') }}:</strong> <code
                    class="text-yellow-300 bg-gray-900 p-1 rounded cursor-pointer hover:bg-gray-700 transition-colors"
                    :title="t('devices.clickToCopy')"
                    @click="copyToClipboard(deviceStore.getEventTopic(dev, btn))"
                  >{{ deviceStore.getEventTopic(dev, btn) }}</code>
                </p>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="deviceStore.isDeviceExpanded(dev.id)"
          class="grid bg-gray-900"
          :class="{
            'grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2 p-3': settings.deviceViewMode === 'compact',
            'grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 p-4': settings.deviceViewMode === 'normal',
            'grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 p-6': settings.deviceViewMode === 'large'
          }"
        >
          <div 
            v-for="(btn, btnIndex) in dev.buttons" 
            :key="btn.id" 
            class="bg-gray-900 border border-gray-600 rounded-lg text-center group relative flex flex-col justify-between transition-all h-full" 
            :data-tour-id="'device-button-card-' + btn.name.replace(/\s+/g, '-').toLowerCase()"
            :class="{ 
              'p-2': settings.deviceViewMode === 'compact',
              'p-3': settings.deviceViewMode === 'normal',
              'p-5': settings.deviceViewMode === 'large',
              'flash-send': flashingSendButtons.has(btn.id),
              'flash-receive': flashingReceiveButtons.has(btn.id),
              'flash-ignore': flashingIgnoredButtons.has(btn.id),
              'opacity-40': draggingButton?.devId === dev.id && draggingButton?.index === btnIndex,
              'border-blue-500 bg-gray-800': dragOverButton?.devId === dev.id && dragOverButton?.index === btnIndex && draggingButton?.index !== btnIndex,
              'border-l-4 border-l-blue-500': dragOverButton?.devId === dev.id && dragOverButton?.index === btnIndex && (draggingButton?.index ?? -1) > btnIndex,
              'border-r-4 border-r-blue-500': dragOverButton?.devId === dev.id && dragOverButton?.index === btnIndex && (draggingButton?.index ?? -1) < btnIndex
            }"
            @dragover.prevent="onButtonDragOver(dev.id, btnIndex)"
            @drop="onButtonDrop($event, dev.id, btnIndex)"
            @dragend="onButtonDragEnd"
          >
            <div>
              <div
                class="absolute top-1 left-1 cursor-move text-gray-500 hover:text-gray-400 z-10 opacity-0 group-hover:opacity-100 transition-opacity"
                draggable="true"
                :title="t('devices.dragToReorder')"
                @dragstart="onButtonDragStart($event, dev.id, btnIndex)"
              >
                <i class="mdi mdi-drag" />
              </div>
              <i
                class="mdi transition-all"
                :class="[
                  `mdi-${btn.icon || 'help-box'}`, 
                  isButtonValid(btn) ? 'text-ha-500' : 'text-gray-400',
                  {
                    'text-2xl': settings.deviceViewMode === 'compact',
                    'text-3xl': settings.deviceViewMode === 'normal',
                    'text-5xl': settings.deviceViewMode === 'large',
                    'flash-text-send': flashingSendButtons.has(btn.id),
                    'flash-text-receive': flashingReceiveButtons.has(btn.id),
                    'flash-text-ignore': flashingIgnoredButtons.has(btn.id)
                  }
                ]"
              />
              <p
                class="font-bold truncate mt-1"
                :class="{
                  'text-[10px] leading-tight': settings.deviceViewMode === 'compact',
                  'text-sm': settings.deviceViewMode === 'normal',
                  'text-base': settings.deviceViewMode === 'large'
                }"
              >
                {{ btn.name }}
              </p>
                        
              <p
                v-if="isButtonValid(btn)"
                class="text-xs text-gray-500 truncate"
                :class="settings.deviceViewMode === 'compact' ? 'text-[9px]' : 'text-xs'"
              >
                {{ btn.code?.protocol }}
              </p>
              <p
                v-else
                class="text-xs text-gray-500"
                :class="settings.deviceViewMode === 'compact' ? 'text-[9px]' : 'text-xs'"
              >
                {{ t('devices.noCode') }}
              </p>

              <div
                v-if="settings.deviceViewMode !== 'compact'"
                class="flex justify-center gap-1 mt-1 flex-wrap"
              >
                <span
                  v-if="btn.is_event"
                  class="text-[10px] bg-yellow-500/10 text-yellow-400 px-1 rounded border border-yellow-500/50"
                  :title="t('devices.button.event')"
                >{{ t('devices.button.badges.evt') }}</span>
                <span
                  v-if="btn.is_output"
                  class="text-[10px] bg-green-600/10 text-green-400 px-1 rounded border border-green-600/50"
                  :title="t('devices.button.output')"
                >{{ t('devices.button.badges.out') }}</span>
                <span
                  v-if="btn.is_input"
                  class="text-[10px] bg-blue-500/10 text-blue-400 px-1 rounded border border-blue-500 cursor-help flex items-center gap-1"
                  :title="`${t('devices.button.input')}: ${btn.input_mode}`"
                >
                  {{ t('devices.button.badges.in') }}
                  <i
                    v-if="btn.input_mode === 'momentary'"
                    class="mdi mdi-gesture-tap-button text-[10px]"
                  />
                  <i
                    v-else-if="btn.input_mode === 'toggle'"
                    class="mdi mdi-toggle-switch text-[10px]"
                  />
                  <i
                    v-else-if="btn.input_mode === 'timed'"
                    class="mdi mdi-timer-outline text-[10px]"
                  />
                </span>
              </div>
            </div>

            <div
              :class="settings.deviceViewMode === 'compact' ? 'mt-2' : 'mt-3'"
              class="space-y-2"
            >
              <div
                v-if="btn.is_output"
                class="flex gap-2"
              >
                <button
                  class="btn btn-sm flex-grow justify-center bg-gray-700 border border-gray-600 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  :class="settings.deviceViewMode === 'compact' ? 'rounded py-0.5 text-[10px]' : 'btn btn-sm rounded'"
                  :disabled="!isButtonValid(btn) || !canSendToDevice(dev)"
                  :title="t('devices.triggerButton')"
                  @click="deviceStore.triggerButton(dev.id, btn.id)"
                >
                  <i
                    class="mdi mdi-send"
                    :class="settings.deviceViewMode === 'compact' ? 'text-[10px]' : ''"
                  />
                </button>
              </div>
              <div
                v-else
                class="flex items-center justify-center text-gray-500 italic"
                :class="settings.deviceViewMode === 'compact' ? 'h-[20px] text-[9px]' : 'h-[32px] text-xs'"
              >
                {{ t('devices.inputOnly') }}
              </div>
            </div>

            <div
              v-if="hasNewCode" 
              class="absolute inset-0 bg-gray-900/80 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-200 transform scale-95 group-hover:scale-100 cursor-pointer rounded-lg"
              @click="deviceStore.assignCode(dev.id, btn.id)"
            >
              <div class="text-center">
                <template v-if="isSameCode(btn.code, learn.last_code)">
                  <i class="mdi mdi-check-all text-4xl text-blue-400" />
                  <p class="font-bold text-blue-400">
                    {{ t('devices.sameCode') }}
                  </p>
                </template>
                <template v-else>
                  <i
                    class="mdi mdi-content-save-cog-outline text-4xl"
                    :class="isButtonValid(btn) ? 'text-orange-400' : 'text-green-400'"
                  />
                  <p
                    class="font-bold"
                    :class="isButtonValid(btn) ? 'text-orange-400' : 'text-green-400'"
                  >
                    {{ isButtonValid(btn) ? t('devices.overwriteCode') : t('devices.assignCode') }}
                  </p>
                </template>
              </div>
            </div>

            <div class="absolute -top-2 -right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity z-10">
              <button
                :title="t('devices.editButton')"
                class="p-1 bg-gray-900 border border-gray-600 rounded-full text-gray-500 hover:text-blue-400"
                @click="deviceStore.openButtonModal(dev.id, btn)"
              >
                <i class="mdi mdi-pencil" />
              </button>
              <button
                :title="t('devices.duplicateButton')"
                class="p-1 bg-gray-900 border border-gray-600 rounded-full text-gray-500 hover:text-green-400"
                @click="deviceStore.duplicateButton(dev.id, btn.id)"
              >
                <i class="mdi mdi-content-copy" />
              </button>
              <button
                :title="t('devices.deleteButton')"
                class="p-1 bg-gray-900 border border-gray-600 rounded-full text-gray-500 hover:text-red-400"
                @click="deviceStore.deleteButton(dev.id, btn.id, $event)"
              >
                <i class="mdi mdi-delete" />
              </button>
            </div>
          </div>
          <div
            data-tour-id="add-button-to-device"
            class="bg-gray-900 border-2 border-dashed border-gray-600 rounded-lg flex flex-col items-center justify-center cursor-pointer hover:bg-gray-700 hover:border-ha-500 transition h-full relative group"
            :class="{
              'p-2 min-h-[80px]': settings.deviceViewMode === 'compact',
              'p-4 min-h-[120px]': settings.deviceViewMode === 'normal',
              'p-6 min-h-[160px]': settings.deviceViewMode === 'large'
            }"
            @click="deviceStore.openButtonModal(dev.id)"
          >
            <i
              class="mdi mdi-plus text-gray-500"
              :class="{
                'text-2xl': settings.deviceViewMode === 'compact',
                'text-4xl': settings.deviceViewMode === 'normal',
                'text-6xl': settings.deviceViewMode === 'large'
              }"
            />
            <span
              class="text-gray-400 font-bold"
              :class="{
                'text-[10px]': settings.deviceViewMode === 'compact',
                'text-sm': settings.deviceViewMode === 'normal',
                'text-base': settings.deviceViewMode === 'large'
              }"
            >{{ t('devices.addButton') }}</span>
            <div
              v-if="hasNewCode" 
              class="absolute inset-0 bg-gray-900/80 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-200 transform scale-95 group-hover:scale-100 cursor-pointer rounded-lg"
            >
              <div class="text-center">
                <i class="mdi mdi-plus-circle-outline text-4xl text-green-400" />
                <p class="font-bold text-green-400">
                  {{ t('devices.addWithCode') }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div
          v-else
          class="flex flex-wrap gap-1 p-4 bg-gray-900"
        >
          <div
            v-for="btn in dev.buttons"
            :key="btn.id" 
            class="w-8 h-8 flex items-center justify-center rounded transition-all duration-300"
            :class="[
              isButtonValid(btn) && canSendToDevice(dev) ? 'cursor-pointer hover:bg-gray-700' : 'cursor-not-allowed opacity-50'
            ]"
            :title="btn.name"
            @click.stop="isButtonValid(btn) && canSendToDevice(dev) && deviceStore.triggerButton(dev.id, btn.id)"
          >
            <i
              class="mdi text-xl"
              :class="[
                `mdi-${btn.icon || 'help-box'}`, 
                isButtonValid(btn) ? 'text-ha-500' : 'text-gray-500',
                {
                  'flash-text-send': flashingSendButtons.has(btn.id),
                  'flash-text-receive': flashingReceiveButtons.has(btn.id),
                  'flash-text-ignore': flashingIgnoredButtons.has(btn.id)
                }
              ]"
            />
          </div>
        </div>

        <div
          class="absolute bottom-1 right-1 p-2 cursor-move text-gray-500 hover:text-gray-400 rounded hover:bg-gray-800/50 transition-colors"
          draggable="true"
          :title="t('devices.dragToReorder')"
          @dragstart="onDeviceDragStart($event, index, 'device')"
        >
          <i class="mdi mdi-drag text-xl" />
        </div>
      </div>
    </div>

    <!-- ACTION BUTTONS -->
    <div class="fixed bottom-6 right-6 z-20 flex items-center gap-4">
      <!-- Learn Split Button -->
      <div
        v-if="devices.length > 0"
        class="flex items-center rounded-full shadow-lg group text-white font-bold text-sm"
      >
        <button
          :disabled="!hasOnlineBridges || learn.active"
          class="flex items-center bg-purple-600 hover:bg-purple-700 disabled:bg-gray-500 disabled:cursor-not-allowed transition-colors duration-200 pl-4 pr-3 py-3 rounded-l-full border-r border-purple-500 disabled:border-gray-500"
          :title="t('devices.quickLearnTitle')"
          data-tour-id="quick-learn-button"
          @click="learnStore.startLearn"
        >
          <i class="mdi mdi-radio-tower text-xl" />
          <span class="max-w-0 group-hover:max-w-xs group-hover:ml-2 transition-all duration-300 overflow-hidden whitespace-nowrap">
            {{ learn.active ? t('learn.listeningBtn') : t('devices.quickLearn') }}
          </span>
        </button>
        <button
          class="bg-purple-600 hover:bg-purple-700 transition-colors duration-200 px-3 py-3 rounded-r-full"
          :title="t('devices.configureLearn')"
          data-tour-id="configure-learn-button"
          @click="showLearnModal = true"
        >
          <i class="mdi mdi-cog text-xl" />
        </button>
      </div>

      <!-- Add Device Button -->
      <button
        class="flex items-center bg-blue-600 text-white font-bold rounded-full shadow-lg hover:bg-blue-700 transition-all duration-300 ease-in-out px-4 py-3 group"
        data-tour-id="add-device-button"
        @click="openAddDeviceModal"
      >
        <i class="mdi mdi-plus text-xl transition-transform duration-300 group-hover:rotate-90" />
        <span class="max-w-0 group-hover:max-w-xs group-hover:ml-3 transition-all duration-300 ease-in-out overflow-hidden whitespace-nowrap">{{ t('devices.addDevice') }}</span>
      </button>
    </div>
  </div>
</template>
