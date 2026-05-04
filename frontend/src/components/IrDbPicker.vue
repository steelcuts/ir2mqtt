<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { storeToRefs } from 'pinia';
import Switch from './Switch.vue';
import BridgeSelector from './BridgeSelector.vue';
import { useIrdbStore } from '../stores/irdb';
import { useBridgeStore } from '../stores/bridges';
import IrCodeDetails from './IrCodeDetails.vue';
import { useI18n } from '../i18n';
import { getProtocolColor } from '../utils';
import type { IRButton } from '../types';

interface IrDbItem {
  name: string;
  path: string;
  type?: 'file' | 'dir';
}

const irdbStore = useIrdbStore();
const bridgeStore = useBridgeStore();

const { irdbStatus, irdbProgress } = storeToRefs(irdbStore);
const { onlineBridges, hasOnlineBridges } = storeToRefs(bridgeStore);

const props = defineProps({
  show: Boolean,
  selectionMode: {
    type: String,
    default: 'single'
  }
});

const emit = defineEmits(['close', 'select']);

const currentPath = ref('');
const items = ref<IrDbItem[]>([]);
const loading = ref(false);
const initialLoading = ref(false);
const selectedFileButtons = ref<IRButton[]>([]);
const viewingFile = ref<IrDbItem | null>(null);

const searchQuery = ref('');
const ignoreSearchWatcher = ref(false);
const searchResults = ref<IrDbItem[]>([]);
const showUpdateOptions = ref(false);
const updateFlipper = ref(false);
const updateProbono = ref(false);

const multiSelection = ref(new Set<number>());
const sendTargets = ref<string[]>([]);
const sendingButtonIndex = ref<number | null>(null);
const showTargetSelector = ref(false);

const { t } = useI18n();
let sendingTimeout: ReturnType<typeof setTimeout> | null = null;

const handleSend = (btn: IRButton, idx: number) => {
    if (sendingButtonIndex.value !== null) {
        return;
    }

    if (btn.code) {
        if (sendingTimeout) clearTimeout(sendingTimeout);
        sendingButtonIndex.value = idx;

        irdbStore.sendIrCode(btn.code, sendTargets.value)
            .finally(() => {
                sendingTimeout = setTimeout(() => {
                    sendingButtonIndex.value = null;
                }, 300);
            });
    } else {
        if (sendingTimeout) clearTimeout(sendingTimeout);
        sendingButtonIndex.value = null;
    }
}

const breadcrumbs = computed(() => {
    if (!currentPath.value) return [];
    const parts = currentPath.value.split('/');
    return parts.map((part, index) => ({
        name: part,
        path: parts.slice(0, index + 1).join('/')
    }));
});

const performSearch = async () => {
    if (!searchQuery.value || searchQuery.value.length < 2) {
        searchResults.value = [];
        return;
    }
    loading.value = true;
    try {
        searchResults.value = await irdbStore.searchIrdb(searchQuery.value) || [];
        viewingFile.value = null;
    } finally {
        loading.value = false;
    }
};

const loadPath = async (path: string) => {
    loading.value = true;
    try {
        items.value = await irdbStore.browseIrdb(path) || [];
        currentPath.value = path;
        viewingFile.value = null;
        selectedFileButtons.value = [];
    } finally {
        loading.value = false;
    }
};

const openItem = async (item: IrDbItem) => {
    const localItem = { ...item };
    if (!localItem.type && localItem.path) {
        localItem.type = 'file';
    }

    if (localItem.type === 'dir') {
        if (searchQuery.value) {
            // If searching, update path and clear search.
            currentPath.value = localItem.path;
            searchQuery.value = '';
        } else {
            loadPath(localItem.path);
        }
    } else {
        loading.value = true;
        try {
            selectedFileButtons.value = await irdbStore.loadIrdbFile(localItem.path) || [];
            viewingFile.value = localItem;
            if (searchQuery.value) {
                const dirPath = localItem.path.substring(0, localItem.path.lastIndexOf('/'));
                currentPath.value = dirPath;
                ignoreSearchWatcher.value = true;
                searchQuery.value = '';
                searchResults.value = [];
            }
            if (props.selectionMode === 'multi') {
                multiSelection.value = new Set(selectedFileButtons.value.map((_, i) => i));
            }
        } catch (e: unknown) {
            console.error("error_loading_ir_file", e);
            alert(`Error loading file: ${e instanceof Error ? e.message : "Unknown error"}`);
        } finally {
            loading.value = false;
        }
    }
};

const goUp = () => {
    if (viewingFile.value) {
        viewingFile.value = null;
        selectedFileButtons.value = [];
        return;
    }
    if (!currentPath.value) return;
    const parts = currentPath.value.split('/');
    parts.pop();
    loadPath(parts.join('/'));
};

const selectButton = (btn: IRButton, idx: number) => {
    if (props.selectionMode === 'multi') {
        const newSet = new Set(multiSelection.value);
        if (newSet.has(idx)) newSet.delete(idx);
        else newSet.add(idx);
        multiSelection.value = newSet;
    } else if (props.selectionMode === 'single') {
        emit('select', btn);
        emit('close');
    }
};

const toggleAll = () => {
    if (multiSelection.value.size === selectedFileButtons.value.length) {
        multiSelection.value = new Set();
    } else {
        multiSelection.value = new Set(selectedFileButtons.value.map((_, i) => i));
    }
};

const importSelection = () => {
    const selected = selectedFileButtons.value.filter((_, i) => multiSelection.value.has(i));
    emit('select', selected);
    emit('close');
};

const startUpdate = () => {
    irdbStore.updateIrdb({ flipper: updateFlipper.value, probono: updateProbono.value });
    showUpdateOptions.value = false;
};

let searchTimeout: ReturnType<typeof setTimeout> | null = null;

watch(searchQuery, (val) => {
    if (ignoreSearchWatcher.value) {
        ignoreSearchWatcher.value = false;
        return;
    }
    if (searchTimeout) clearTimeout(searchTimeout);

    if (!val) {
        searchResults.value = [];
        loadPath(currentPath.value);
    } else if (val.length >= 2) {
        searchTimeout = setTimeout(() => {
            performSearch();
        }, 300);
    } else {
        searchResults.value = [];
    }
});

watch(showUpdateOptions, (isShown) => {
  if (isShown) {
    updateFlipper.value = true;
    updateProbono.value = true;
  }
});

watch(() => props.show, (val) => {
    if (val) {
        initialLoading.value = true;
        irdbStore.fetchIrdbStatus().then(() => {
            initialLoading.value = false;
            if (irdbStatus.value.exists) {
                if (searchQuery.value) return;
                if (viewingFile.value) return;

                loadPath(currentPath.value || '');
            }
        });
    }
}, { immediate: true });

watch(irdbProgress, (val, oldVal) => {
    // When progress clears after an update, reload the current directory
    if (oldVal !== null && val === null && irdbStatus.value.exists) {
        loadPath(currentPath.value || '');
    }
});

onUnmounted(() => {
    if (sendingTimeout) clearTimeout(sendingTimeout);
    if (searchTimeout) clearTimeout(searchTimeout);
});

</script>

<template>
  <div
    v-if="show"
    class="fixed inset-0 !m-0 bg-gray-900/60 flex items-center justify-center z-[60] backdrop-blur-sm"
    @click.self="$emit('close')"
  >
    <div
      class="bg-gray-900 border border-gray-700 rounded-lg max-w-4xl w-full h-[80vh] flex flex-col shadow-2xl animate-in fade-in scale-95 duration-200"
      style="animation: slideInUp 0.3s ease-out;"
    >
      <div class="p-4 border-b border-gray-700 flex justify-between items-center shrink-0">
        <div class="flex items-center gap-4 flex-grow mr-4">
          <h3 class="text-lg font-semibold flex items-center gap-2 whitespace-nowrap">
            <i class="mdi mdi-database-search" /> {{ t('irdb.title') }}
          </h3>
          <div
            v-if="irdbStatus.exists && !irdbProgress"
            class="flex items-center flex-grow max-w-md bg-gray-800 border border-gray-600 rounded-full focus-within:border-gray-500 transition-colors"
            data-tour-id="irdb-search-input"
          >
            <i class="mdi mdi-magnify pl-3 pr-1 text-gray-500 shrink-0" />
            <input
              v-model="searchQuery"
              :placeholder="t('irdb.search')"
              class="w-full py-1.5 pr-4 text-sm bg-transparent border-0 focus:outline-none focus:ring-0 focus:shadow-none"
              @keyup.enter="performSearch"
            >
          </div>
        </div>
        <button
          v-if="irdbStatus.exists && !irdbProgress"
          class="text-xs btn btn-sm btn-secondary ml-auto mr-4"
          data-tour-id="irdb-update-options-btn"
          @click="showUpdateOptions = !showUpdateOptions"
        >
          <i class="mdi mdi-refresh" /> {{ t('irdb.update') }}
        </button>
        <button
          data-tour-id="irdb-close-btn"
          class="text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
          @click="$emit('close')"
        >
          <i class="mdi mdi-close text-xl" />
        </button>
      </div>

      <div class="flex-grow overflow-hidden flex flex-col p-4">
        <div
          v-if="initialLoading"
          class="flex-grow flex items-center justify-center h-full"
        >
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-ha-500" />
        </div>

        <div
          v-else-if="!irdbStatus.exists && !irdbProgress"
          class="flex flex-col items-center justify-center h-full text-center space-y-4"
          data-tour-id="irdb-no-db-message"
        >
          <i class="mdi mdi-database-off text-6xl text-gray-500" />
          <p class="text-gray-400">
            {{ t('irdb.noDb') }}
          </p>
            
          <div class="max-w-sm text-xs text-gray-500 bg-yellow-900/20 border border-yellow-700/50 p-3 rounded text-left space-y-2">
            <strong class="text-yellow-500 block">{{ t('irdb.disclaimerTitle') }}</strong>
            <p>{{ t('irdb.disclaimerText') }}</p>
            <p>
              {{ t('irdb.disclaimerWip') }} <a
                href="https://github.com/steelcuts/ir2mqtt/issues"
                target="_blank"
                rel="noopener noreferrer"
                class="text-yellow-400 underline hover:text-yellow-300"
              >{{ t('irdb.disclaimerIssueLink') }}</a>.
            </p>
          </div>

          <div class="bg-[var(--color-bg-tertiary)] p-4 rounded-lg text-left space-y-2 w-64">
            <label class="flex items-center justify-between cursor-pointer">
              <span>{{ t('irdb.flipperZero') }}</span>
              <Switch v-model="updateFlipper" />
            </label>
            <label class="flex items-center justify-between cursor-pointer">
              <span>{{ t('irdb.probono') }}</span>
              <Switch v-model="updateProbono" />
            </label>
          </div>

          <button
            class="btn btn-primary btn-sm disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!updateFlipper && !updateProbono"
            data-tour-id="irdb-download-button"
            @click="startUpdate"
          >
            <i class="mdi mdi-download" /> {{ t('irdb.download') }}
          </button>
        </div>

        <div
          v-if="showUpdateOptions && !irdbProgress"
          class="absolute inset-0 bg-gray-900/80 z-10 flex items-center justify-center backdrop-blur-sm"
          data-tour-id="irdb-update-options-overlay"
        >
          <div class="bg-gray-900 border border-gray-700 shadow-2xl rounded-lg w-80 p-6 space-y-4">
            <h3 class="font-semibold text-sm">
              {{ t('irdb.updateDatabases') }}
            </h3>
            <div class="space-y-2">
              <label class="flex items-center justify-between p-2 rounded hover:bg-gray-800 cursor-pointer">
                <span>{{ t('irdb.flipperZero') }}</span>
                <Switch v-model="updateFlipper" />
              </label>
              <label class="flex items-center justify-between p-2 rounded hover:bg-gray-800 cursor-pointer">
                <span>{{ t('irdb.probono') }}</span>
                <Switch v-model="updateProbono" />
              </label>
            </div>
            <div class="flex justify-end gap-2">
              <button
                class="btn btn-secondary btn-sm"
                @click="showUpdateOptions = false"
              >
                {{ t('confirm.cancel') }}
              </button>
              <button
                class="btn btn-primary btn-sm disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="!updateFlipper && !updateProbono"
                data-tour-id="irdb-confirm-update-btn"
                @click="startUpdate"
              >
                {{ t('irdb.update') }}
              </button>
            </div>
          </div>
        </div>

        <div
          v-if="!initialLoading && irdbProgress"
          class="flex flex-col items-center justify-center h-full text-center space-y-6 p-8"
        >
          <div
            v-if="irdbProgress.percent != null"
            class="w-full max-w-md space-y-2"
          >
            <div class="flex justify-between text-sm font-bold text-gray-300">
              <span>{{ irdbProgress.message }}</span>
              <span>{{ irdbProgress.percent }}%</span>
            </div>
            <div class="w-full bg-gray-700 rounded-full h-2.5 overflow-hidden">
              <div
                class="bg-ha-500 h-2.5 rounded-full transition-all duration-300 ease-out"
                :style="{ width: irdbProgress.percent + '%' }"
              />
            </div>
            <p class="text-xs text-gray-500 capitalize">
              {{ irdbProgress.status }}...
            </p>
          </div>
            
          <div
            v-else
            class="flex flex-col items-center space-y-4"
          >
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-ha-500" />
            <div>
              <h3 class="font-semibold text-sm">
                {{ irdbProgress.message }}
              </h3>
              <p class="text-sm text-gray-400 capitalize">
                {{ irdbProgress.status }}...
              </p>
            </div>
          </div>
        </div>

        <div
          v-else-if="!initialLoading && irdbStatus.exists"
          class="flex flex-col h-full"
        >
          <div
            v-if="!searchQuery"
            class="flex items-center gap-2 mb-4 text-sm overflow-x-auto whitespace-nowrap pb-2 shrink-0"
          >
            <button
              class="hover:text-ha-500 shrink-0"
              :class="!currentPath ? 'font-bold text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'"
              @click="loadPath('')"
            >
              <i class="mdi mdi-home" />
            </button>
            <template
              v-for="crumb in breadcrumbs"
              :key="crumb.path"
            >
              <span class="text-[var(--color-text-secondary)] shrink-0">/</span>
              <button
                class="hover:text-ha-500 text-[var(--color-text-secondary)] shrink-0"
                @click="loadPath(crumb.path)"
              >
                {{ crumb.name }}
              </button>
            </template>
            <template v-if="viewingFile">
              <span class="text-[var(--color-text-secondary)] shrink-0">/</span>
              <span class="font-bold text-[var(--color-text-primary)] shrink-0">{{ viewingFile.name }}</span>
            </template>
          </div>

          <div
            v-if="!searchQuery && (currentPath || viewingFile)"
            class="mb-2 shrink-0 flex justify-between items-center relative"
          >
            <button
              class="text-xs flex items-center gap-1 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
              @click="goUp"
            >
              <i class="mdi mdi-arrow-left" /> {{ t('irdb.back') }}
            </button>

            <div
              v-if="viewingFile"
              class="relative"
            >
              <button
                data-tour-id="target-selector-btn"
                class="text-xs flex items-center gap-1 px-2 py-1.5 rounded bg-gray-800 hover:bg-gray-700 border border-gray-600 transition-colors"
                :class="sendTargets.length > 0 ? 'text-green-400' : (hasOnlineBridges ? 'text-gray-400' : 'text-red-400')"
                @click="showTargetSelector = !showTargetSelector"
              >
                <span v-if="sendTargets.length === 0"><i class="mdi mdi-alert-circle-outline mr-0.5" />{{ hasOnlineBridges ? t('irdb.noTargetSelected') : t('learn.noBridges') }}</span>
                <span v-else><i class="mdi mdi-upload mr-0.5" />{{ sendTargets.length }} target{{ sendTargets.length > 1 ? 's' : '' }}</span>
                <i class="mdi mdi-chevron-down ml-1" />
              </button>

              <div
                v-if="showTargetSelector"
                class="fixed inset-0 z-40"
                @click="showTargetSelector = false"
              />
              <div
                v-if="showTargetSelector"
                class="absolute right-0 top-full mt-2 w-96 bg-gray-800 border border-gray-600 rounded-lg shadow-2xl z-50 p-3 text-left"
              >
                <BridgeSelector
                  v-if="hasOnlineBridges"
                  v-model="sendTargets"
                  :bridges="onlineBridges"
                  type="target"
                  :compact="true"
                />
                <p
                  v-else
                  class="text-xs text-gray-500 italic py-1"
                >
                  {{ t('irdb.sendDisabled') }}
                </p>
              </div>
            </div>
          </div>

          <div
            v-if="loading"
            class="flex-grow flex items-center justify-center"
          >
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-ha-500" />
          </div>

          <div
            v-else-if="searchQuery"
            class="flex-grow overflow-y-auto space-y-1 pr-1 min-h-0"
          >
            <div
              v-for="item in searchResults"
              :key="item.path"
              class="flex items-center gap-3 p-3 rounded-lg bg-gray-800 border border-gray-600 cursor-pointer transition-all group hover:bg-gray-700"
              @click="openItem(item)"
            >
              <i class="mdi mdi-file-document-outline text-2xl text-blue-400 group-hover:scale-110 transition-transform" />
              <div class="flex flex-col overflow-hidden">
                <span class="text-[var(--color-text-primary)] font-medium truncate">{{ item.name }}</span>
                <span class="text-xs text-[var(--color-text-secondary)] truncate">{{ item.path }}</span>
              </div>
            </div>
            <div
              v-if="searchResults.length === 0 && !loading"
              class="text-center text-gray-500 mt-10"
            >
              {{ t('irdb.noResults') }}
            </div>
          </div>

          <div
            v-else-if="!viewingFile"
            class="flex-grow overflow-y-auto space-y-1 pr-1 min-h-0"
            data-tour-id="irdb-file-list"
          >
            <div
              v-for="item in items"
              :key="item.path" 
              class="flex items-center gap-3 p-3 rounded-lg bg-gray-800 border border-gray-600 cursor-pointer transition-all group hover:bg-gray-700"
              @click="openItem(item)"
            >
              <i
                class="mdi text-2xl transition-transform group-hover:scale-110"
                :class="item.type === 'dir' ? 'mdi-folder text-yellow-500' : 'mdi-file-document-outline text-blue-400'"
              />
              <span class="text-[var(--color-text-primary)] font-medium">{{ item.name }}</span>
              <i
                v-if="item.type === 'dir'"
                class="mdi mdi-chevron-right ml-auto text-[var(--color-text-secondary)]"
              />
            </div>
          </div>

          <div
            v-else
            class="flex-grow flex flex-col min-h-0"
          >
            <div
              v-if="selectionMode === 'multi'"
              class="p-3 border-b border-gray-700 flex justify-between items-center bg-gray-900 shrink-0"
            >
              <div class="flex items-center gap-2">
                <label class="flex items-center gap-2 cursor-pointer text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] select-none">
                  <input
                    type="checkbox" 
                    :checked="multiSelection.size === selectedFileButtons.length && selectedFileButtons.length > 0"
                    class="rounded border-gray-600 bg-gray-700 text-ha-500 focus:ring-offset-0 focus:ring-1 focus:ring-ha-500"
                    @change="toggleAll"
                  >
                  {{ t('irdb.selectAll', { count: multiSelection.size }) }}
                </label>
                <button
                  class="btn btn-xs btn-primary"
                  :disabled="multiSelection.size === 0"
                  @click="importSelection"
                >
                  {{ t('irdb.import') }}
                </button>
              </div>
            </div>

            <div class="flex-grow overflow-y-auto grid grid-cols-1 sm:grid-cols-2 gap-3 content-start p-1">
              <div
                v-for="(btn, idx) in selectedFileButtons"
                :key="idx"
                class="group relative p-3 bg-gray-800 border border-gray-600 rounded-lg transition-all flex flex-col"
                :class="[
                  selectionMode !== 'browse' ? 'cursor-pointer' : '',
                  selectionMode === 'multi' && multiSelection.has(idx) ? 'bg-ha-500/10' : 'hover:bg-gray-700'
                ]"
                :data-tour-id="idx === 0 ? 'irdb-first-button' : undefined"
                @click="selectButton(btn, idx)"
              >
                <div class="flex justify-between items-start mb-1">
                  <div class="flex items-center gap-2 overflow-hidden">
                    <div class="relative w-8 h-8 flex items-center justify-center shrink-0">
                      <i
                        class="mdi text-2xl text-[var(--color-text-secondary)] transition-all duration-200"
                        :class="[`mdi-${btn.icon || 'remote'}`, (hasOnlineBridges && btn.code?.protocol) ? 'group-hover:opacity-0 group-hover:scale-50' : '']"
                      />
                      <button
                        v-if="hasOnlineBridges && btn.code?.protocol"
                        class="absolute inset-0 flex items-center justify-center rounded-full transition-all duration-200 opacity-0 scale-50 group-hover:opacity-100 group-hover:scale-100"
                        :class="sendTargets.length > 0
                          ? 'hover:bg-[var(--color-bg-secondary)] text-ha-500'
                          : 'cursor-not-allowed text-gray-500'"
                        :title="sendTargets.length > 0 ? t('devices.triggerButton') : t('irdb.selectTargetFirst')"
                        :disabled="sendTargets.length === 0"
                        @click.stop="handleSend(btn, idx)"
                      >
                        <i
                          class="mdi text-xl"
                          :class="sendingButtonIndex === idx ? 'mdi-loading mdi-spin' : 'mdi-send'"
                        />
                      </button>
                    </div>
                    <span class="font-bold text-[var(--color-text-primary)] truncate">{{ btn.name }}</span>
                  </div>
                  <span
                    class="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded border bg-gray-900 font-mono shrink-0"
                    :class="getProtocolColor(btn.code?.protocol)"
                  >{{ btn.code?.protocol || 'N/A' }}</span>
                </div>
                <div class="mt-auto overflow-hidden">
                  <IrCodeDetails :code="btn.code" />
                </div>

                <div
                  v-if="selectionMode === 'multi'"
                  class="absolute bottom-3 right-3"
                >
                  <input
                    type="checkbox"
                    :checked="multiSelection.has(idx)"
                    class="rounded border-gray-600 bg-gray-700 text-ha-500 focus:ring-offset-0 focus:ring-1 focus:ring-ha-500 pointer-events-none"
                  >
                </div>
              </div>
              <div
                v-if="selectedFileButtons.length === 0"
                class="col-span-full text-center text-gray-500 py-8 flex flex-col items-center"
              >
                <i class="mdi mdi-file-remove-outline text-4xl mb-2 opacity-50" />
                {{ t('irdb.noValidButtons') }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
    
<style scoped>
@keyframes slideInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
    