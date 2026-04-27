import { defineStore } from 'pinia';
import { ref, reactive } from 'vue';
import { api } from '../services/api';
import { useCommonStore } from './common';
import { useSettingsStore } from './settings';
import { t } from '../i18n';

export interface AutomationTrigger {
    type: 'single' | 'multi' | 'sequence' | 'device_inactivity';
    // single / multi / sequence
    device_id: string;
    button_id: string;
    count?: number;
    window_ms?: number;
    sequence?: { device_id: string; button_id: string }[];
    reset_on_other_input?: boolean;
    // device_inactivity
    timeout_s?: number;
    watch_mode?: 'received' | 'sent' | 'both';
    button_filter?: string[] | null;
    button_exclude?: string[] | null;
    rearm_mode?: 'always' | 'cooldown' | 'never';
    cooldown_s?: number;
    require_initial_activity?: boolean;
    ignore_own_actions?: boolean;
}

export interface AutomationAction {
    type: 'delay' | 'ir_send' | 'event';
    delay_ms?: number;
    device_id?: string;
    button_id?: string;
    event_name?: string;
    target?: string;
}

export interface Automation {
    id: string;
    name: string;
    enabled: boolean;
    triggers: AutomationTrigger[];
    actions: AutomationAction[];
    allow_parallel?: boolean;
    ha_expose_button?: boolean;
}

interface RunningAutomation {
    count: number;
    nextColorIdx: number;
    instances: Map<string, { colorIdx: number; actionIndex?: number }>;
}

interface AutomationProgressMessage {
    id: string;
    run_id?: string;
    status: 'running' | 'idle';
    running_count?: number;
    current_action_index?: number;
}

interface TriggerProgressMessage {
    id: string;
    trigger_index: number;
    current: number;
    target: number;
}

export interface InactivityTriggerState {
    /** Current state of the trigger. */
    state: 'armed' | 'idle' | 'fired' | 'cooldown';
    /** Total inactivity timeout in seconds (present when state === "armed"). */
    timeout_s?: number;
    /** Unix timestamp (seconds) when the timer was armed. */
    armed_at?: number;
    /** Cooldown duration in seconds (present when state === "cooldown"). */
    cooldown_s?: number;
    /** Unix timestamp when the cooldown ends (present when state === "cooldown"). */
    cooldown_until?: number;
}

interface InactivityStateMessage extends InactivityTriggerState {
    id: string;
    trigger_index: number;
}

export const useAutomationsStore = defineStore('automations', () => {
    const commonStore = useCommonStore();
    const settingsStore = useSettingsStore();
    const automations = ref<Automation[]>([]);
    const editingAutomation = ref<Automation | null>(null);
    const runningAutomations = reactive(new Map<string, RunningAutomation>());
    const flashingActions = reactive(new Map<string, Map<number, number>>());
    const triggerProgress = reactive(new Map<string, { current: number; target: number }>());
    // Keyed by "automationId_triggerIndex", mirrors the backend InactivityState.
    const inactivityStates = reactive(new Map<string, InactivityTriggerState>());

    const fetchAutomations = async () => {
        const result = await api<Automation[]>('automations');
        automations.value = Array.isArray(result) ? result : [];

        // Remove inactivity state entries for automations that no longer exist.
        const liveIds = new Set(automations.value.map(a => a.id));
        for (const key of inactivityStates.keys()) {
            const autoId = key.split('_')[0];
            if (!liveIds.has(autoId)) {
                inactivityStates.delete(key);
            }
        }
    };

    const deleteAutomation = async (id: string, event: MouseEvent) => {
        if (await commonStore.askConfirm(t('store.deleteAutomationTitle'), t('store.deleteAutomationConfirm'), 'danger', t('confirm.confirm'), event)) {
            await api(`automations/${id}`, { method: 'DELETE' });
            await fetchAutomations();
            commonStore.addFlashMessage(t('store.automationDeleted'), 'success');
        }
    };

    const duplicateAutomation = async (id: string) => {
        await api(`automations/${id}/duplicate`, { method: 'POST' });
        await fetchAutomations();
    };

    const reorderAutomations = async (newOrderIds: string[]) => {
        const currentAutomations = [...automations.value];
        const newAutomations: Automation[] = [];
        const map = new Map(currentAutomations.map(a => [a.id, a]));
        newOrderIds.forEach(id => { if (map.has(id)) { newAutomations.push(map.get(id)!); map.delete(id); } });
        map.forEach(a => newAutomations.push(a));
        automations.value = newAutomations;

        await api('automations/order', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: newOrderIds }) });
    };

    const triggerAutomation = async (id: string) => {
        await api(`automations/${id}/trigger`, { method: 'POST' });
        commonStore.addFlashMessage(t('store.automationTriggered'), 'success');
    };

    const getAutomationsUsingDevice = (devId: string) => {
        return automations.value.filter(a => {
             if (a.triggers && a.triggers.some(t => t.device_id === devId || (t.sequence && t.sequence.some(s => s.device_id === devId)))) return true;
             if (a.actions && a.actions.some(act => act.type === 'ir_send' && act.device_id === devId)) return true;
             return false;
        });
    };

    const getAutomationsUsingButton = (devId: string, btnId: string) => {
        return automations.value.filter(a => {
            if (a.triggers && a.triggers.some(t => (t.device_id === devId && t.button_id === btnId) || (t.sequence && t.sequence.some(s => s.device_id === devId && s.button_id === btnId)))) return true;
            if (a.actions && a.actions.some(act => act.type === 'ir_send' && act.device_id === devId && act.button_id === btnId)) return true;
            return false;
        });
    };

    const handleAutomationProgress = (msg: AutomationProgressMessage) => {
        let autoState = runningAutomations.get(msg.id);
        if (!autoState) {
            autoState = { count: 0, nextColorIdx: 0, instances: new Map() };
            runningAutomations.set(msg.id, autoState);
        }
        
        autoState.count = msg.running_count !== undefined ? msg.running_count : autoState.count;

        if (msg.run_id) {
            if (msg.status === 'idle') {
                autoState.instances.delete(msg.run_id);
            } else {
                let instance = autoState.instances.get(msg.run_id);
                if (!instance) {
                    instance = { colorIdx: autoState.nextColorIdx % 6 };
                    autoState.nextColorIdx++;
                    autoState.instances.set(msg.run_id, instance);
                }
                instance.actionIndex = msg.current_action_index;
            }
        } else if (msg.status === 'idle' && !msg.run_id) {
            runningAutomations.delete(msg.id);
        }

        if (autoState.count <= 0 && autoState.instances.size === 0) {
            runningAutomations.delete(msg.id);
        }

        if (settingsStore.settings.enableUiIndications && msg.current_action_index !== undefined && msg.current_action_index !== -1) {
            const autoId = msg.id;
            let colorIdx = 0;
            if (msg.run_id && autoState.instances.has(msg.run_id)) {
                colorIdx = autoState.instances.get(msg.run_id)!.colorIdx;
            }

            if (!flashingActions.has(autoId)) {
                flashingActions.set(autoId, new Map());
            }
            const flashingMap = flashingActions.get(autoId)!;
            flashingMap.set(msg.current_action_index, colorIdx);
            setTimeout(() => {
                flashingMap.delete(msg.current_action_index as number);
                if (flashingMap.size === 0) {
                    flashingActions.delete(autoId);
                }
            }, 600);
        }
    };

    const handleTriggerProgress = (msg: TriggerProgressMessage) => {
        const key = `${msg.id}_${msg.trigger_index}`;
        if (msg.current === 0) {
            triggerProgress.delete(key);
        } else {
            triggerProgress.set(key, { current: msg.current, target: msg.target });
        }
    };

    const handleInactivityState = (msg: InactivityStateMessage) => {
        const key = `${msg.id}_${msg.trigger_index}`;
        if (msg.state === 'idle') {
            inactivityStates.delete(key);
        } else {
            const frontendNow = Date.now() / 1000;
            inactivityStates.set(key, {
                state: msg.state,
                timeout_s: msg.timeout_s,
                // Use frontend clock to avoid clock-skew between backend and browser
                armed_at: msg.state === 'armed' ? frontendNow : msg.armed_at,
                cooldown_s: msg.cooldown_s,
                cooldown_until: msg.state === 'cooldown' && msg.cooldown_s != null
                    ? frontendNow + msg.cooldown_s
                    : msg.cooldown_until,
            });
        }
    };

    const getInactivityState = (autoId: string, triggerIndex: number): InactivityTriggerState | undefined => {
        return inactivityStates.get(`${autoId}_${triggerIndex}`);
    };

    return { automations, editingAutomation, runningAutomations, flashingActions, triggerProgress, inactivityStates, fetchAutomations, deleteAutomation, duplicateAutomation, reorderAutomations, triggerAutomation, getAutomationsUsingDevice, getAutomationsUsingButton, handleAutomationProgress, handleTriggerProgress, handleInactivityState, getInactivityState };
});