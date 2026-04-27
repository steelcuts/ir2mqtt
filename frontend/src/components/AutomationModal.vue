<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useDeviceStore } from '../stores/devices';
import { useAutomationsStore, Automation, AutomationTrigger, AutomationAction } from '../stores/automations';
import { useSettingsStore } from '../stores/settings';
import { api } from '../services/api';
import Switch from './Switch.vue';
import ActionList from './ActionList.vue';
import { startAutomationModalTour } from '../tour';
import { useI18n } from '../i18n';

const props = defineProps({
  show: Boolean,
  automation: {
    type: Object as () => Automation | null,
    default: null,
  },
});

const emit = defineEmits(['close']);

const deviceStore = useDeviceStore();
const automationsStore = useAutomationsStore();
const settingsStore = useSettingsStore();

const { devices } = storeToRefs(deviceStore);
const { automations } = storeToRefs(automationsStore);
const { appMode } = storeToRefs(settingsStore);

const localAuto = ref<Automation | null>(null);
const isEditing = computed(() => !!localAuto.value?.id);

const { t } = useI18n();


watch(() => props.show, (newVal) => {
  if (newVal && props.automation) {
    const data = JSON.parse(JSON.stringify(props.automation));
    if (data.enabled === undefined) data.enabled = true;
    if (!data.triggers) data.triggers = [];
    data.ha_expose_button = !!(data.ha_expose_button ?? false);
    data.allow_parallel = !!(data.allow_parallel ?? false);
    
    localAuto.value = data;
  }
}, { immediate: true });

watch(() => props.automation, (newVal) => {
  if (props.show && newVal) {
    const data = JSON.parse(JSON.stringify(newVal));
    if (data.enabled === undefined) data.enabled = true;
    if (!data.triggers) data.triggers = [];
    data.ha_expose_button = !!(data.ha_expose_button ?? false);
    data.allow_parallel = !!(data.allow_parallel ?? false);
    localAuto.value = data;
  }
}, { deep: true });

const addAction = (type: string) => {
    if (!localAuto.value) return;
    if (!localAuto.value.actions) localAuto.value.actions = [];
    if (type === 'delay') {
        localAuto.value.actions.push({ type: 'delay', delay_ms: 1000 });
    } else if (type === 'event') {
        localAuto.value.actions.push({ type: 'event', event_name: 'my_event' });
    }
    else {
        const firstDev = devices.value[0];
        const firstBtn = firstDev?.buttons[0];
        localAuto.value.actions.push({ 
            type: 'ir_send', 
            device_id: firstDev?.id || '', 
            button_id: firstBtn?.id || ''
        });
    }
};

const removeAction = (idx: number) => {
    localAuto.value?.actions.splice(idx, 1);
};

const addTrigger = () => {
    if (!localAuto.value) return;
    if (!localAuto.value.triggers) localAuto.value.triggers = [];
    localAuto.value.triggers.push({
        type: 'single',
        device_id: '',
        button_id: '',
        count: 1,
        window_ms: 2000,
        sequence: [],
        reset_on_other_input: true,
        // device_inactivity defaults
        timeout_s: 30,
        watch_mode: 'received',
        button_filter: null,
        button_exclude: null,
        rearm_mode: 'always',
        cooldown_s: 0,
        require_initial_activity: true,
        ignore_own_actions: true,
    });
};

/**
 * Ensures all device_inactivity fields have sensible defaults when the user
 * switches a trigger's type to "device_inactivity". Without this, optional
 * fields are undefined and the <select> elements appear blank.
 */
const onTriggerTypeChange = (trigger: AutomationTrigger) => {
    if (trigger.type === 'device_inactivity') {
        if (trigger.timeout_s === undefined || trigger.timeout_s === null) trigger.timeout_s = 30;
        if (!trigger.watch_mode) trigger.watch_mode = 'received';
        if (!trigger.rearm_mode) trigger.rearm_mode = 'always';
        if (trigger.cooldown_s === undefined || trigger.cooldown_s === null) trigger.cooldown_s = 0;
        if (trigger.require_initial_activity === undefined) trigger.require_initial_activity = true;
        if (trigger.ignore_own_actions === undefined) trigger.ignore_own_actions = true;
        if (trigger.button_filter === undefined) trigger.button_filter = null;
        if (trigger.button_exclude === undefined) trigger.button_exclude = null;
    }
};

// Toggle a button in a trigger's filter or exclude list
const toggleButtonInList = (
    trigger: AutomationTrigger,
    field: 'button_filter' | 'button_exclude',
    btnId: string,
) => {
    if (trigger[field] === null || trigger[field] === undefined) {
        trigger[field] = [btnId];
        return;
    }
    const list = trigger[field] as string[];
    const idx = list.indexOf(btnId);
    if (idx === -1) list.push(btnId);
    else list.splice(idx, 1);
    // Null means "all buttons" — remove the list when it becomes empty
    if (list.length === 0) trigger[field] = null;
};

const removeTrigger = (idx: number) => {
    localAuto.value?.triggers.splice(idx, 1);
};

const save = () => {
    if (!localAuto.value) return;
    if (validationError.value) return;
    
    const method = localAuto.value.id ? 'PUT' : 'POST';
    const url = localAuto.value.id ? `automations/${localAuto.value.id}` : 'automations';
    
    api(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(localAuto.value)
    }).then(() => {
        automationsStore.fetchAutomations();
        emit('close');
    });
};

const onTriggerDeviceChange = (trigger: AutomationTrigger) => {
    const buttons = deviceStore.getButtonsForDevice(trigger.device_id);
    trigger.button_id = buttons.length > 0 ? buttons[0].id : '';
};

const onActionDeviceChange = (action: AutomationAction) => {
    const buttons = deviceStore.getButtonsForDevice(action.device_id || '');
    action.button_id = buttons.length > 0 ? buttons[0].id : '';
};

const addSequenceStep = (trigger: AutomationTrigger) => {
    const firstDev = devices.value[0];
    const firstBtn = firstDev?.buttons[0];
    if (!trigger.sequence) trigger.sequence = [];
    trigger.sequence.push({
        device_id: firstDev?.id || '',
        button_id: firstBtn?.id || ''
    });
};

const removeSequenceStep = (trigger: AutomationTrigger, idx: number) => {
    trigger.sequence?.splice(idx, 1);
};

const draggingItem = ref<{ index: number; type: string } | undefined>(undefined);
const dragOverItem = ref<{ index: number; type: string } | undefined>(undefined);

const onDragStart = (event: DragEvent, index: number, type: string, triggerIndex: number | null = null) => {
    const typeKey = triggerIndex !== null ? `${type}-${triggerIndex}` : type;
    draggingItem.value = { index, type: typeKey };
    if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.dropEffect = 'move';
        event.dataTransfer.setData('application/json', JSON.stringify({ index, type: typeKey }));
    }
};

const onDrop = (event: DragEvent, toIndex: number, type: string) => {
    draggingItem.value = undefined;
    dragOverItem.value = undefined;

    if (!event.dataTransfer) return;
    const dataStr = event.dataTransfer.getData('application/json');
    if (!dataStr) return;
    const data = JSON.parse(dataStr);
    
    // Check if dropping in the same list
    if (data.type !== type || data.index === toIndex) return;
    
    if (!localAuto.value) return;

    if (type.startsWith('sequence-')) {
        const triggerIdx = parseInt(type.split('-')[1]);
        if (localAuto.value.triggers && localAuto.value.triggers[triggerIdx] && localAuto.value.triggers[triggerIdx].sequence) {
            const list = localAuto.value.triggers[triggerIdx].sequence!;
            const [moved] = list.splice(data.index, 1);
            list.splice(toIndex, 0, moved);
        }
    } else {
        if (localAuto.value.actions) {
            const list = localAuto.value.actions;
            const [moved] = list.splice(data.index, 1);
            list.splice(toIndex, 0, moved);
        }
    }
};

const onDragEnd = () => {
    draggingItem.value = undefined;
    dragOverItem.value = undefined;
};

const onDragOver = (index: number, type: string) => {
    if (draggingItem.value?.type === type) {
        dragOverItem.value = { index, type };
    }
};

const getSequenceStepClass = (tIdx: number, idx: number) => {
    const dragType = `sequence-${tIdx}`;
    const isDragging = draggingItem.value?.type === dragType && draggingItem.value?.index === idx;
    const isDragOver = dragOverItem.value?.type === dragType && dragOverItem.value?.index === idx;
    const draggingIdx = draggingItem.value?.index ?? -1;

    return {
        'opacity-40': isDragging,
        'border-blue-500': isDragOver && draggingIdx !== idx,
        'border-t-4 border-t-blue-500': isDragOver && draggingIdx > idx,
        'border-b-4 border-b-blue-500': isDragOver && draggingIdx < idx
    };
};

const liveErrors = computed(() => {
    const errs: Record<string, string> = {};
    const auto = localAuto.value;
    if (!auto) return errs;

    if (!auto.name) errs.name = t('errors.required', { field: t('automations.modal.name') });
    else {
        const name = auto.name.trim().toLowerCase();
        const duplicate = automations.value.some(a => a.name.toLowerCase() === name && a.id !== auto.id);
        if (duplicate) errs.name = t('errors.unique', { field: t('automations.modal.name') });
    }
    
    if (!auto.triggers || auto.triggers.length === 0) errs.triggers = t('errors.atLeastOneTrigger');
    else {
        auto.triggers.forEach((t_obj, i) => {
            if (t_obj.type === 'single' || t_obj.type === 'multi') {
                if (!t_obj.device_id) errs[`trigger_${i}_device`] = t('errors.triggerDeviceRequired', { num: i + 1 });
                if (!t_obj.button_id) errs[`trigger_${i}_button`] = t('errors.triggerButtonRequired', { num: i + 1 });
            } else if (t_obj.type === 'sequence') {
                if (!t_obj.sequence || t_obj.sequence.length < 2) errs[`trigger_${i}_sequence`] = t('errors.sequenceLength', { num: i + 1 });
            } else if (t_obj.type === 'device_inactivity') {
                if (!t_obj.device_id) errs[`trigger_${i}_device`] = t('errors.triggerDeviceRequired', { num: i + 1 });
                if (!t_obj.timeout_s || t_obj.timeout_s <= 0) errs[`trigger_${i}_timeout`] = t('errors.inactivityTimeoutRequired', { num: i + 1 });
            }
        });
    }

    if (!auto.actions || auto.actions.length === 0) errs.actions = t('errors.atLeastOneAction');
    
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
    @click.self="$emit('close')"
  >
    <div
      v-if="localAuto"
      class="bg-gray-900 border border-gray-700 rounded-lg max-w-3xl w-full max-h-[90vh] flex flex-col shadow-2xl animate-in fade-in scale-95 duration-200"
      data-tour-id="automation-modal"
      style="animation: slideInUp 0.3s ease-out;"
    >
      <div
        class="p-6 border-b border-gray-700 shrink-0 flex justify-between items-center"
        data-tour-id="automation-modal-header"
      >
        <div class="flex items-center gap-3">
          <h3 class="text-lg font-semibold">
            {{ isEditing ? t('automations.editAutomation') : t('automations.addAutomation') }}
          </h3>
          <button
            v-if="!isEditing"
            class="text-gray-500 hover:text-gray-300 transition-colors"
            :title="t('app.startTourDefault')"
            @click="startAutomationModalTour"
          >
            <i class="mdi mdi-help-circle-outline text-xl" />
          </button>
        </div>
        <label
          class="flex items-center gap-2 cursor-pointer"
          data-tour-id="automation-enabled-switch"
        >
          <span class="text-sm text-gray-300">{{ localAuto.enabled ? t('automations.modal.enabled') : t('automations.disabled') }}</span>
          <Switch v-model="localAuto.enabled" />
        </label>
      </div>
      
      <div class="p-6 space-y-4 overflow-y-auto min-h-0">
        <div data-tour-id="automation-name-input">
          <label class="block text-sm font-medium text-gray-300 mb-1">{{ t('automations.modal.name') }}</label>
          <input
            v-model="localAuto.name"
            :placeholder="t('automations.modal.placeholder')"
            class="w-full rounded p-2 text-sm"
            :class="{'border-red-500': liveErrors.name}"
          >
        </div>

        <div class="space-y-4">
          <div class="flex justify-between items-center">
            <h4
              class="text-sm font-bold text-yellow-400 flex items-center gap-2"
              data-tour-id="automation-triggers-section"
            >
              <i class="mdi mdi-lightning-bolt" /> {{ t('automations.modal.triggers') }}
            </h4>
          </div>
            
          <div
            v-for="(trigger, tIdx) in localAuto.triggers"
            :key="tIdx"
            class="bg-gray-800/50 p-4 rounded-lg border border-gray-700 relative"
          >
            <button
              class="absolute top-2 right-2 text-gray-500 hover:text-red-400"
              @click="removeTrigger(tIdx)"
            >
              <i class="mdi mdi-close" />
            </button>
                
            <div
              class="mb-4"
              data-tour-id="automation-trigger-type"
            >
              <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.triggerType') }}</label>
              <select
                v-model="trigger.type"
                class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
                @change="onTriggerTypeChange(trigger)"
              >
                <option value="single">
                  {{ t('automations.modal.triggerTypeSingle') }}
                </option>
                <option value="multi">
                  {{ t('automations.modal.triggerTypeMulti') }}
                </option>
                <option value="sequence">
                  {{ t('automations.modal.triggerTypeSequence') }}
                </option>
                <option value="device_inactivity">
                  {{ t('automations.modal.triggerTypeInactivity') }}
                </option>
              </select>
            </div>

            <label
              v-if="trigger.type !== 'single' && trigger.type !== 'device_inactivity'"
              class="mb-4 flex items-center justify-between bg-gray-900 p-2 rounded border border-gray-600 cursor-pointer"
              data-tour-id="automation-strict-mode"
            >
              <div>
                <span class="text-xs font-bold text-gray-200 block">{{ t('automations.modal.strictMode') }}</span>
                <span class="text-[10px] text-gray-400 block">
                  {{ trigger.type === 'sequence' ? t('automations.modal.strictModeDescSequence') : t('automations.modal.strictModeDescMulti') }}
                </span>
              </div>
              <Switch
                :model-value="trigger.reset_on_other_input ?? false"
                @update:model-value="val => trigger.reset_on_other_input = val"
              />
            </label>

            <div
              v-if="trigger.type === 'single' || trigger.type === 'multi'"
              class="grid grid-cols-2 gap-4"
              data-tour-id="automation-trigger-device-selection"
            >
              <div>
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.device') }}</label>
                <select
                  v-model="trigger.device_id"
                  class="w-full rounded p-2 text-sm bg-gray-900"
                  :class="liveErrors['trigger_' + tIdx + '_device'] ? 'border-red-500' : 'border-gray-600'"
                  @change="onTriggerDeviceChange(trigger)"
                >
                  <option
                    value=""
                    disabled
                  >
                    {{ t('automations.modal.selectDevice') }}
                  </option>
                  <option
                    v-for="dev in devices"
                    :key="dev.id"
                    :value="dev.id"
                  >
                    {{ dev.name }}
                  </option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.button') }}</label>
                <select
                  v-model="trigger.button_id"
                  class="w-full rounded p-2 text-sm bg-gray-900"
                  :class="liveErrors['trigger_' + tIdx + '_button'] ? 'border-red-500' : 'border-gray-600'"
                  :disabled="!trigger.device_id"
                >
                  <option
                    value=""
                    disabled
                  >
                    {{ t('automations.modal.selectButton') }}
                  </option>
                  <option
                    v-for="btn in deviceStore.getButtonsForDevice(trigger.device_id)"
                    :key="btn.id"
                    :value="btn.id"
                  >
                    {{ btn.name }}
                  </option>
                </select>
              </div>
            </div>

            <div
              v-if="trigger.type === 'multi'"
              class="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-gray-700"
              data-tour-id="automation-multi-options"
            >
              <div>
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.pressCount') }}</label>
                <input
                  v-model.number="trigger.count"
                  type="number"
                  class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
                  min="2"
                >
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.withinTime') }}</label>
                <input
                  v-model.number="trigger.window_ms"
                  type="number"
                  class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
                  min="100"
                  step="100"
                >
              </div>
            </div>
                

            <div
              v-if="trigger.type === 'sequence'"
              class="space-y-2"
              data-tour-id="automation-sequence-options"
            >
              <div 
                v-for="(step, idx) in trigger.sequence" 
                :key="idx" 
                class="flex items-center gap-2 bg-gray-900 p-2 rounded border border-gray-700 cursor-move transition-all duration-200"
                :class="[
                  getSequenceStepClass(tIdx, idx),
                  liveErrors['trigger_' + tIdx + '_sequence'] ? 'border-red-500' : ''
                ]"
                draggable="true"
                @dragstart="onDragStart($event, idx, 'sequence', tIdx)"
                @dragover.prevent="onDragOver(idx, `sequence-${tIdx}`)"
                @drop="onDrop($event, idx, `sequence-${tIdx}`)"
                @dragend="onDragEnd"
              >
                <div class="text-gray-500 font-mono text-xs w-6 text-center">
                  {{ idx + 1 }}
                </div>
                <select
                  v-model="step.device_id"
                  class="rounded p-1 text-xs bg-gray-800 border-gray-600 flex-1"
                  @change="step.button_id = deviceStore.getButtonsForDevice(step.device_id)[0]?.id || ''"
                >
                  <option
                    v-for="dev in devices"
                    :key="dev.id"
                    :value="dev.id"
                  >
                    {{ dev.name }}
                  </option>
                </select>
                <select
                  v-model="step.button_id"
                  class="rounded p-1 text-xs bg-gray-800 border-gray-600 flex-1"
                >
                  <option
                    v-for="btn in deviceStore.getButtonsForDevice(step.device_id)"
                    :key="btn.id"
                    :value="btn.id"
                  >
                    {{ btn.name }}
                  </option>
                </select>
                <button
                  class="text-gray-500 hover:text-red-400 p-1"
                  @click="removeSequenceStep(trigger, idx)"
                >
                  <i class="mdi mdi-close" />
                </button>
              </div>
                    
              <div class="flex justify-center mt-2">
                <button
                  class="btn btn-sm btn-secondary border-dashed w-full"
                  @click="addSequenceStep(trigger)"
                >
                  <i class="mdi mdi-plus" /> {{ t('automations.modal.addStep') }}
                </button>
              </div>

              <div class="mt-4 pt-4 border-t border-gray-700">
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.maxTimeBetween') }}</label>
                <div class="flex items-center gap-2">
                  <input
                    v-model.number="trigger.window_ms"
                    type="number"
                    class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
                    min="100"
                    step="100"
                  >
                  <span class="text-xs text-gray-400">{{ t('automations.modal.maxTimeBetweenDesc') }}</span>
                </div>
              </div>
            </div>

            <!-- DEVICE INACTIVITY TRIGGER -->
            <div
              v-if="trigger.type === 'device_inactivity'"
              class="space-y-4"
              data-tour-id="automation-inactivity-options"
            >
              <!-- Device selector -->
              <div>
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.inactivityDevice') }}</label>
                <select
                  v-model="trigger.device_id"
                  class="w-full rounded p-2 text-sm bg-gray-900"
                  :class="liveErrors['trigger_' + tIdx + '_device'] ? 'border-red-500' : 'border-gray-600'"
                  @change="trigger.button_filter = null; trigger.button_exclude = null"
                >
                  <option
                    value=""
                    disabled
                  >
                    {{ t('automations.modal.selectDevice') }}
                  </option>
                  <option
                    v-for="dev in devices"
                    :key="dev.id"
                    :value="dev.id"
                  >
                    {{ dev.name }}
                  </option>
                </select>
              </div>

              <!-- Timeout -->
              <div>
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.inactivityTimeout') }}</label>
                <input
                  v-model.number="trigger.timeout_s"
                  type="number"
                  class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
                  min="1"
                  step="1"
                >
                <span class="text-[10px] text-gray-500 mt-1 block">{{ t('automations.modal.inactivityTimeoutDesc') }}</span>
              </div>

              <!-- Watch mode -->
              <div>
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.inactivityWatchMode') }}</label>
                <select
                  v-model="trigger.watch_mode"
                  class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
                >
                  <option value="received">
                    {{ t('automations.modal.inactivityWatchReceived') }}
                  </option>
                  <option value="sent">
                    {{ t('automations.modal.inactivityWatchSent') }}
                  </option>
                  <option value="both">
                    {{ t('automations.modal.inactivityWatchBoth') }}
                  </option>
                </select>
              </div>

              <!-- Re-arm mode -->
              <div>
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.inactivityRearmMode') }}</label>
                <select
                  v-model="trigger.rearm_mode"
                  class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
                >
                  <option value="always">
                    {{ t('automations.modal.inactivityRearmAlways') }}
                  </option>
                  <option value="cooldown">
                    {{ t('automations.modal.inactivityRearmCooldown') }}
                  </option>
                  <option value="never">
                    {{ t('automations.modal.inactivityRearmNever') }}
                  </option>
                </select>
              </div>

              <!-- Cooldown (only relevant when rearm_mode == "cooldown") -->
              <div v-if="trigger.rearm_mode === 'cooldown'">
                <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.inactivityCooldown') }}</label>
                <input
                  v-model.number="trigger.cooldown_s"
                  type="number"
                  class="w-full rounded p-2 text-sm bg-gray-900 border-gray-600"
                  min="0"
                  step="1"
                >
                <span class="text-[10px] text-gray-500 mt-1 block">{{ t('automations.modal.inactivityCooldownDesc') }}</span>
              </div>

              <!-- Advanced options (collapsible) -->
              <details class="bg-gray-900/60 rounded border border-gray-700">
                <summary class="text-xs font-medium text-gray-400 p-3 cursor-pointer select-none hover:text-gray-200 transition-colors">
                  <i class="mdi mdi-tune-variant mr-1" />{{ t('automations.modal.inactivityAdvanced') }}
                </summary>
                <div class="p-3 space-y-4 border-t border-gray-700 mt-0">
                  <!-- Button whitelist -->
                  <div v-if="trigger.device_id">
                    <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.inactivityButtonFilter') }}</label>
                    <span class="text-[10px] text-gray-500 block mb-2">{{ t('automations.modal.inactivityButtonFilterDesc') }}</span>
                    <div class="flex flex-wrap gap-1">
                      <button
                        v-for="btn in deviceStore.getButtonsForDevice(trigger.device_id)"
                        :key="btn.id"
                        class="px-2 py-1 text-xs rounded border transition-colors"
                        :class="trigger.button_filter && trigger.button_filter.includes(btn.id)
                          ? 'bg-green-600/30 border-green-500 text-green-300'
                          : 'bg-gray-800 border-gray-600 text-gray-400 hover:border-gray-400'"
                        @click="toggleButtonInList(trigger, 'button_filter', btn.id)"
                      >
                        {{ btn.name }}
                      </button>
                    </div>
                    <p
                      v-if="!trigger.button_filter"
                      class="text-[10px] text-gray-500 mt-1"
                    >
                      ({{ t('automations.modal.selectButton') }} — all buttons active)
                    </p>
                  </div>

                  <!-- Button blacklist -->
                  <div v-if="trigger.device_id">
                    <label class="block text-xs font-medium text-gray-300 mb-1">{{ t('automations.modal.inactivityButtonExclude') }}</label>
                    <span class="text-[10px] text-gray-500 block mb-2">{{ t('automations.modal.inactivityButtonExcludeDesc') }}</span>
                    <div class="flex flex-wrap gap-1">
                      <button
                        v-for="btn in deviceStore.getButtonsForDevice(trigger.device_id)"
                        :key="btn.id"
                        class="px-2 py-1 text-xs rounded border transition-colors"
                        :class="trigger.button_exclude && trigger.button_exclude.includes(btn.id)
                          ? 'bg-red-600/30 border-red-500 text-red-300'
                          : 'bg-gray-800 border-gray-600 text-gray-400 hover:border-gray-400'"
                        @click="toggleButtonInList(trigger, 'button_exclude', btn.id)"
                      >
                        {{ btn.name }}
                      </button>
                    </div>
                  </div>

                  <!-- require_initial_activity -->
                  <label class="flex items-center justify-between bg-gray-800 p-2 rounded border border-gray-700 cursor-pointer">
                    <div>
                      <span class="text-xs font-bold text-gray-200 block">{{ t('automations.modal.inactivityRequireInitial') }}</span>
                      <span class="text-[10px] text-gray-400 block">{{ t('automations.modal.inactivityRequireInitialDesc') }}</span>
                    </div>
                    <Switch
                      :model-value="trigger.require_initial_activity ?? true"
                      @update:model-value="val => trigger.require_initial_activity = val"
                    />
                  </label>

                  <!-- ignore_own_actions -->
                  <label class="flex items-center justify-between bg-gray-800 p-2 rounded border border-gray-700 cursor-pointer">
                    <div>
                      <span class="text-xs font-bold text-gray-200 block">{{ t('automations.modal.inactivityIgnoreOwn') }}</span>
                      <span class="text-[10px] text-gray-400 block">{{ t('automations.modal.inactivityIgnoreOwnDesc') }}</span>
                    </div>
                    <Switch
                      :model-value="trigger.ignore_own_actions ?? true"
                      @update:model-value="val => trigger.ignore_own_actions = val"
                    />
                  </label>
                </div>
              </details>
            </div>
          </div>
        </div>


        <div class="flex gap-2 mt-4 justify-center">
          <button
            class="btn btn-sm btn-secondary border-dashed"
            @click="addTrigger"
          >
            <i class="mdi mdi-plus" /> {{ t('automations.modal.addTrigger') }}
          </button>
        </div>

        <div>
          <h4
            class="text-sm font-bold text-blue-400 mb-3 flex items-center gap-2"
            data-tour-id="automation-actions-section"
          >
            <i class="mdi mdi-play-circle-outline" /> {{ t('automations.modal.actions') }}
          </h4>
            
          <ActionList 
            :actions="localAuto.actions" 
            :devices="devices"
            :app-mode="appMode"
            :dragging-item="draggingItem"
            :drag-over-item="dragOverItem"
            @add-action="addAction"
            @remove-action="removeAction"
            @action-device-change="onActionDeviceChange"
            @drag-start="onDragStart"
            @drop="onDrop"
            @drag-end="onDragEnd"
            @drag-over="onDragOver"
          />
        </div>

        <label
          class="bg-gray-800/50 p-4 rounded-lg border border-gray-700 flex items-center justify-between cursor-pointer"
          data-tour-id="automation-parallel-switch"
        >
          <div>
            <span class="text-sm font-bold text-gray-200 block">{{ t('automations.modal.allowParallel') }}</span>
            <span class="text-xs text-gray-400 block">{{ t('automations.modal.parallelDesc') }}</span>
          </div>
          <Switch
            :model-value="localAuto.allow_parallel ?? false"
            @update:model-value="val => { if (localAuto) localAuto.allow_parallel = val }"
          />
        </label>
        
        <div
          v-if="appMode === 'home_assistant'"
          class="bg-gray-800/50 p-4 rounded-lg border border-gray-700"
          data-tour-id="automation-ha-section"
        >
          <h4 class="text-sm font-bold text-indigo-400 mb-3 flex items-center gap-2">
            <i class="mdi mdi-home-assistant" /> {{ t('automations.modal.haIntegration') }}
          </h4>
          <div class="space-y-3">
            <label class="flex items-center justify-between bg-gray-900 p-3 rounded border border-gray-700 cursor-pointer">
              <div class="max-w-xs">
                <span class="text-sm font-bold text-gray-200 block">{{ t('automations.modal.exposeAsButton') }}</span>
                <span class="text-xs text-gray-400 block">
                  {{ t('automations.modal.exposeDesc') }}
                </span>
              </div>
              <Switch
                :model-value="localAuto.ha_expose_button ?? false"
                @update:model-value="val => { if (localAuto) localAuto.ha_expose_button = val }"
              />
            </label>
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
          @click="$emit('close')"
        >
          {{ t('confirm.cancel') }}
        </button>
        <button
          class="btn btn-primary"
          :disabled="!isValid"
          :class="{'opacity-50 cursor-not-allowed': !isValid}"
          data-tour-id="automation-save-button"
          @click="save"
        >
          {{ t('automations.modal.save') }}
        </button>
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