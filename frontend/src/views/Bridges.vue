<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { storeToRefs } from 'pinia';
import Switch from '../components/Switch.vue';
import AddSerialBridgeModal from '../components/AddSerialBridgeModal.vue';
import { useBridgeStore } from '../stores/bridges';
import { useCommonStore } from '../stores/common';
import IrCodeDetails from '../components/IrCodeDetails.vue';
import { useI18n } from '../i18n';
import type { Bridge, BridgeSettings } from '../types';

const bridgeStore = useBridgeStore();
const commonStore = useCommonStore();
const { bridges, ignoredBridgeIds } = storeToRefs(bridgeStore);

const visibleIgnoredBridgeIds = computed(() => ignoredBridgeIds.value.filter(id => !id.startsWith('serial:')));

const { t } = useI18n();

const showIgnoredPopover = ref(false);
const ignoredPopoverRef = ref<HTMLElement | null>(null);

const handleOutsideClick = (e: MouseEvent) => {
    if (ignoredPopoverRef.value && !ignoredPopoverRef.value.contains(e.target as Node)) {
        showIgnoredPopover.value = false;
    }
};

onMounted(() => {
    bridgeStore.fetchIgnoredBridges();
    document.addEventListener('click', handleOutsideClick, true);
});

onUnmounted(() => {
    document.removeEventListener('click', handleOutsideClick, true);
});

const expandedBridges = reactive(new Set());
const expandedProtocols = reactive(new Set());
const expandedSettings = reactive(new Set());
const settingsMap = reactive(new Map<string, BridgeSettings>());
const showAddSerialBridgeModal = ref(false);

const pulsingBridges = reactive(new Map<string, number>());

watch(() => bridges.value, (newBridges, oldBridges) => {
    if (!oldBridges) return;
    newBridges.forEach(nb => {
        const ob = oldBridges.find(b => b.id === nb.id);
        if (!ob || ob.last_seen !== nb.last_seen || ob.status !== nb.status) {
            if (pulsingBridges.has(nb.id)) {
                clearTimeout(pulsingBridges.get(nb.id));
                    pulsingBridges.delete(nb.id);
            }
                nextTick(() => {
                    const timerId = window.setTimeout(() => {
                        pulsingBridges.delete(nb.id);
                    }, 800);
                    pulsingBridges.set(nb.id, timerId);
                });
        }
    });
});

const toggleProtocolPanel = (id: string) => {
    if (expandedProtocols.has(id)) {
        expandedProtocols.delete(id);
    } else {
        expandedProtocols.add(id);
    }
};

const defaultSettings = (): BridgeSettings => ({
    echo_enabled: false,
    echo_timeout: 500,
    echo_smart: true,
    echo_ignore_self: true,
    echo_ignore_others: false,
});

const toggleSettingsPanel = (bridge: Bridge) => {
    if (expandedSettings.has(bridge.id)) {
        expandedSettings.delete(bridge.id);
    } else {
        settingsMap.set(bridge.id, { ...defaultSettings(), ...(bridge.settings || {}) });
        expandedSettings.add(bridge.id);
    }
};

const saveSettings = async (bridge: Bridge) => {
    const s = settingsMap.get(bridge.id);
    if (!s) return;
    await bridgeStore.updateBridgeSettings(bridge.id, s);
    await bridgeStore.fetchBridges();
    expandedSettings.delete(bridge.id);
    commonStore.addFlashMessage('Bridge settings saved.', 'success');
};

const toggleProtocol = async (bridge: Bridge, protocol: string, event: MouseEvent) => {
    const pendingId = `${bridge.id}:${protocol}`;
    if (bridgeStore.pendingProtocols.has(pendingId)) return;

    const currentEnabled: string[] = bridge.enabled_protocols || [];
    let newEnabled;
    
    if (event && event.shiftKey) {
        if (currentEnabled.includes(protocol)) {
            // Invert exclusive: Enable all others, disable this one
            newEnabled = (bridge.capabilities || []).filter(p => p !== protocol);
        } else {
            // Exclusive enable: Enable only this one
            newEnabled = [protocol];
        }
    } else {
        if (currentEnabled.includes(protocol)) {
            newEnabled = currentEnabled.filter(p => p !== protocol);
        } else {
            newEnabled = [...currentEnabled, protocol];
        }
    }
    
    bridgeStore.pendingProtocols.add(pendingId);
    try {
        await bridgeStore.updateBridgeProtocols(bridge.id, newEnabled);
    } finally {
        bridgeStore.pendingProtocols.delete(pendingId);
    }
};

const toggleExpand = (id: string) => {
    if (expandedBridges.has(id)) {
        expandedBridges.delete(id);
    } else {
        expandedBridges.add(id);
    }
};

const formatRelativeTime = (ts: number) => {
    if (!ts) return '';
    const diff = Math.round(Date.now() / 1000 - ts);
    if (diff < 60)  return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return new Date(ts * 1000).toLocaleTimeString();
};

const formatAbsoluteTime = (ts: number) => {
    if (!ts) return '';
    return new Date(ts * 1000).toLocaleString();
};
</script>

<template>
  <div class="space-y-4 pb-20">
    <!-- Bridge cards -->
    <div
      v-if="bridges.length > 0"
      class="grid grid-cols-1 gap-4 items-start"
      data-tour-id="bridges-table"
    >
      <div
        v-for="(bridge) in bridges"
        :key="bridge.id"
        class="card flex flex-col gap-0 overflow-hidden p-0"
      >
        <!-- Header -->
        <div class="flex items-center gap-3 px-4 py-3 border-b border-gray-700">
          <!-- Status -->
          <span
            class="shrink-0 origin-center"
            :class="[
              bridge.status === 'online' ? 'text-green-400' : bridge.status === 'connecting' ? 'text-yellow-400' : 'text-red-400',
              pulsingBridges.has(bridge.id) ? 'bridge-pulse' : ''
            ]"
            data-tour-id="bridge-status"
          >
            <i :class="bridge.status === 'connecting' ? 'mdi mdi-circle-outline mdi-spin text-xs' : 'mdi mdi-circle text-xs'" />
          </span>
          <!-- Name -->
          <div
            class="flex-1 min-w-0"
            data-tour-id="bridge-info"
          >
            <span class="font-bold text-base truncate block">{{ bridge.name }}</span>
            <span
              class="text-xs font-mono"
              :class="bridge.status === 'connecting' ? 'text-yellow-500' : 'text-gray-500'"
            >
              {{ bridge.status === 'connecting' ? `${t('bridges.connecting')} (${bridge.serial_port})` : bridge.id }}
            </span>
          </div>
          <!-- Actions -->
          <div
            class="flex items-center gap-1 shrink-0"
            data-tour-id="bridge-actions"
          >
            <template v-if="bridge.status !== 'connecting'">
              <button
                class="p-1.5 rounded hover:bg-gray-700 transition-colors"
                :class="expandedProtocols.has(bridge.id) ? 'text-blue-400' : 'text-gray-500 hover:text-gray-200'"
                :title="t('bridges.protocolsTitle')"
                data-tour-id="bridge-protocols"
                @click="toggleProtocolPanel(bridge.id)"
              >
                <i class="mdi mdi-tune text-lg" />
              </button>
              <button
                class="p-1.5 rounded hover:bg-gray-700 transition-colors"
                :class="expandedSettings.has(bridge.id) ? 'text-blue-400' : 'text-gray-500 hover:text-blue-400'"
                :title="t('bridges.echoSettingsTitle')"
                data-tour-id="bridge-edit-btn"
                @click="toggleSettingsPanel(bridge)"
              >
                <i class="mdi mdi-cog-outline text-lg" />
              </button>
              <button
                class="p-1.5 rounded hover:bg-gray-700 transition-colors"
                :class="expandedBridges.has(bridge.id) ? 'text-blue-400' : 'text-gray-500 hover:text-gray-200'"
                :title="expandedBridges.has(bridge.id) ? t('bridges.hideHistory') : t('bridges.showHistory')"
                data-tour-id="bridge-history-btn"
                @click="toggleExpand(bridge.id)"
              >
                <i class="mdi mdi-history text-lg" />
              </button>
              <span class="w-px h-4 bg-gray-700 mx-0.5" />
            </template>
            <button
              class="p-1.5 rounded hover:bg-gray-700 text-gray-500 hover:text-yellow-400 transition-colors"
              :title="t('bridges.ignoreBridge')"
              @click="bridgeStore.ignoreBridge(bridge.id, $event)"
            >
              <i class="mdi mdi-eye-off-outline text-lg" />
            </button>
            <button
              class="p-1.5 rounded hover:bg-gray-700 text-gray-500 hover:text-red-400 transition-colors"
              :title="t('bridges.deleteBridge')"
              data-tour-id="bridge-delete-btn"
              @click="bridgeStore.deleteBridge(bridge.id, $event)"
            >
              <i class="mdi mdi-delete-outline text-lg" />
            </button>
          </div>
        </div>

        <!-- Meta row -->
        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-xs text-gray-400">
          <!-- Connection -->
          <span class="flex items-center gap-1">
            <i
              class="text-gray-500 mdi"
              :class="bridge.connection_type === 'serial' ? 'mdi-usb' : bridge.network_type === 'ethernet' ? 'mdi-ethernet' : 'mdi-wifi'"
            />
            <span class="font-mono">{{ bridge.connection_type === 'serial' ? (bridge.serial_port || 'Serial') : (bridge.ip || 'N/A') }}</span>
          </span>
          <!-- Channels -->
          <span class="flex items-center gap-2 text-gray-500">
            <span
              :title="t('bridges.rxChannels')"
              class="flex items-center gap-0.5"
            ><i class="mdi mdi-arrow-down text-[10px]" />{{ bridge.receivers?.length || 1 }} RX</span>
            <span
              :title="t('bridges.txChannels')"
              class="flex items-center gap-0.5"
            ><i class="mdi mdi-arrow-up text-[10px]" />{{ bridge.transmitters?.length || 1 }} TX</span>
          </span>
          <!-- Version -->
          <span class="font-mono text-gray-500">{{ bridge.version || 'N/A' }}</span>
          <!-- Protocols summary -->
          <span
            v-if="bridge.capabilities?.length"
            class="ml-auto font-mono"
          >
            <span class="text-gray-200 font-semibold">{{ (bridge.enabled_protocols || []).length }}</span>
            <span class="text-gray-500">/{{ bridge.capabilities.length }}</span>
            <span class="text-gray-500 ml-1">{{ t('bridges.protocols') }}</span>
          </span>
          <!-- Last seen -->
          <span
            class="text-gray-500"
            :title="bridge.last_seen ? new Date(bridge.last_seen).toLocaleString() : ''"
          >{{ bridge.last_seen ? formatRelativeTime(new Date(bridge.last_seen).getTime() / 1000) : t('bridges.never') }}</span>
        </div>

        <!-- Protocols panel -->
        <div
          v-if="expandedProtocols.has(bridge.id)"
          class="border-t border-gray-700 px-4 py-3"
        >
          <p class="text-[10px] text-gray-500 mb-2 uppercase tracking-wide">
            {{ t('bridges.toggleHint') }}
          </p>
          <div class="flex flex-wrap gap-1.5">
            <div
              v-for="cap in bridge.capabilities"
              :key="cap"
              class="relative"
            >
              <span
                :title="t('bridges.toggleHintShort')"
                class="flex items-center justify-center gap-1 px-2 py-1 rounded text-[10px] uppercase border transition-colors select-none"
                :class="[
                  bridgeStore.pendingProtocols.has(`${bridge.id}:${cap}`) || bridge.status !== 'online' ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
                  (bridge.enabled_protocols || []).includes(cap)
                    ? 'bg-green-900/30 text-green-400 border-green-700 hover:bg-green-900/50'
                    : 'bg-gray-800 text-gray-500 border-gray-700 hover:bg-gray-700'
                ]"
                @click="bridge.status === 'online' && !bridgeStore.pendingProtocols.has(`${bridge.id}:${cap}`) ? toggleProtocol(bridge, cap, $event) : null"
              >
                <i
                  v-if="bridgeStore.pendingProtocols.has(`${bridge.id}:${cap}`)"
                  class="absolute mdi mdi-loading mdi-spin text-xs"
                />
                <span :class="{ 'opacity-0': bridgeStore.pendingProtocols.has(`${bridge.id}:${cap}`) }">{{ cap }}</span>
              </span>
            </div>
          </div>
        </div>

        <!-- Echo suppression panel -->
        <div
          v-if="expandedSettings.has(bridge.id) && settingsMap.get(bridge.id)"
          class="border-t border-gray-700 px-4 py-3 space-y-2"
          data-tour-id="bridge-settings-panel"
        >
          <label class="flex items-center justify-between cursor-pointer py-1 rounded hover:bg-gray-800/50 transition-colors">
            <div>
              <span class="font-semibold text-sm">{{ t('bridges.settings.echoSuppression') }}</span>
              <p class="text-xs text-gray-500">{{ t('bridges.settings.echoDesc') }}</p>
            </div>
            <Switch v-model="settingsMap.get(bridge.id)!.echo_enabled" />
          </label>
          <div
            v-if="settingsMap.get(bridge.id)!.echo_enabled"
            class="pl-3 border-l-2 border-gray-700 space-y-2"
          >
            <div class="py-1">
              <label class="block text-xs font-medium text-gray-400 mb-1">{{ t('bridges.settings.timeout') }}</label>
              <input
                v-model.number="settingsMap.get(bridge.id)!.echo_timeout"
                type="number"
                class="w-32 rounded p-1.5 bg-gray-900 border border-gray-600 text-sm"
                min="50"
                step="50"
              >
            </div>
            <label class="flex items-center justify-between cursor-pointer py-1 rounded hover:bg-gray-800/50 transition-colors">
              <span class="text-sm">{{ t('bridges.settings.smartMode') }}</span>
              <Switch v-model="settingsMap.get(bridge.id)!.echo_smart" />
            </label>
            <label class="flex items-center justify-between cursor-pointer py-1 rounded hover:bg-gray-800/50 transition-colors">
              <span class="text-sm">{{ t('bridges.settings.ignoreSelf') }}</span>
              <Switch v-model="settingsMap.get(bridge.id)!.echo_ignore_self" />
            </label>
            <label class="flex items-center justify-between cursor-pointer py-1 rounded hover:bg-gray-800/50 transition-colors">
              <span class="text-sm">{{ t('bridges.settings.ignoreOthers') }}</span>
              <Switch v-model="settingsMap.get(bridge.id)!.echo_ignore_others" />
            </label>
          </div>
          <div class="flex justify-end gap-2 pt-1">
            <button
              class="btn btn-secondary btn-sm"
              @click="expandedSettings.delete(bridge.id)"
            >
              {{ t('confirm.cancel') }}
            </button>
            <button
              class="btn btn-primary btn-sm"
              @click="saveSettings(bridge)"
            >
              {{ t('bridges.settings.save') }}
            </button>
          </div>
        </div>

        <!-- History panel -->
        <div
          v-if="expandedBridges.has(bridge.id)"
          class="border-t border-gray-700 grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-700"
        >
          <!-- Received -->
          <div class="px-4 py-3">
            <h4 class="text-xs font-bold text-purple-400 uppercase mb-2 flex items-center gap-2">
              <i class="mdi mdi-arrow-down-circle" />
              {{ t('bridges.received') }}
              <span class="ml-auto font-normal text-gray-500 normal-case">{{ bridge.last_received?.length || 0 }} {{ t('bridges.codes') }}</span>
            </h4>
            <div class="bg-gray-900 rounded border border-gray-700 overflow-hidden">
              <div
                v-if="!bridge.last_received?.length"
                class="p-3 text-xs text-gray-500 text-center italic"
              >
                {{ t('bridges.noReceived') }}
              </div>
              <div
                v-else
                class="max-h-48 overflow-y-auto divide-y divide-gray-800"
              >
                <div
                  v-for="(code, i) in bridge.last_received"
                  :key="i"
                  class="px-3 py-2 hover:bg-gray-800/40 transition-colors"
                >
                  <IrCodeDetails
                    :code="code"
                    show-protocol
                  >
                    <template #header-extra>
                      <span
                        v-if="code.ignored"
                        class="text-[9px] px-1.5 py-0.5 rounded bg-gray-800 text-yellow-500 border border-yellow-600 flex items-center gap-1"
                        :title="t('bridges.ignoredEcho')"
                      ><i class="mdi mdi-volume-variant-off text-[8px]" />{{ t('bridges.ignoredBadge') }}</span>
                      <span
                        v-if="code.receiver_id"
                        class="text-[9px] px-1.5 py-0.5 rounded bg-gray-800 text-purple-400 border border-purple-500 flex items-center gap-1"
                      ><i class="mdi mdi-download text-[8px]" />{{ code.receiver_id }}</span>
                      <span
                        class="ml-auto text-[10px] text-gray-500"
                        :title="formatAbsoluteTime(code.timestamp)"
                      >{{ formatRelativeTime(code.timestamp) }}</span>
                    </template>
                  </IrCodeDetails>
                </div>
              </div>
            </div>
          </div>

          <!-- Sent -->
          <div class="px-4 py-3">
            <h4 class="text-xs font-bold text-blue-400 uppercase mb-2 flex items-center gap-2">
              <i class="mdi mdi-arrow-up-circle" />
              {{ t('bridges.sent') }}
              <span class="ml-auto font-normal text-gray-500 normal-case">{{ bridge.last_sent?.length || 0 }} {{ t('bridges.codes') }}</span>
            </h4>
            <div class="bg-gray-900 rounded border border-gray-700 overflow-hidden">
              <div
                v-if="!bridge.last_sent?.length"
                class="p-3 text-xs text-gray-500 text-center italic"
              >
                {{ t('bridges.noSent') }}
              </div>
              <div
                v-else
                class="max-h-48 overflow-y-auto divide-y divide-gray-800"
              >
                <div
                  v-for="(code, i) in bridge.last_sent"
                  :key="i"
                  class="px-3 py-2 hover:bg-gray-800/40 transition-colors"
                >
                  <IrCodeDetails
                    :code="code"
                    show-protocol
                  >
                    <template #header-extra>
                      <template v-if="code.channel">
                        <span
                          v-for="ch in (Array.isArray(code.channel) ? code.channel : [code.channel])"
                          :key="ch"
                          class="text-[9px] px-1.5 py-0.5 rounded bg-gray-800 text-blue-400 border border-blue-400 flex items-center gap-1"
                        ><i class="mdi mdi-upload text-[8px]" />{{ ch }}</span>
                      </template>
                      <span
                        class="ml-auto text-[10px] text-gray-500"
                        :title="formatAbsoluteTime(code.timestamp)"
                      >{{ formatRelativeTime(code.timestamp) }}</span>
                    </template>
                  </IrCodeDetails>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-else
      class="text-center text-gray-500 mt-10"
      data-tour-id="no-bridges-message"
    >
      <i class="mdi mdi-lan-disconnect text-6xl mb-2" />
      <p class="font-bold">
        {{ t('bridges.noBridges') }}
      </p>
      <p class="text-sm">
        {{ t('bridges.noBridgesDesc') }}
      </p>
    </div>

    <AddSerialBridgeModal
      :show="showAddSerialBridgeModal"
      @close="showAddSerialBridgeModal = false"
    />

    <!-- BOTTOM BUTTONS -->
    <div class="fixed bottom-6 right-6 z-20 flex items-end gap-3">
      <!-- Ignored bridges button + click popover -->
      <div
        v-if="visibleIgnoredBridgeIds.length > 0"
        ref="ignoredPopoverRef"
        class="relative flex flex-col items-end"
      >
        <!-- Popover -->
        <div
          v-if="showIgnoredPopover"
          class="absolute bottom-full mb-2 right-0 w-72 bg-gray-800 border border-gray-700 rounded-xl shadow-2xl p-3 space-y-1"
        >
          <p class="text-xs text-gray-500 px-1 pb-1">
            {{ t('bridges.ignoredBridges') }}
          </p>
          <div
            v-for="id in visibleIgnoredBridgeIds"
            :key="id"
            class="flex items-center justify-between gap-2 py-1.5 px-2 rounded-lg bg-gray-900 text-xs"
          >
            <span class="font-mono text-gray-300 truncate">{{ id }}</span>
            <button
              class="shrink-0 text-gray-500 hover:text-green-400 transition-colors"
              :title="t('bridges.unignore')"
              @click="bridgeStore.unignoreBridge(id)"
            >
              <i class="mdi mdi-eye-outline text-base" />
            </button>
          </div>
        </div>
        <!-- Button -->
        <button
          class="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 text-gray-300 hover:text-gray-200 rounded-full shadow-lg transition-all duration-200 px-4 py-3"
          :class="showIgnoredPopover ? 'bg-gray-600 text-gray-200' : ''"
          @click="showIgnoredPopover = !showIgnoredPopover"
        >
          <i class="mdi mdi-eye-off-outline text-xl" />
          <span class="text-sm font-semibold">{{ visibleIgnoredBridgeIds.length }}</span>
        </button>
      </div>

      <!-- Add Serial Bridge button -->
      <div class="group">
        <button
          class="flex items-center bg-blue-600 text-white font-bold rounded-full shadow-lg hover:bg-blue-700 transition-all duration-300 ease-in-out px-4 py-3"
          :title="t('bridges.addSerialBridge')"
          data-tour-id="add-serial-bridge-btn"
          @click="showAddSerialBridgeModal = true"
        >
          <i class="mdi mdi-plus text-2xl transition-transform duration-300 group-hover:rotate-90" />
          <span class="max-w-0 group-hover:max-w-xs group-hover:ml-3 transition-all duration-300 ease-in-out overflow-hidden whitespace-nowrap">{{ t('bridges.addSerialBridge') }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes bridge-pulse-anim {
  0% {
    transform: scale(1);
    filter: brightness(1);
  }
  15% {
    transform: scale(1.4);
    filter: brightness(1.5);
  }
  100% {
    transform: scale(1);
    filter: brightness(1);
  }
}
.bridge-pulse {
  animation: bridge-pulse-anim 0.8s cubic-bezier(0.2, 0, 0, 1) forwards;
}
</style>
