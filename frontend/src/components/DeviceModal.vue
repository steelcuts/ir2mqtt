<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { storeToRefs } from 'pinia';
import BridgeSelector from './BridgeSelector.vue';
import IconPicker from './IconPicker.vue';
import IrDbPicker from './IrDbPicker.vue';
import { useDeviceStore } from '../stores/devices';
import { useSettingsStore } from '../stores/settings';
import { api } from '../services/api';
import { deviceTemplates } from '../templates';
import { sanitizeNameForImport } from '../utils';
import { startDeviceModalTour } from '../tour';
import { useI18n } from '../i18n';
import { IRDevice, IRButton, Bridge } from '../types';

interface Props {
  show: boolean;
  device?: IRDevice | null;
  bridges: Bridge[];
}

const props = withDefaults(defineProps<Props>(), {
  show: false,
  device: null,
  bridges: () => [],
});

const emit = defineEmits(['close', 'device-created']);

const deviceStore = useDeviceStore();
const settingsStore = useSettingsStore();

const { devices, newDevice } = storeToRefs(deviceStore);
const { appMode, topicStyle } = storeToRefs(settingsStore);

const localDevice = ref<Partial<IRDevice> | null>(null);
const selectedTemplateId = ref('');
const importedButtons = ref<IRButton[]>([]);
const showDbPicker = ref(false);
const isEditMode = computed(() => !!props.device);

const { t } = useI18n();
const selectedTemplate = computed(() => deviceTemplates.find(t => t.id === selectedTemplateId.value));

watch(() => props.show, (newVal) => {
  if (newVal) {
    if (isEditMode.value && props.device) {
        // Deep copy the device object to allow for local edits.
        localDevice.value = JSON.parse(JSON.stringify(props.device));
        if (localDevice.value) {
            if (!localDevice.value.target_bridges) {
                localDevice.value.target_bridges = [];
            } else {
                const existingBridgeIds = new Set(props.bridges.map(b => b.id));
                localDevice.value.target_bridges = localDevice.value.target_bridges.filter((id: string) => existingBridgeIds.has(id.split(':')[0]));
            }
            if (!localDevice.value.allowed_bridges) {
                localDevice.value.allowed_bridges = [];
            } else {
                const existingBridgeIds = new Set(props.bridges.map(b => b.id));
                localDevice.value.allowed_bridges = localDevice.value.allowed_bridges.filter((id: string) => id === 'any' || existingBridgeIds.has(id.split(':')[0]));
            }
        }
    } else {
        localDevice.value = {
            name: '',
            icon: 'remote-tv',
            target_bridges: [],
            allowed_bridges: []
        };
        selectedTemplateId.value = '';
        importedButtons.value = [];
    }
    document.addEventListener('keydown', onEscape);
  } else {
    document.removeEventListener('keydown', onEscape);
  }
});

watch(selectedTemplateId, (newId) => {
  if (!newId) return;
  importedButtons.value = [];
  const template = deviceTemplates.find(t => t.id === newId);
  const device = localDevice.value;
  if (template && device) {
      const isTemplateName = deviceTemplates.some(t => t.name === device.name);
      if (!device.name || isTemplateName) {
          device.name = template.name;
      }
      const isTemplateIcon = deviceTemplates.some(t => t.icon === device.icon || `mdi-${t.icon}` === device.icon);
      if (!device.icon || isTemplateIcon || (device.icon && device.icon.startsWith('mdi-')) || device.icon === 'remote-tv') {
           device.icon = template.icon;
      }
  }
});

const deviceIcon = computed({
    get: () => localDevice.value?.icon || '',
    set: (val) => {
        if (localDevice.value) {
            localDevice.value.icon = val;
        }
    }
});

const closeModal = () => {
  emit('close');
};

const onEscape = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    closeModal();
  }
};

const onDbButtonsSelected = (buttons: IRButton[]) => {
    if (buttons && buttons.length > 0) {
        const usedNames = new Set<string>();
        const uniqueButtons = buttons.map((btn) => {
            let name = btn.name.trim();

            if (appMode.value === 'standalone' && topicStyle.value === 'name') {
                name = sanitizeNameForImport(name);
            }

            let baseName = name;
            let counter = 1;
            while (usedNames.has(name.toLowerCase())) {
                counter++;
                name = `${baseName} ${counter}`;
            }
            usedNames.add(name.toLowerCase());
            return { ...btn, name };
        });
        importedButtons.value = uniqueButtons;
        selectedTemplateId.value = '';
    }
    showDbPicker.value = false;
};

const save = () => {
    if (!localDevice.value) return;

    if (isEditMode.value && localDevice.value.id) {
        const { name, icon, target_bridges, allowed_bridges } = localDevice.value;
        api(`devices/${localDevice.value.id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, icon, target_bridges: target_bridges || [], allowed_bridges: allowed_bridges || [] })
        }).then(() => {
            deviceStore.fetchDevices();
            closeModal();
        });
    } else {
        newDevice.value.name = localDevice.value.name;
        newDevice.value.icon = localDevice.value.icon || 'remote-tv';
        newDevice.value.target_bridges = localDevice.value.target_bridges || [];
        newDevice.value.allowed_bridges = localDevice.value.allowed_bridges || [];

        if (selectedTemplateId.value) {
            const template = deviceTemplates.find(t => t.id === selectedTemplateId.value);
            if (template) {
                newDevice.value.buttons = template.buttons.map(btn => ({
                    id: '',
                    name: btn.name,
                    icon: btn.icon,
                    code: null,
                    is_output: true,
                    is_input: false,
                    is_event: false,
                }));
            }
        } else if (importedButtons.value.length > 0) {
            newDevice.value.buttons = importedButtons.value;
        }

        deviceStore.addDevice().then(device => {
            if (device) {
                emit('device-created', device.id);
                closeModal();
            }
        });
    }
};

const liveErrors = computed(() => {
    const errs: Record<string, string> = {};
    if (!localDevice.value) return errs;

    if (!localDevice.value.name || !localDevice.value.name.trim()) {
        errs.name = t('errors.required', { field: t('devices.modal.deviceName') });
    } else {
        const name = localDevice.value.name.trim().toLowerCase();
        const duplicate = devices.value.some(d => d.name.toLowerCase() === name && d.id !== localDevice.value?.id);
        if (duplicate) {
            errs.name = t('errors.unique', { field: t('devices.modal.deviceName') });
        }
    }
    return errs;
});

const validationError = computed(() => {
    const keys = Object.keys(liveErrors.value);
    return keys.length > 0 ? liveErrors.value[keys[0]] : undefined;
});


const isValid = computed(() => !validationError.value);

</script>

<template>
  <div
    v-if="show"
    class="fixed inset-0 !m-0 bg-gray-900/60 flex items-center justify-center z-50 backdrop-blur-sm"
    @click.self="closeModal"
  >
    <div
      v-if="localDevice"
      class="bg-gray-900 border border-gray-700 rounded-lg max-w-lg w-full max-h-[90vh] flex flex-col shadow-2xl animate-in fade-in scale-95 duration-200"
      style="animation: slideInUp 0.3s ease-out;"
    >
      <div class="p-6 border-b border-gray-700 shrink-0">
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-semibold">
            {{ isEditMode ? t('devices.editDevice') : t('devices.addDevice') }}
          </h3>
          <button
            v-if="!isEditMode"
            class="text-gray-500 hover:text-gray-300 transition-colors"
            :title="t('app.startTourDefault')"
            @click="startDeviceModalTour"
          >
            <i class="mdi mdi-help-circle-outline text-xl" />
          </button>
        </div>
      </div>
      <div class="p-6 space-y-4 overflow-y-auto min-h-0">
        <div
          v-if="!isEditMode"
          data-tour-id="device-init-section"
        >
          <label class="block text-sm font-medium text-gray-300 mb-1">{{ t('devices.modal.initDevice') }}</label>
            
          <div class="flex gap-2 mb-2">
            <select
              v-model="selectedTemplateId"
              class="flex-grow rounded p-2 text-sm bg-gray-900 border-gray-600"
              :disabled="importedButtons.length > 0"
            >
              <option value="">
                {{ t('devices.modal.selectTemplate') }}
              </option>
              <option
                v-for="tmpl in deviceTemplates"
                :key="tmpl.id"
                :value="tmpl.id"
              >
                {{ tmpl.name }}
              </option>
            </select>
            <button
              class="btn btn-sm btn-secondary whitespace-nowrap"
              @click="showDbPicker = true"
            >
              <i class="mdi mdi-database-search" /> {{ t('devices.modal.browseDb') }}
            </button>
          </div>
            
          <div
            v-if="selectedTemplate"
            class="mt-3 p-3 bg-gray-900/50 rounded border border-gray-700"
          >
            <div class="text-xs font-bold text-gray-300 mb-2">
              {{ t('devices.modal.includedButtons', { count: selectedTemplate.buttons.length }) }}
            </div>
            <div class="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
              <div 
                v-for="btn in selectedTemplate.buttons" 
                :key="btn.name" 
                class="w-8 h-8 flex items-center justify-center bg-gray-800 rounded border border-gray-600 text-gray-300 hover:text-gray-200 hover:border-gray-400 transition-colors cursor-help"
                :title="btn.name"
              >
                <i
                  class="mdi text-lg"
                  :class="`mdi-${btn.icon}`"
                />
              </div>
            </div>
          </div>

          <div
            v-if="importedButtons.length > 0"
            class="mt-3 p-3 bg-blue-900/20 rounded border border-blue-500/50"
          >
            <div class="flex justify-between items-center mb-2">
              <div class="text-xs font-bold text-blue-400">
                {{ t('devices.modal.importedButtons', { count: importedButtons.length }) }}
              </div>
              <button
                class="text-xs text-gray-400 hover:text-gray-300"
                @click="importedButtons = []"
              >
                <i class="mdi mdi-close" /> {{ t('devices.modal.clear') }}
              </button>
            </div>
            <div class="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
              <div
                v-for="(btn, idx) in importedButtons"
                :key="idx"
                class="text-xs bg-gray-800 px-2 py-1 rounded border border-gray-600 text-gray-300 truncate max-w-[120px]"
                :title="btn.name"
              >
                <i
                  class="mdi"
                  :class="`mdi-${btn.icon || 'remote'}`"
                /> {{ btn.name }}
              </div>
            </div>
          </div>

          <p
            v-if="!selectedTemplate && importedButtons.length === 0"
            class="text-xs text-gray-400 pt-1"
          >
            {{ t('devices.modal.helpText') }}
          </p>
        </div>

        <div data-tour-id="device-name-input">
          <label class="block text-sm font-medium text-gray-300 mb-1">{{ t('devices.modal.deviceName') }}</label>
          <input
            v-model="localDevice.name"
            :placeholder="t('devices.modal.placeholder')"
            class="w-full rounded p-2"
            :class="{'border-red-500': liveErrors.name}"
            @keyup.enter="save"
          >
        </div>
        
        <IconPicker
          v-model="deviceIcon"
          :label="t('devices.modal.icon')"
          data-tour-id="device-icon-picker"
        />

        <BridgeSelector
          v-model="localDevice.target_bridges"
          :bridges="bridges"
          data-tour-id="device-target-bridges"
        />
        <BridgeSelector
          v-model="localDevice.allowed_bridges"
          :bridges="bridges"
          type="source"
          data-tour-id="device-allowed-bridges"
        />
      </div>
      <div class="p-6 border-t border-gray-700 flex gap-2 justify-end items-center shrink-0">
        <span
          v-if="validationError"
          class="text-red-400 text-sm mr-auto font-medium"
        >{{ validationError }}</span>
        <button
          class="btn btn-secondary"
          data-tour-id="device-modal-cancel"
          @click="closeModal"
        >
          {{ t('confirm.cancel') }}
        </button>
        <button
          class="btn btn-primary"
          :disabled="!isValid"
          :class="{'opacity-50 cursor-not-allowed': !isValid}"
          data-tour-id="device-save-button"
          @click="save"
        >
          <i
            v-if="!isEditMode"
            class="mdi mdi-plus"
          />
          {{ isEditMode ? t('devices.editDeviceBtn') : t('devices.addDeviceBtn') }}
        </button>
      </div>
    </div>
    <IrDbPicker
      :show="showDbPicker"
      selection-mode="multi"
      @close="showDbPicker = false"
      @select="onDbButtonsSelected"
    />
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