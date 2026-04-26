import { defineStore } from 'pinia';
import { ref, reactive, watch } from 'vue';
import { api } from '../services/api';
import { useCommonStore } from './common';
import { useDeviceStore } from './devices';
import { useBridgeStore } from './bridges';
import { useAutomationsStore } from './automations';
import type { IRCode } from '../types';
import { t } from '../i18n';

export interface MqttSettings {
    broker: string;
    port: number;
    user: string;
    password: string;
}

export interface TestState {
    running: boolean;
    results: TestMessage[];
    progress: number;
    total: number;
}

export interface TestMessage {
    type: 'test_start' | 'test_progress' | 'test_end' | 'test_error';
    total?: number;
    index?: number;
    message?: string;
    protocol?: string;
    sent?: IRCode;
    received?: IRCode;
    status?: 'passed' | 'failed' | 'error' | 'timeout';
    error?: string;
}

export const useSettingsStore = defineStore('settings', () => {
    const commonStore = useCommonStore();
    const deviceStore = useDeviceStore();
    const bridgeStore = useBridgeStore();
    const automationStore = useAutomationsStore();

    const settings = reactive({
        enableUiIndications: true,
        flashIgnoredCodes: localStorage.getItem('ir2mqtt_flashIgnoredCodes') === 'true',
        theme: localStorage.getItem('ir2mqtt_theme') || 'theme-ha',
        logLevel: localStorage.getItem('ir2mqtt_logLevel') || 'INFO',
        deviceViewMode: localStorage.getItem('ir2mqtt_deviceViewMode') || 'normal',
    });
    const appMode = ref('home_assistant');
    const appModeLocked = ref(false);
    const topicStyle = ref('name');
    const version = ref('unknown');
    const mqttSettings = ref<MqttSettings>({ broker: '', port: 1883, user: '', password: '' });
    const testState = ref<TestState>({ running: false, results: [], progress: 0, total: 0 });
    const isFactoryResetting = ref(false);

    watch(() => settings.theme, (newTheme) => localStorage.setItem('ir2mqtt_theme', newTheme));
    watch(() => settings.logLevel, (newLevel) => {
        localStorage.setItem('ir2mqtt_logLevel', newLevel);
        updateLogLevel(newLevel);
    });
    watch(() => settings.deviceViewMode, (newMode) => localStorage.setItem('ir2mqtt_deviceViewMode', newMode));
    watch(() => settings.flashIgnoredCodes, (newVal) => localStorage.setItem('ir2mqtt_flashIgnoredCodes', String(newVal)));

    const fetchAppMode = async () => {
        const data = await api('settings/app') as { mode: string, topic_style: string, locked: boolean, log_level: string, version: string };
        appMode.value = data.mode;
        topicStyle.value = data.topic_style || 'name';
        appModeLocked.value = !!data.locked;
        if (data.version) version.value = data.version;
        if (data.log_level) settings.logLevel = data.log_level;
    };

    const updateAppMode = (mode: string, style = 'name', migrate = false) => {
        appMode.value = mode;
        topicStyle.value = style;
        return api('settings/app', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode, topic_style: style, migrate }) });
    };

    const fetchMqttSettings = () => api<MqttSettings>('settings/mqtt').then(data => mqttSettings.value = data || { broker: '', port: 1883, user: '', password: '' });
    const saveMqttSettings = (s: MqttSettings) => api('settings/mqtt', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(s) });
    const testMqttSettings = (s: MqttSettings) => api<{ status: string; message: string }>('settings/mqtt/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(s) });
    const updateLogLevel = (level: string) => api('settings/log_level', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ log_level: level }) });

    const factoryReset = async (event: MouseEvent) => {
        if (await commonStore.askConfirm(t('confirm.factoryResetTitle'), t('confirm.factoryResetMsg'), 'danger', t('confirm.resetEverything'), event)) {
            isFactoryResetting.value = true;
            try {
                await api('reset', { method: 'POST' });
                commonStore.addFlashMessage(t('flash.factoryResetComplete'), 'success');
                await Promise.all([deviceStore.fetchDevices(), bridgeStore.fetchBridges(), automationStore.fetchAutomations()]);
            } finally {
                isFactoryResetting.value = false;
            }
        }
    };

    const startLoopbackTest = (tx: string, rx: string, txChannel?: string, rxChannel?: string, repeats: number = 3, timeout: number = 3.0, protocols?: string[]) => {
        const params = new URLSearchParams({ tx, rx, repeats: repeats.toString(), timeout: timeout.toString() });
        if (txChannel) params.set('tx_channel', txChannel);
        if (rxChannel) params.set('rx_channel', rxChannel);
        if (protocols && protocols.length > 0) {
            protocols.forEach(p => params.append('protocols', p));
        }
        return api(`test/loopback?${params}`, { method: 'POST' });
    };
    const stopLoopbackTest = () => api('test/loopback', { method: 'DELETE' });

    const handleTestMessage = (msg: TestMessage) => {
        switch (msg.type) {
            case 'test_start':
                testState.value.running = true;
                testState.value.results = [];
                testState.value.total = msg.total || 0;
                testState.value.progress = 0;
                break;
            case 'test_progress':
                testState.value.results.push(msg);
                testState.value.progress = (msg.index || 0) + 1;
                break;
            case 'test_end':
                testState.value.running = false;
                break;
            case 'test_error':
                testState.value.running = false;
                commonStore.addFlashMessage(t('flash.testError', { msg: msg.message ?? '' }), 'error');
                break;
        }
    };

    return { settings, appMode, appModeLocked, topicStyle, version, mqttSettings, testState, isFactoryResetting, fetchAppMode, updateAppMode, fetchMqttSettings, saveMqttSettings, testMqttSettings, updateLogLevel, factoryReset, startLoopbackTest, stopLoopbackTest, handleTestMessage };
});