<script setup lang="ts">
import { ref, watch, computed, nextTick } from 'vue';
import { storeToRefs } from 'pinia';
import Switch from './Switch.vue';
import IconPicker from './IconPicker.vue';
import IrDbPicker from './IrDbPicker.vue';
import { useDeviceStore, Button } from '../stores/devices';
import { useSettingsStore } from '../stores/settings';
import { useLearnStore } from '../stores/learn';
import { api } from '../services/api';
import { sanitizeNameForImport } from '../utils';
import { startButtonModalTour } from '../tour';
import { useI18n } from '../i18n';
import type { IRCode } from '../types';

const props = defineProps({
  show: Boolean,
  button: {
    type: Object as () => Partial<Button> | null,
    default: null,
  },
  protocols: {
    type: Array as () => string[],
    default: () => [],
  },
});

const emit = defineEmits(['close']);

const deviceStore = useDeviceStore();
const settingsStore = useSettingsStore();
const learnStore = useLearnStore();

const { devices } = storeToRefs(deviceStore);
const { appMode, topicStyle } = storeToRefs(settingsStore);

const localButton = ref<Partial<Button> | null>(null);
const showDbPicker = ref(false);
const isInternalUpdate = ref(false);

const { t } = useI18n();

const closeModal = () => {
  emit('close');
};

const onEscape = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    closeModal();
  }
};
const isEditing = computed(() => !!localButton.value?.id);

const isEvent = computed({
    get: () => localButton.value?.is_event ?? false,
    set: (v) => { if (localButton.value) localButton.value.is_event = v; }
});
const isOutput = computed({
    get: () => localButton.value?.is_output ?? false,
    set: (v) => { if (localButton.value) localButton.value.is_output = v; }
});
const isInput = computed({
    get: () => localButton.value?.is_input ?? false,
    set: (v) => { if (localButton.value) localButton.value.is_input = v; }
});

watch(() => props.show, (newVal) => {
  if (newVal) {
    const defaults = {
        code: { protocol: '', payload: {}, raw_tolerance: 20 },
        is_output: true,
        is_input: false,
        is_event: true,
        input_mode: 'momentary',
        input_off_delay_s: 1,
    };
    const btnToEdit = { ...defaults, ...props.button };
    const existingCode = (btnToEdit.code ?? {}) as Partial<IRCode>;
    btnToEdit.code = {
        protocol: existingCode.protocol ?? '',
        payload: existingCode.payload ?? {},
        raw_tolerance: existingCode.raw_tolerance ?? 20,
    };

    isInternalUpdate.value = true;
    localButton.value = JSON.parse(JSON.stringify(btnToEdit));
    document.addEventListener('keydown', onEscape);
    nextTick(() => { isInternalUpdate.value = false; });
  } else {
    document.removeEventListener('keydown', onEscape);
  }
}, { immediate: true });

watch(() => localButton.value?.code?.protocol, (newProto, oldProto) => {
    if (isInternalUpdate.value || oldProto === undefined || newProto === oldProto || !localButton.value?.code) {
        return;
    }
    
    const proto = localButton.value.code.protocol;
    localButton.value.code = { protocol: proto, payload: {}, raw_tolerance: 20 };
});

const editableButtonIcon = computed({
    get: () => localButton.value?.icon || '',
    set: (val) => {
        if (localButton.value) {
            localButton.value.icon = val;
        }
    }
});

// Protocol groups by form type
const addrCmdProtos    = ['nec', 'samsung36', 'panasonic', 'rc5', 'rc6', 'dish',
                          'byronsx', 'drayton', 'dyson', 'abbwelcome',
                          'sharp', 'sanyo', 'rca']; // legacy
const dataBitsProtos   = ['samsung', 'sony', 'lg', 'symphony', 'toshiba', 'whynter']; // legacy toshiba/whynter
const dataHexProtos    = ['jvc', 'gobox'];
const arrayDataProtos  = ['midea', 'haier', 'mirage'];
const aehaProtos       = ['aeha'];
const rcCodesProtos    = ['pioneer', 'toshiba_ac'];
const coolixProtos     = ['coolix'];
const rawProtos        = ['raw'];
const prontoProtos     = ['pronto'];
const beo4Protos       = ['beo4'];
const canalsatProtos   = ['canalsat', 'canalsat_ld'];
const dooyaProtos      = ['dooya'];
const keeloqProtos     = ['keeloq'];
const magiquestProtos  = ['magiquest'];
const nexaProtos       = ['nexa'];
const rcswitchProtos   = ['rc_switch'];
const cmdOnlyProtos    = ['roomba', 'toto'];

const isHex = (val: string | number[] | null | undefined): boolean => {
    if (Array.isArray(val)) {
        return false; // Or handle array conversion to string if needed for hex check
    }
    return !!val && /^0x[0-9A-Fa-f]+$/.test(val);
};

const getValidationErrors = (btn: Partial<Button> | null) => {
    const errs: Record<string, string> = {};
    if (!btn) return errs;

    if (!btn.name?.trim()) {
        errs.name = t('errors.required', { field: t('devices.button.name') });
    }

    const dev = devices.value.find(d => d.id === btn.deviceId);
    if (dev) {
        const name = (btn.name || '').trim().toLowerCase();
        const duplicate = dev.buttons.some(b => b.name.toLowerCase() === name && b.id !== btn.id);
        if (duplicate) {
            errs.name = t('errors.unique', { field: t('devices.button.name') });
        }
    }

    if (btn.is_input && btn.input_mode === 'timed') {
        if (typeof btn.input_off_delay_s !== 'number' || btn.input_off_delay_s < 0) {
            errs.off_delay = t('errors.required', { field: t('devices.button.offDelay') });
        }
    }

    const code = btn.code;
    if (code && code.protocol) {
        const p = code.payload ?? {};
        const reqHex = (key: string, label: string) => {
            if (!p[key]) errs[`code_${key}`] = t('errors.required', { field: label });
            else if (!isHex(p[key] as string)) errs[`code_${key}`] = `${label}: ${t('errors.invalidHex')}`;
        };

        if (addrCmdProtos.includes(code.protocol)) {
            reqHex('address', 'Address'); reqHex('command', 'Command');
        } else if (dataBitsProtos.includes(code.protocol)) {
            reqHex('data', 'Data');
            if (!p.nbits) errs.code_nbits = t('errors.required', { field: 'Bits' });
        } else if (dataHexProtos.includes(code.protocol)) {
            reqHex('data', 'Data');
        } else if (arrayDataProtos.includes(code.protocol)) {
            if (!p.data) errs.code_data = t('errors.required', { field: 'Data' });
        } else if (aehaProtos.includes(code.protocol)) {
            reqHex('address', 'Address');
            if (!p.data) errs.code_data = t('errors.required', { field: 'Data' });
        } else if (rcCodesProtos.includes(code.protocol)) {
            reqHex('rc_code_1', 'RC Code 1'); reqHex('rc_code_2', 'RC Code 2');
        } else if (coolixProtos.includes(code.protocol)) {
            reqHex('first', 'First');
        } else if (rawProtos.includes(code.protocol)) {
            if (!p.timings && !p.data) errs.code_timings = t('errors.required', { field: 'Timings' });
        } else if (prontoProtos.includes(code.protocol)) {
            if (!p.data) errs.code_data = t('errors.required', { field: 'Pronto Data' });
        } else if (beo4Protos.includes(code.protocol)) {
            reqHex('command', 'Command');
        } else if (canalsatProtos.includes(code.protocol)) {
            reqHex('device', 'Device'); reqHex('command', 'Command');
        } else if (dooyaProtos.includes(code.protocol)) {
            reqHex('address', 'Address'); reqHex('command', 'Command');
        } else if (keeloqProtos.includes(code.protocol)) {
            reqHex('encrypted', 'Encrypted'); reqHex('serial', 'Serial');
        } else if (magiquestProtos.includes(code.protocol)) {
            reqHex('id', 'Wand ID'); reqHex('magnitude', 'Magnitude');
        } else if (nexaProtos.includes(code.protocol)) {
            reqHex('device', 'Device'); reqHex('group', 'Group');
            reqHex('state', 'State'); reqHex('channel', 'Channel'); reqHex('level', 'Level');
        } else if (rcswitchProtos.includes(code.protocol)) {
            reqHex('code', 'Code');
        } else if (cmdOnlyProtos.includes(code.protocol)) {
            reqHex('command', 'Command');
        }
    }
    return errs;
};

const saveButton = () => {
    if (!localButton.value) return;

    if (validationError.value) return;
    
    const url = isEditing.value
        ? `devices/${localButton.value.deviceId}/buttons/${localButton.value.id}`
        : `devices/${localButton.value.deviceId}/buttons`;
    const method = isEditing.value ? 'PUT' : 'POST';

    const btnData: Partial<Button> = { ...localButton.value };

    if (btnData.code) {
        if (!btnData.code.protocol) {
            btnData.code = undefined;
        } else {
            const cleanedPayload: IRCode['payload'] = {};
            for (const [k, v] of Object.entries(btnData.code.payload ?? {})) {
                if (v !== '' && v !== null && v !== undefined) {
                    cleanedPayload[k] = v;
                }
            }
            const cleanedCode: IRCode = { protocol: btnData.code.protocol, payload: cleanedPayload };
            if (['raw', 'pronto'].includes(btnData.code.protocol)) {
                cleanedCode.raw_tolerance = btnData.code.raw_tolerance ?? 20;
            }
            btnData.code = cleanedCode;
        }
    }

    api(url, {
        method: method, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(btnData)
    }).then(() => { 
        deviceStore.fetchDevices();
        if (!isEditing.value && btnData.code) {
            learnStore.consumeLearnedCode(btnData.code);
        }
        closeModal();
    });
};

const onDbButtonSelected = (dbBtn: Partial<Button>) => {
    if (!localButton.value) return;
    
    let newName = dbBtn.name?.trim() || '';

    if (appMode.value === 'standalone' && topicStyle.value === 'name') {
        newName = sanitizeNameForImport(newName);
    }

    const dev = devices.value.find(d => d.id === localButton.value?.deviceId);
    if (dev) {
        let baseName = newName;
        let counter = 1;
        while (dev.buttons.some(b => b.name.toLowerCase() === newName.toLowerCase() && b.id !== localButton.value?.id)) {
            counter++;
            newName = `${baseName} ${counter}`;
        }
    }

    localButton.value.name = newName;
    localButton.value.icon = dbBtn.icon;
    
    isInternalUpdate.value = true;
    const currentCode = localButton.value.code || { protocol: '', payload: {} };
    const newCode = (dbBtn.code || {}) as Partial<IRCode>;
    localButton.value.code = {
        protocol: newCode.protocol || currentCode.protocol || '',
        payload: { ...(currentCode.payload ?? {}), ...(newCode.payload ?? {}) },
        raw_tolerance: newCode.raw_tolerance ?? currentCode.raw_tolerance ?? 20,
    };
    
    nextTick(() => { isInternalUpdate.value = false; });
};

// Timings textarea for raw protocol
const rawTimings = computed({
    get: () => {
        const t = localButton.value?.code?.payload?.timings;
        if (Array.isArray(t)) return (t as number[]).join(', ');
        return typeof t === 'string' ? t : '';
    },
    set: (v: string) => {
        if (localButton.value?.code) {
            const nums = v.split(/[\s,]+/).map(s => parseInt(s.trim())).filter(n => !isNaN(n));
            localButton.value.code.payload.timings = nums.length > 0 ? nums : (v as unknown as number[]);
        }
    },
});

// Byte-array textarea for midea/haier/mirage/aeha
const arrayInputData = computed({
    get: () => {
        const d = localButton.value?.code?.payload?.data;
        if (Array.isArray(d)) return (d as number[]).map(b => '0x' + b.toString(16).toUpperCase()).join(', ');
        return typeof d === 'string' ? d : '';
    },
    set: (v: string) => {
        if (localButton.value?.code) {
            localButton.value.code.payload.data = v; // backend parses hex/int array
        }
    },
});

const liveErrors = computed(() => getValidationErrors(localButton.value));
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
      v-if="localButton"
      class="bg-gray-900 border border-gray-700 rounded-lg max-w-lg w-full max-h-[90vh] flex flex-col shadow-2xl animate-in fade-in scale-95 duration-200"
      style="animation: slideInUp 0.3s ease-out;"
    >
      <div class="p-6 border-b border-gray-700 shrink-0">
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-semibold">
            {{ isEditing ? t('devices.button.edit') : t('devices.button.add') }}
          </h3>
          <button
            v-if="!isEditing"
            class="text-gray-500 hover:text-gray-300 transition-colors"
            :title="t('app.startTourDefault')"
            @click="startButtonModalTour"
          >
            <i class="mdi mdi-help-circle-outline text-xl" />
          </button>
        </div>
      </div>
      <div class="p-6 space-y-4 overflow-y-auto min-h-0">
        <button
          class="w-full btn btn-sm btn-secondary"
          data-tour-id="button-browse-db"
          @click="showDbPicker = true"
        >
          <i class="mdi mdi-database-search" /> {{ t('devices.button.browseDb') }}
        </button>

        <div
          class="space-y-1"
          data-tour-id="button-name-input"
        >
          <label class="block text-sm font-medium text-gray-300">{{ t('devices.button.name') }}</label>
          <input
            v-model="localButton.name"
            :placeholder="t('devices.button.placeholder')"
            class="w-full rounded p-2 text-sm"
            :class="{'border-red-500': liveErrors.name}"
          >
        </div>
        
        <IconPicker
          v-model="editableButtonIcon"
          :label="t('devices.button.icon')"
          data-tour-id="button-icon-picker"
        />

        <div
          v-if="appMode === 'home_assistant'"
          class="bg-gray-800/50 p-4 rounded-lg border border-gray-700"
          data-tour-id="button-ha-section"
        >
          <h4 class="text-sm font-bold text-indigo-400 mb-3 flex items-center gap-2">
            <i class="mdi mdi-home-assistant" /> {{ t('automations.modal.haIntegration') }}
          </h4>
          <div class="space-y-3">
            <label class="flex items-center justify-between bg-gray-900 p-3 rounded border border-gray-700 cursor-pointer">
              <div>
                <span class="font-medium text-sm block text-gray-200">{{ t('devices.button.event') }}</span>
                <span class="text-xs text-gray-400">{{ t('devices.button.eventDesc') }}</span>
              </div>
              <Switch v-model="isEvent" />
            </label>

            <label class="flex items-center justify-between bg-gray-900 p-3 rounded border border-gray-700 cursor-pointer">
              <div>
                <span class="font-medium text-sm block text-gray-200">{{ t('devices.button.output') }}</span>
                <span class="text-xs text-gray-400">{{ t('devices.button.outputDesc') }}</span>
              </div>
              <Switch v-model="isOutput" />
            </label>

            <label class="flex items-center justify-between bg-gray-900 p-3 rounded border border-gray-700 cursor-pointer">
              <div>
                <span class="font-medium text-sm block text-gray-200">{{ t('devices.button.input') }}</span>
                <span class="text-xs text-gray-400">{{ t('devices.button.inputDesc') }}</span>
              </div>
              <Switch v-model="isInput" />
            </label>
          </div>

          


          <div
            v-if="localButton.is_input"
            class="p-3 bg-gray-800/50 rounded-lg space-y-2 mt-2 border border-gray-700"
          >
            <h4 class="text-sm font-semibold text-gray-300">
              {{ t('devices.button.inputSettings') }}
            </h4>
            <div>
              <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('devices.button.mode') }}</label>
              <select
                v-model="localButton.input_mode"
                class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
              >
                <option value="momentary">
                  {{ t('devices.button.modeMomentary') }}
                </option>
                <option value="toggle">
                  {{ t('devices.button.modeToggle') }}
                </option>
                <option value="timed">
                  {{ t('devices.button.modeTimed') }}
                </option>
              </select>
            </div>
            <div v-if="localButton.input_mode === 'timed'">
              <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('devices.button.offDelay') }}</label>
              <input
                v-model.number="localButton.input_off_delay_s"
                type="number"
                class="w-full rounded p-2 text-sm bg-gray-900"
                :class="liveErrors.off_delay ? 'border-red-500' : 'border-gray-600'"
              >
            </div>
          </div>
        </div>
        
        <div
          v-if="appMode !== 'home_assistant'"
          class="bg-gray-800/50 p-4 rounded-lg border border-gray-700"
          data-tour-id="button-standalone-section"
        >
          <h4 class="text-sm font-bold text-indigo-400 mb-3 flex items-center gap-2">
            <i class="mdi mdi-axis-arrow" /> {{ t('devices.button.capabilities') }}
          </h4>
          <div class="space-y-3">
            <label class="flex items-center justify-between bg-gray-900 p-3 rounded border border-gray-700 cursor-pointer">
              <div>
                <span class="font-medium text-sm block text-gray-200">{{ t('devices.button.event') }}</span>
                <span class="text-xs text-gray-400">{{ t('devices.button.eventDescStandalone') }}</span>
              </div>
              <Switch v-model="isEvent" />
            </label>
              
            <label class="flex items-center justify-between bg-gray-900 p-3 rounded border border-gray-700 cursor-pointer">
              <div>
                <span class="font-medium text-sm block text-gray-200">{{ t('devices.button.output') }}</span>
                <span class="text-xs text-gray-400">{{ t('devices.button.outputDescStandalone') }}</span>
              </div>
              <Switch v-model="isOutput" />
            </label>

            <label class="flex items-center justify-between bg-gray-900 p-3 rounded border border-gray-700 cursor-pointer">
              <div>
                <span class="font-medium text-sm block text-gray-200">{{ t('devices.button.input') }}</span>
                <span class="text-xs text-gray-400">{{ t('devices.button.inputDescStandalone') }}</span>
              </div>
              <Switch v-model="isInput" />
            </label>
          </div>

          


          <div
            v-if="localButton.is_input"
            class="p-3 bg-gray-800/50 rounded-lg space-y-2 mt-2 border border-gray-700"
          >
            <h4 class="text-sm font-semibold text-gray-300">
              {{ t('devices.button.inputSettings') }}
            </h4>
            <div>
              <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('devices.button.mode') }}</label>
              <select
                v-model="localButton.input_mode"
                class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
              >
                <option value="momentary">
                  {{ t('devices.button.modeMomentary') }}
                </option>
                <option value="toggle">
                  {{ t('devices.button.modeToggle') }}
                </option>
                <option value="timed">
                  {{ t('devices.button.modeTimed') }}
                </option>
              </select>
            </div>
            <div v-if="localButton.input_mode === 'timed'">
              <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('devices.button.offDelay') }}</label>
              <input
                v-model.number="localButton.input_off_delay_s"
                type="number"
                class="w-full rounded p-2 text-sm bg-gray-900"
                :class="liveErrors.off_delay ? 'border-red-500' : 'border-gray-600'"
              >
            </div>
          </div>
        </div>

        <div
          class="border-t border-gray-700 pt-4 space-y-2"
          data-tour-id="button-ir-code-section"
        >
          <h4 class="text-lg font-semibold text-gray-300">
            {{ t('devices.button.irCode') }}
          </h4>
          <p class="text-xs text-gray-400 pb-2">
            {{ t('devices.button.irCodeDesc') }}
          </p>
          
          <div
            v-if="localButton.code"
            class="space-y-2"
          >
            <select
              v-model="localButton.code.protocol"
              class="w-full rounded p-2 text-sm"
              data-tour-id="button-protocol-select"
            >
              <option value="">
                {{ t('devices.button.selectProtocol') }}
              </option>
              <option
                v-for="p in protocols"
                :key="p"
                :value="p"
              >
                {{ p.toUpperCase() }}
              </option>
            </select>
            
            <!-- address + command -->
            <template v-if="addrCmdProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.address"
                :placeholder="t('devices.button.placeholders.address')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_address}"
                data-tour-id="button-address-input"
              >
              <input
                v-model="localButton.code.payload.command"
                :placeholder="t('devices.button.placeholders.command')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_command}"
                data-tour-id="button-command-input"
              >
            </template>

            <!-- data + nbits -->
            <template v-if="dataBitsProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.data"
                :placeholder="t('devices.button.placeholders.data')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_data}"
              >
              <input
                v-model="localButton.code.payload.nbits"
                :placeholder="t('devices.button.placeholders.bits')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_nbits}"
              >
            </template>

            <!-- data hex only (jvc, gobox) -->
            <template v-if="dataHexProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.data"
                :placeholder="t('devices.button.placeholders.dataHex')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_data}"
              >
            </template>

            <!-- byte array (midea, haier, mirage) -->
            <template v-if="arrayDataProtos.includes(localButton.code.protocol)">
              <textarea
                v-model="arrayInputData"
                :placeholder="t('devices.button.placeholders.bytesArray')"
                class="w-full rounded p-2 text-sm h-16"
                :class="{'border-red-500': liveErrors.code_data}"
              />
            </template>

            <!-- aeha: address + byte array -->
            <template v-if="aehaProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.address"
                :placeholder="t('devices.button.placeholders.addressAeha')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_address}"
              >
              <textarea
                v-model="arrayInputData"
                :placeholder="t('devices.button.placeholders.dataBytes')"
                class="w-full rounded p-2 text-sm h-16"
                :class="{'border-red-500': liveErrors.code_data}"
              />
            </template>

            <!-- rc_code_1 + rc_code_2 (pioneer, toshiba_ac) -->
            <template v-if="rcCodesProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.rc_code_1"
                :placeholder="t('devices.button.placeholders.rcCode1')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_rc_code_1}"
              >
              <input
                v-model="localButton.code.payload.rc_code_2"
                :placeholder="t('devices.button.placeholders.rcCode2')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_rc_code_2}"
              >
            </template>

            <!-- coolix -->
            <template v-if="coolixProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.first"
                :placeholder="t('devices.button.placeholders.first')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_first}"
              >
              <input
                v-model="localButton.code.payload.second"
                :placeholder="t('devices.button.placeholders.second')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_second}"
              >
            </template>

            <!-- raw -->
            <template v-if="rawProtos.includes(localButton.code.protocol)">
              <textarea
                v-model="rawTimings"
                :placeholder="t('devices.button.placeholders.timings')"
                class="w-full rounded p-2 text-sm h-24"
                :class="{'border-red-500': liveErrors.code_timings}"
              />
              <input
                v-model.number="localButton.code.payload.frequency"
                type="number"
                :placeholder="t('devices.button.placeholders.frequency')"
                class="w-full rounded p-2 text-sm"
              >
              <div class="flex items-center gap-2">
                <label class="text-xs font-medium text-gray-300 whitespace-nowrap">{{ t('devices.button.tolerance') }}</label>
                <input
                  v-model.number="localButton.code.raw_tolerance"
                  type="number"
                  class="w-20 rounded p-2 text-sm bg-gray-900 border-gray-600"
                  min="1"
                  max="100"
                >
              </div>
            </template>

            <!-- pronto -->
            <template v-if="prontoProtos.includes(localButton.code.protocol)">
              <textarea
                v-model="(localButton.code.payload.data as string)"
                :placeholder="t('devices.button.placeholders.pronto')"
                class="w-full rounded p-2 text-sm h-24"
                :class="{'border-red-500': liveErrors.code_data}"
              />
              <input
                v-model.number="localButton.code.payload.delta"
                type="number"
                :placeholder="t('devices.button.placeholders.delta')"
                class="w-full rounded p-2 text-sm"
              >
              <div class="flex items-center gap-2">
                <label class="text-xs font-medium text-gray-300 whitespace-nowrap">{{ t('devices.button.tolerance') }}</label>
                <input
                  v-model.number="localButton.code.raw_tolerance"
                  type="number"
                  class="w-20 rounded p-2 text-sm bg-gray-900 border-gray-600"
                  min="1"
                  max="100"
                >
              </div>
            </template>

            <!-- beo4 -->
            <template v-if="beo4Protos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.command"
                :placeholder="t('devices.button.placeholders.beo4Command')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_command}"
              >
              <input
                v-model="localButton.code.payload.source"
                :placeholder="t('devices.button.placeholders.beo4Source')"
                class="w-full rounded p-2 text-sm"
              >
            </template>

            <!-- canalsat / canalsat_ld -->
            <template v-if="canalsatProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.device"
                :placeholder="t('devices.button.placeholders.deviceCanalsat')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_device}"
              >
              <input
                v-model="localButton.code.payload.command"
                :placeholder="t('devices.button.placeholders.commandCanalsat')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_command}"
              >
              <input
                v-model="localButton.code.payload.address"
                :placeholder="t('devices.button.placeholders.addressOpt')"
                class="w-full rounded p-2 text-sm"
              >
            </template>

            <!-- dooya -->
            <template v-if="dooyaProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.address"
                :placeholder="t('devices.button.placeholders.motorId')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_address}"
              >
              <input
                v-model="localButton.code.payload.command"
                :placeholder="t('devices.button.placeholders.buttonDooya')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_command}"
              >
              <input
                v-model="localButton.code.payload.channel"
                :placeholder="t('devices.button.placeholders.channelOpt')"
                class="w-full rounded p-2 text-sm"
              >
            </template>

            <!-- keeloq -->
            <template v-if="keeloqProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.encrypted"
                :placeholder="t('devices.button.placeholders.encrypted')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_encrypted}"
              >
              <input
                v-model="localButton.code.payload.serial"
                :placeholder="t('devices.button.placeholders.serial')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_serial}"
              >
            </template>

            <!-- magiquest -->
            <template v-if="magiquestProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.id"
                :placeholder="t('devices.button.placeholders.wandId')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_id}"
              >
              <input
                v-model="localButton.code.payload.magnitude"
                :placeholder="t('devices.button.placeholders.magnitude')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_magnitude}"
              >
            </template>

            <!-- nexa -->
            <template v-if="nexaProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.device"
                :placeholder="t('devices.button.placeholders.deviceId')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_device}"
              >
              <input
                v-model="localButton.code.payload.group"
                :placeholder="t('devices.button.placeholders.group')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_group}"
              >
              <input
                v-model="localButton.code.payload.state"
                :placeholder="t('devices.button.placeholders.stateNexa')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_state}"
              >
              <input
                v-model="localButton.code.payload.channel"
                :placeholder="t('devices.button.placeholders.channelNexa')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_channel}"
              >
              <input
                v-model="localButton.code.payload.level"
                :placeholder="t('devices.button.placeholders.level')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_level}"
              >
            </template>

            <!-- rc_switch -->
            <template v-if="rcswitchProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.code"
                :placeholder="t('devices.button.placeholders.codeRc')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_code}"
              >
              <input
                v-model.number="localButton.code.payload.protocol"
                type="number"
                :placeholder="t('devices.button.placeholders.protocolRc')"
                class="w-full rounded p-2 text-sm"
                min="1"
                max="12"
              >
            </template>

            <!-- roomba / toto: command only -->
            <template v-if="cmdOnlyProtos.includes(localButton.code.protocol)">
              <input
                v-model="localButton.code.payload.command"
                :placeholder="t('devices.button.placeholders.commandRoomba')"
                class="w-full rounded p-2 text-sm"
                :class="{'border-red-500': liveErrors.code_command}"
              >
            </template>
          </div>
        </div>
      </div>
      <div class="p-6 border-t border-gray-700 flex gap-2 justify-end items-center shrink-0">
        <span
          v-if="validationError"
          class="text-red-400 text-sm mr-auto font-medium"
        >{{ validationError }}</span>
        <button
          class="btn btn-secondary"
          @click="closeModal"
        >
          {{ t('confirm.cancel') }}
        </button>
        <button
          class="btn btn-primary"
          :disabled="!isValid"
          :class="{'opacity-50 cursor-not-allowed': !isValid}"
          data-tour-id="button-save-button"
          @click="saveButton"
        >
          {{ t('devices.button.save') }}
        </button>
      </div>
    </div>
    <IrDbPicker
      :show="showDbPicker"
      @close="showDbPicker = false"
      @select="onDbButtonSelected"
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
