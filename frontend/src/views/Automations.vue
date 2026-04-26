<script setup lang="ts">
import { storeToRefs } from 'pinia';
import { ref, onMounted, onUnmounted } from 'vue';
import { useAutomationsStore, Automation } from '../stores/automations';
import { useDeviceStore } from '../stores/devices';
import { useSettingsStore } from '../stores/settings';
import { useDragDrop } from '../composables/useDragDrop';
import { useI18n } from '../i18n';

const automationsStore = useAutomationsStore();
const deviceStore = useDeviceStore();
const settingsStore = useSettingsStore();
const { t } = useI18n();

const { automations, editingAutomation, runningAutomations, triggerProgress, flashingActions, inactivityStates } = storeToRefs(automationsStore);
const { devices, flashingReceiveButtons, flashingIgnoredButtons } = storeToRefs(deviceStore);
const { appMode } = storeToRefs(settingsStore);

// Reactive timestamp updated every second to drive countdown displays
const now = ref(Date.now() / 1000);
let nowTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => { nowTimer = setInterval(() => { now.value = Date.now() / 1000; }, 1000); });
onUnmounted(() => { if (nowTimer) clearInterval(nowTimer); });

/**
 * Returns the remaining seconds for an armed inactivity trigger,
 * or null when the trigger is not currently armed.
 */
const getInactivityRemaining = (autoId: string, triggerIndex: number): number | null => {
    const key = `${autoId}_${triggerIndex}`;
    const state = inactivityStates.value.get(key);
    if (!state || state.state !== 'armed' || !state.armed_at || !state.timeout_s) return null;
    const remaining = (state.armed_at + state.timeout_s) - now.value;
    return remaining > 0 ? remaining : 0;
};

/**
 * Returns the remaining cooldown seconds, or null when not in cooldown.
 */
const getInactivityCooldownRemaining = (autoId: string, triggerIndex: number): number | null => {
    const key = `${autoId}_${triggerIndex}`;
    const state = inactivityStates.value.get(key);
    if (!state || state.state !== 'cooldown' || !state.cooldown_until) return null;
    const remaining = state.cooldown_until - now.value;
    return remaining > 0 ? remaining : 0;
};


const openAddModal = () => {
    editingAutomation.value = {
        id: '',
        name: '',
        enabled: true,
        triggers: [{
            type: 'single',
            device_id: '',
            button_id: '',
            count: 1,
            window_ms: 2000,
            sequence: [],
            reset_on_other_input: true,
            timeout_s: 30,
            watch_mode: 'received',
            button_filter: null,
            button_exclude: null,
            rearm_mode: 'always',
            cooldown_s: 0,
            require_initial_activity: true,
            ignore_own_actions: true,
        }],
        actions: []
    } as Automation;
};

const openEditModal = (auto: Automation) => {
    editingAutomation.value = JSON.parse(JSON.stringify(auto));
};

const isRunning = (id: string) => runningAutomations.value.has(id);
const getRunningCount = (id: string) => runningAutomations.value.get(id)?.count || 0;

// Returns the color index if this action is active for any running instance
const getActiveInstanceColor = (id: string, actionIdx: number) => {
    const state = runningAutomations.value.get(id);
    if (!state || !state.instances) return -1;
    
    // Find the last instance (most recent) that is at this step
    for (const [, inst] of state.instances) {
        if (inst.actionIndex === actionIdx) return inst.colorIdx;
    }
    return -1;
};

const colorClasses = [
    { border: 'border-blue-500', bg: 'bg-blue-900/30', text: 'text-blue-400' },
    { border: 'border-green-500', bg: 'bg-green-900/30', text: 'text-green-400' },
    { border: 'border-purple-500', bg: 'bg-purple-900/30', text: 'text-purple-400' },
    { border: 'border-pink-500', bg: 'bg-pink-900/30', text: 'text-pink-400' },
    { border: 'border-orange-500', bg: 'bg-orange-900/30', text: 'text-orange-400' },
    { border: 'border-cyan-500', bg: 'bg-cyan-900/30', text: 'text-cyan-400' },
];

const getFlashColorIndex = (autoId: string, actionIndex: number) => {
    if (!settingsStore.settings.enableUiIndications || !flashingActions.value.has(autoId)) return -1;
    const map = flashingActions.value.get(autoId);
    return map?.has(actionIndex) ? map.get(actionIndex) ?? -1 : -1;
};
const getTriggerProgress = (id: string, triggerIndex: number) => {
    const key = `${id}_${triggerIndex}`;
    return triggerProgress.value.get(key)?.current || 0;
};

const { 
    draggingIndex, 
    dragOverIndex, 
    onDragStart, 
    onDragOver, 
    onDrop, 
    onDragEnd 
} = useDragDrop((fromIndex, toIndex) => {
    const newOrder = [...automations.value];
    const [moved] = newOrder.splice(fromIndex, 1);
    newOrder.splice(toIndex, 0, moved);
    automationsStore.reorderAutomations(newOrder.map(a => a.id));
});

const getStepClass = (id: string, triggerIndex: number, sIdx: number) => {
    if (!settingsStore.settings.enableUiIndications) return 'bg-gray-900 border-gray-600 text-gray-400';
    const progress = getTriggerProgress(id, triggerIndex);
    if (progress > sIdx) return 'bg-yellow-500/40 border-yellow-500 text-yellow-400';
    if (progress === sIdx && progress > 0) return 'bg-blue-500/40 border-blue-500 text-blue-400 animate-pulse shadow-[0_0_15px_rgba(59,130,246,0.5)]';
    return 'bg-gray-900 border-gray-600 text-gray-400';
};
</script>

<template>
  <div class="space-y-4">
    <!-- LIST -->
    <div
      v-if="automations.length === 0"
      class="text-center text-gray-500 mt-10"
    >
      <i class="mdi mdi-robot-off text-6xl mb-2" />
      <p class="font-bold">
        {{ t('automations.noAutomations') }}
      </p>
      <p
        v-if="devices.length > 0"
        class="text-sm"
      >
        {{ t('automations.noAutomationsDesc') }}
      </p>
      <p
        v-else
        class="text-sm"
      >
        {{ t('automations.noDevicesDesc') }}
      </p>
    </div>

    <div
      v-else
      class="grid grid-cols-1 gap-4 items-start"
    >
      <div 
        v-for="(auto, index) in automations" 
        :key="auto.id" 
        data-tour-id="automation-card"
        class="card relative group transition-all duration-200 flex flex-col p-0 overflow-hidden" 
        :class="[
          settingsStore.settings.enableUiIndications && isRunning(auto.id) ? 'border-blue-500 shadow-lg shadow-blue-500/10' : '',
          draggingIndex === index ? 'opacity-40' : '',
          dragOverIndex === index && draggingIndex !== index ? 'border-blue-500 bg-gray-800/50' : '',
          dragOverIndex === index && (draggingIndex ?? -1) > index ? 'border-t-4 border-t-blue-500' : '',
          dragOverIndex === index && (draggingIndex ?? -1) < index ? 'border-b-4 border-b-blue-500' : ''
        ]"
        @dragover.prevent="onDragOver(index)"
        @drop="onDrop($event, index, 'automation')"
        @dragend="onDragEnd"
      >
        <div class="flex items-start justify-between px-4 py-3 border-b border-gray-700 bg-gray-800/20">
          <div class="flex items-center gap-3">
            <div
              class="p-2 rounded-lg relative"
              :class="auto.enabled ? 'bg-blue-500/20 text-blue-400' : 'bg-gray-700 text-gray-500'"
            >
              <i class="mdi mdi-robot text-xl" />
              <div
                v-if="getRunningCount(auto.id) > 1"
                class="absolute -top-2 -right-2 bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full border border-gray-800 shadow-sm z-10"
              >
                {{ getRunningCount(auto.id) }}x
              </div>
            </div>
            <div>
              <h3
                class="font-semibold text-sm"
                :class="{'text-gray-500': !auto.enabled}"
              >
                {{ auto.name }}
              </h3>
              <p
                v-if="!auto.enabled"
                class="text-xs text-gray-400"
              >
                ({{ t('automations.disabled') }})
              </p>
            </div>
          </div>
          <div
            class="flex items-center gap-2"
            data-tour-id="automation-action-buttons"
          >
            <button 
              :disabled="!auto.enabled || (isRunning(auto.id) && !auto.allow_parallel)" 
              :class="{'text-gray-500': !auto.enabled || (isRunning(auto.id) && !auto.allow_parallel), 'hover:text-gray-200': auto.enabled && (!isRunning(auto.id) || auto.allow_parallel)}" 
              class="text-gray-500 disabled:opacity-50 disabled:cursor-not-allowed" 
              :title="t('automations.triggerAutomation')"
              @click="automationsStore.triggerAutomation(auto.id)"
            >
              <i class="mdi mdi-play-circle-outline" />
            </button>
            <button
              class="text-gray-500 hover:text-blue-400"
              :title="t('automations.editAutomation')"
              @click="openEditModal(auto)"
            >
              <i class="mdi mdi-pencil-outline" />
            </button>
            <button
              class="text-gray-500 hover:text-green-400"
              :title="t('automations.duplicateAutomation')"
              @click="automationsStore.duplicateAutomation(auto.id)"
            >
              <i class="mdi mdi-content-copy" />
            </button>
            <button
              class="text-gray-500 hover:text-red-400"
              :title="t('automations.deleteAutomation')"
              @click="automationsStore.deleteAutomation(auto.id, $event)"
            >
              <i class="mdi mdi-delete-outline" />
            </button>
          </div>
        </div>

        <!-- VISUAL FLOW -->
        <div class="flex items-center gap-2 overflow-x-auto px-4 py-4 scrollbar-thin bg-gray-900">
          <!-- TRIGGERS -->
          <div class="flex flex-col gap-2">
            <div
              v-for="(trigger, tIdx) in auto.triggers"
              :key="tIdx"
              class="flex items-center gap-2"
            >
              <div
                v-if="tIdx > 0"
                class="text-[10px] font-bold text-gray-500 uppercase px-1"
              >
                {{ t('automations.or') }}
              </div>
              <div class="flex items-center gap-2 flex-shrink-0 bg-gray-700 rounded px-3 py-2 border border-gray-700 min-w-[200px]">
                <i class="mdi mdi-lightning-bolt text-yellow-400" />
                <div class="text-sm w-full">
                  <!-- SEQUENCE DISPLAY -->
                  <div v-if="trigger.type === 'sequence'">
                    <div class="flex flex-wrap gap-1 mb-1">
                      <div
                        v-for="(step, sIdx) in trigger.sequence"
                        :key="sIdx"
                        class="flex items-center gap-1 px-2 py-1 rounded border text-xs transition-all duration-200"
                        :class="getStepClass(auto.id, tIdx, sIdx)"
                      >
                        <i
                          class="mdi"
                          :class="[`mdi-${deviceStore.getButtonIcon(step.device_id, step.button_id)}`, settingsStore.settings.enableUiIndications && flashingReceiveButtons.has(step.button_id) ? 'flash-text-receive' : (settingsStore.settings.enableUiIndications && flashingIgnoredButtons.has(step.button_id) ? 'flash-text-ignore' : '')]"
                        />
                        <span class="font-bold">{{ deviceStore.getButtonName(step.device_id, step.button_id) }}</span>
                      </div>
                    </div>
                    <div class="text-[10px] text-gray-500 flex justify-between items-center">
                      <span>{{ t('automations.sequenceMax', { ms: trigger.window_ms ?? 0 }) }}</span>
                      <span
                        v-if="settingsStore.settings.enableUiIndications && getTriggerProgress(auto.id, tIdx) > 0"
                        class="text-blue-400 font-bold animate-pulse ml-2"
                      >{{ t('automations.active') }}</span>
                    </div>
                  </div>
                  <!-- DEVICE INACTIVITY DISPLAY -->
                  <div v-else-if="trigger.type === 'device_inactivity'">
                    <div class="flex items-center gap-1 font-bold">
                      <i class="mdi mdi-timer-sand-empty text-orange-400" />
                      <span>{{ deviceStore.getDeviceName(trigger.device_id) }}</span>
                    </div>
                    <div class="text-[10px] text-gray-500 mt-1">
                      {{ trigger.timeout_s }}s inactivity
                    </div>
                    <!-- Live inactivity state indicator (only when UI indications are on) -->
                    <template v-if="settingsStore.settings.enableUiIndications">
                      <!-- Armed: countdown bar -->
                      <div
                        v-if="getInactivityRemaining(auto.id, tIdx) !== null"
                        class="mt-2"
                      >
                        <div class="flex items-center justify-between text-[10px] mb-0.5">
                          <span class="text-orange-400 font-bold animate-pulse flex items-center gap-1">
                            <i class="mdi mdi-timer-outline" />
                            {{ t('automations.active') }}
                          </span>
                          <span class="text-orange-300 font-mono">
                            {{ Math.ceil(getInactivityRemaining(auto.id, tIdx)!) }}s
                          </span>
                        </div>
                        <div class="w-full h-1 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            class="h-full bg-orange-500 rounded-full transition-all duration-1000"
                            :style="{
                              width: `${(getInactivityRemaining(auto.id, tIdx)! / (trigger.timeout_s ?? 1)) * 100}%`
                            }"
                          />
                        </div>
                      </div>
                      <!-- Cooldown indicator -->
                      <div
                        v-else-if="getInactivityCooldownRemaining(auto.id, tIdx) !== null"
                        class="mt-1 text-[10px] text-blue-400 flex items-center gap-1"
                      >
                        <i class="mdi mdi-clock-outline" />
                        cooldown {{ Math.ceil(getInactivityCooldownRemaining(auto.id, tIdx)!) }}s
                      </div>
                    </template>
                  </div>
                  <!-- SINGLE / MULTI DISPLAY -->
                  <div v-else>
                    <div class="font-bold">
                      <span
                        v-if="trigger.type === 'multi'"
                        class="mr-1 transition-colors duration-200"
                        :class="settingsStore.settings.enableUiIndications && getTriggerProgress(auto.id, tIdx) > 0 ? 'text-yellow-400' : 'text-blue-400'"
                      >
                        {{ (settingsStore.settings.enableUiIndications && getTriggerProgress(auto.id, tIdx) > 0) ? getTriggerProgress(auto.id, tIdx) : trigger.count }}x
                      </span>
                      <span :class="settingsStore.settings.enableUiIndications && flashingReceiveButtons.has(trigger.button_id) ? 'flash-text-receive inline-block' : (settingsStore.settings.enableUiIndications && flashingIgnoredButtons.has(trigger.button_id) ? 'flash-text-ignore inline-block' : '')">
                        {{ deviceStore.getButtonName(trigger.device_id, trigger.button_id) }}
                      </span>
                    </div>
                    <div class="text-xs text-gray-500">
                      {{ deviceStore.getDeviceName(trigger.device_id) }}
                      <span
                        v-if="trigger.type === 'multi'"
                        class="text-[10px] ml-1 opacity-75"
                      >{{ t('automations.withinMs', { ms: trigger.window_ms ?? 0 }) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ARROW -->
          <i class="mdi mdi-arrow-right text-gray-500" />

          <!-- ACTIONS -->
          <template
            v-for="(action, idx) in auto.actions"
            :key="idx"
          >
            <div 
              class="flex items-center gap-2 flex-shrink-0 bg-gray-900 rounded px-3 py-2 border transition-colors duration-200" 
              :class="[
                settingsStore.settings.enableUiIndications && getActiveInstanceColor(auto.id, idx) !== -1 ? `${colorClasses[getActiveInstanceColor(auto.id, idx)].border} ${colorClasses[getActiveInstanceColor(auto.id, idx)].bg}` : 'border-gray-700',
                getFlashColorIndex(auto.id, idx) !== -1 ? `action-running-${getFlashColorIndex(auto.id, idx)}` : ''
              ]"
            >
              <template v-if="action.type === 'delay'">
                <i class="mdi mdi-timer-sand text-blue-400" />
                <span class="font-mono text-sm">{{ action.delay_ms }}ms</span>
              </template>
              <template v-else-if="action.type === 'ir_send'">
                <i
                  class="mdi text-green-400"
                  :class="`mdi-${deviceStore.getButtonIcon(action.device_id || '', action.button_id || '')}`"
                />
                <div class="text-sm">
                  <div class="font-bold">
                    {{ deviceStore.getButtonName(action.device_id || '', action.button_id || '') }}
                  </div>
                  <div class="text-xs text-gray-500">
                    {{ deviceStore.getDeviceName(action.device_id || '') }}
                    <span
                      v-if="action.target"
                      class="text-xs text-blue-300 ml-1"
                    >{{ t('automations.viaTarget', { target: action.target }) }}</span>
                  </div>
                </div>
              </template>
              <template v-else-if="action.type === 'event'">
                <!-- HA Mode Display -->
                <template v-if="appMode === 'home_assistant'">
                  <i class="mdi mdi-home-assistant text-indigo-400" />
                  <div class="text-sm">
                    <div class="font-bold">
                      {{ t('actionList.fireHaEvent') }}
                    </div>
                    <div class="text-xs text-gray-500">
                      {{ action.event_name }}
                    </div>
                  </div>
                </template>
                <!-- Standalone Mode Display -->
                <template v-else>
                  <i class="mdi mdi-lightning-bolt text-yellow-400" />
                  <div class="text-sm">
                    <div class="font-bold">
                      {{ t('actionList.fireEvent') }}
                    </div>
                    <div class="text-xs text-gray-500">
                      {{ action.event_name }}
                    </div>
                  </div>
                </template>
              </template>
            </div>
                    
            <i
              v-if="idx < auto.actions.length - 1"
              class="mdi mdi-arrow-right text-gray-500"
            />
          </template>
        </div>

        <div
          class="absolute bottom-1 right-1 p-2 cursor-move text-gray-500 hover:text-gray-400 rounded hover:bg-gray-800/50 transition-colors"
          draggable="true"
          :title="t('automations.dragToReorder')"
          @dragstart="onDragStart($event, index, 'automation')"
        >
          <i class="mdi mdi-drag text-xl" />
        </div>
      </div>
    </div>

    <!-- ADD BUTTON -->
    <div class="fixed bottom-6 right-6 z-20 group">
      <button
        v-if="devices.length > 0"
        class="flex items-center bg-blue-600 text-white font-bold rounded-full shadow-lg hover:bg-blue-700 transition-all duration-300 ease-in-out px-4 py-3"
        data-tour-id="create-automation-button"
        @click="openAddModal"
      >
        <i class="mdi mdi-plus text-xl transition-transform duration-300 group-hover:rotate-90" />
        <span class="max-w-0 group-hover:max-w-xs group-hover:ml-3 transition-all duration-300 ease-in-out overflow-hidden whitespace-nowrap">{{ t('automations.addAutomation') }}</span>
      </button>
      <div
        v-else
        class="relative"
      >
        <button
          disabled
          class="flex items-center gap-3 bg-gray-600 text-gray-400 font-bold rounded-full shadow-lg cursor-not-allowed px-4 py-3"
          data-tour-id="create-automation-button-disabled"
        >
          <i class="mdi mdi-plus text-xl" />
        </button>
        <div class="absolute bottom-full mb-2 right-0 w-max bg-gray-800 text-gray-200 text-xs rounded py-1 px-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          {{ t('automations.noDevicesDesc') }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes flash-0 { 50% { background-color: rgba(59, 130, 246, 0.4); } }
@keyframes flash-1 { 50% { background-color: rgba(34, 197, 94, 0.4); } }
@keyframes flash-2 { 50% { background-color: rgba(168, 85, 247, 0.4); } }
@keyframes flash-3 { 50% { background-color: rgba(236, 72, 153, 0.4); } }
@keyframes flash-4 { 50% { background-color: rgba(249, 115, 22, 0.4); } }
@keyframes flash-5 { 50% { background-color: rgba(6, 182, 212, 0.4); } }

.action-running-0 { animation: flash-0 600ms ease-out; }
.action-running-1 { animation: flash-1 600ms ease-out; }
.action-running-2 { animation: flash-2 600ms ease-out; }
.action-running-3 { animation: flash-3 600ms ease-out; }
.action-running-4 { animation: flash-4 600ms ease-out; }
.action-running-5 { animation: flash-5 600ms ease-out; }
</style>