import { defineStore } from 'pinia';
import { ref, reactive, watch, nextTick } from 'vue';
import { useDeviceStore } from './devices';
import { useBridgeStore } from './bridges';
import { useLearnStore } from './learn';
import { useAutomationsStore } from './automations';
import { useIrdbStore } from './irdb';
import { useSettingsStore } from './settings';
import { t } from '../i18n';

export interface FlashMessage {
    id: number;
    message: string;
    type: 'success' | 'error' | 'warning' | 'info' | 'danger' | 'automation';
    duration: number;
}

export interface LogEntry {
    level: string;
    message: string;
    timestamp: Date;
    special?: string;
}

export interface ConfirmationState {
    show: boolean;
    title: string;
    message: string;
    confirmText: string;
    cancelText: string;
    type: 'danger' | 'warning' | 'info';
    resolve: ((value: boolean) => void) | null;
}

export const useCommonStore = defineStore('common', () => {
    const activeView = ref('Devices');
    const flashMessages = ref<FlashMessage[]>([]);
    const logs = ref<LogEntry[]>([]);
    const mqttConnected = ref(false);

    // UI State
    const initialPinState = localStorage.getItem('isNavPinned') === 'true';
    const isNavPinned = ref(initialPinState);

    watch(isNavPinned, (newValue) => {
        localStorage.setItem('isNavPinned', String(newValue));
    });

    const toggleNavPin = () => {
        isNavPinned.value = !isNavPinned.value;
    };
    
    const confirmation = reactive<ConfirmationState>({
        show: false,
        title: '',
        message: '',
        confirmText: 'Confirm',
        cancelText: 'Cancel',
        type: 'danger',
        resolve: null
    });

    const addFlashMessage = (message: string, type: FlashMessage['type'] = 'info', duration = 4000) => {
        const id = Date.now() + Math.random();
        flashMessages.value.push({ id, message, type, duration });
        setTimeout(() => {
            flashMessages.value = flashMessages.value.filter(m => m.id !== id);
        }, duration);
    };

    const askConfirm = (title: string, message: string, type: ConfirmationState['type'] = 'danger', confirmText = 'Confirm', event: MouseEvent | null = null) => {
        if (event && event.shiftKey) {
            return Promise.resolve(true);
        }
        return new Promise<boolean>((resolve) => {
            confirmation.title = title;
            confirmation.message = message;
            confirmation.type = type;
            confirmation.confirmText = confirmText;
            confirmation.cancelText = t('confirm.cancel');
            confirmation.resolve = resolve;
            confirmation.show = true;
        });
    };

    const clearLogs = () => {
        logs.value = [];
        addFlashMessage(t('store.logsCleared'), 'success');
    };

    // WebSocket Logic
    const parseLog = (logStr: string): LogEntry => {
        const match = logStr.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([\w.-]+) - (DEBUG|INFO|WARNING|ERROR) - (.*)/s);
        if (match) {
            return {
                level: match[3],
                message: match[4],
                timestamp: new Date(match[1].replace(',', '.')),
            };
        }
        return {
            level: 'INFO',
            message: logStr,
            timestamp: new Date(),
        };
    };

    const connectWs = () => {
        const deviceStore = useDeviceStore();
        const bridgeStore = useBridgeStore();
        const learnStore = useLearnStore();
        const automationsStore = useAutomationsStore();
        const irdbStore = useIrdbStore();
        const settingsStore = useSettingsStore();

        const basePath = window.location.pathname.replace(/\/$/, '');
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}${basePath}/ws/events`;
        const ws = new WebSocket(wsUrl);

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            switch (msg.type) {
                case 'mqtt_status':
                    mqttConnected.value = msg.connected;
                    if (!msg.connected) {
                        addFlashMessage(t('store.mqttNoConnection'), 'warning');
                    }
                    break;
                case 'bridges_updated':
                    bridgeStore.handleBridgesUpdated(msg);
                    break;
                case 'devices_updated':
                    deviceStore.fetchDevices();
                    break;
                case 'automations_updated':
                    automationsStore.fetchAutomations();
                    break;
                case 'irdb_updated':
                    irdbStore.fetchIrdbStatus();
                    break;
                case 'learning_status':
                    learnStore.handleLearningStatus(msg);
                    break;
                case 'smart_learn_progress':
                    learnStore.handleSmartLearnProgress(msg);
                    break;
                case 'learned_code':
                    learnStore.handleLearnedCode(msg);
                    break;
                case 'automation_progress':
                    automationsStore.handleAutomationProgress(msg);
                    break;
                case 'trigger_progress':
                    automationsStore.handleTriggerProgress(msg);
                    break;
                case 'inactivity_state':
                    automationsStore.handleInactivityState(msg);
                    break;
                case 'irdb_progress':
                    irdbStore.handleIrdbProgress(msg);
                    break;
                case 'test_start':
                case 'test_progress':
                case 'test_end':
                case 'test_error':
                    settingsStore.handleTestMessage(msg);
                    break;
                case 'known_code_received':
                    deviceStore.handleKnownCode(msg, settingsStore.settings.enableUiIndications, settingsStore.settings.flashIgnoredCodes);
                    break;
                case 'known_code_sent':
                    deviceStore.handleCodeSent(msg, settingsStore.settings.enableUiIndications);
                    break;
                case 'log': {
                    const logEntry = parseLog(msg.message);
                    logs.value.push(logEntry);
                    if (logs.value.length > 300) logs.value.shift();
                    nextTick(() => {
                        const el = document.getElementById('log-box');
                        if (el) el.scrollTop = el.scrollHeight;
                    });
                    break;
                }
            }
        };
        ws.onopen = () => {
            logs.value.push({ level: 'INFO', message: t('store.wsConnected'), timestamp: new Date(), special: 'connected' });
            bridgeStore.fetchBridges();
            settingsStore.fetchAppMode();
        };
        ws.onclose = () => {
            logs.value.push({ level: 'ERROR', message: t('store.wsDisconnected'), timestamp: new Date(), special: 'disconnected' });
            setTimeout(connectWs, 3000);
        };
    };

    return { 
        activeView, flashMessages, confirmation, logs, mqttConnected, isNavPinned,
        addFlashMessage, askConfirm, clearLogs, connectWs, toggleNavPin 
    };
});