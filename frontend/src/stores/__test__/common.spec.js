import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useCommonStore } from '../common';
import { useLearnStore } from '../learn';
import { useAutomationsStore } from '../automations';
import { useIrdbStore } from '../irdb';
import { useDeviceStore } from '../devices';
import { useBridgeStore } from '../bridges';
import { useSettingsStore } from '../settings';
import { api } from '../../services/api';

vi.mock('../../services/api', () => ({
    api: vi.fn(),
}));

vi.mock('../../i18n', () => ({
    t: vi.fn((key) => {
        if (key === 'store.wsConnected') return 'Event stream connected.';
        if (key === 'store.wsDisconnected') return 'disconnected';
        return key;
    }),
    useI18n: () => ({ t: vi.fn((k) => k) })
}));

vi.useFakeTimers();

describe('Common Store', () => {
    let store;

    beforeEach(() => {
        setActivePinia(createPinia());
        store = useCommonStore();
        
        api.mockImplementation((path) => {
            if (path === 'settings/app') {
                return Promise.resolve({ mode: 'standalone', topic_style: 'name', locked: false });
            }
            return Promise.resolve(null);
        });
    });

    it('adds and removes flash messages', () => {
        store.addFlashMessage('Test', 'info', 1000);
        expect(store.flashMessages).toHaveLength(1);
        expect(store.flashMessages[0].message).toBe('Test');

        vi.advanceTimersByTime(1000);
        expect(store.flashMessages).toHaveLength(0);
    });

    it('handles confirmation dialog', async () => {
        const promise = store.askConfirm('Title', 'Msg');
        expect(store.confirmation.show).toBe(true);
        
        // Simulate resolve
        store.confirmation.resolve(true);
        const result = await promise;
        expect(result).toBe(true);
    });

    it('clears logs', () => {
        store.logs = [{ message: 'test' }];
        store.clearLogs();
        expect(store.logs).toHaveLength(0);
        expect(store.flashMessages).toHaveLength(1); // "Logs cleared" message
    });
    
    it('toggles nav pin', () => {
        const initial = store.isNavPinned;
        store.toggleNavPin();
        expect(store.isNavPinned).toBe(!initial);
    });

    it('connects websocket and handles messages', () => {
        const mockWS = {
            onmessage: null,
            onopen: null,
            onclose: null,
            close: vi.fn()
        };
        global.WebSocket = vi.fn(function() { return mockWS; });

        store.connectWs();
        expect(global.WebSocket).toHaveBeenCalled();

        // Simulate open
        mockWS.onopen();
        expect(store.logs.some(l => l.message === 'Event stream connected.')).toBe(true);

        // Simulate log message (now wrapped as JSON with type 'log')
        const logData = "2023-01-01 12:00:00,000 - module - INFO - Test Log";
        mockWS.onmessage({ data: JSON.stringify({ type: 'log', message: logData }) });
        expect(store.logs.some(l => l.message === 'Test Log')).toBe(true);
        
        // Simulate JSON message (mqtt_status)
        mockWS.onmessage({ data: JSON.stringify({ type: 'mqtt_status', connected: true }) });
        expect(store.mqttConnected).toBe(true);
    });

    it('handles all websocket message types dispatching to stores', () => {
        const mockWS = {
            onmessage: null,
            onopen: null,
            onclose: null,
            close: vi.fn()
        };
        global.WebSocket = vi.fn(function() { return mockWS; });

        store.connectWs();
        
        // Setup spies on other stores
        const learnStore = useLearnStore();
        const automationsStore = useAutomationsStore();
        const irdbStore = useIrdbStore();
        const deviceStore = useDeviceStore();
        const bridgeStore = useBridgeStore();
        const settingsStore = useSettingsStore();

        const learnSpy = vi.spyOn(learnStore, 'handleLearningStatus');
        const smartLearnSpy = vi.spyOn(learnStore, 'handleSmartLearnProgress');
        const learnedCodeSpy = vi.spyOn(learnStore, 'handleLearnedCode');
        const autoProgressSpy = vi.spyOn(automationsStore, 'handleAutomationProgress');
        const triggerProgressSpy = vi.spyOn(automationsStore, 'handleTriggerProgress');
        const irdbSpy = vi.spyOn(irdbStore, 'handleIrdbProgress');
        const bridgesSpy = vi.spyOn(bridgeStore, 'handleBridgesUpdated');
        const testSpy = vi.spyOn(settingsStore, 'handleTestMessage');
        const knownCodeSpy = vi.spyOn(deviceStore, 'handleKnownCode');
        const fetchDevicesSpy = vi.spyOn(deviceStore, 'fetchDevices');
        const fetchAutosSpy = vi.spyOn(automationsStore, 'fetchAutomations');

        // Simulate messages
        mockWS.onmessage({ data: JSON.stringify({ type: 'learning_status', active: true }) });
        expect(learnSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'smart_learn_progress', current: 1 }) });
        expect(smartLearnSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'learned_code', code: {} }) });
        expect(learnedCodeSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'automation_progress', id: 'a1' }) });
        expect(autoProgressSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'trigger_progress', id: 'a1' }) });
        expect(triggerProgressSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'irdb_progress', percent: 10 }) });
        expect(irdbSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'bridges_updated', bridges: [] }) });
        expect(bridgesSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'test_progress', status: 'running' }) });
        expect(testSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'known_code_received', button_id: 'b1' }) });
        expect(knownCodeSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'devices_updated' }) });
        expect(fetchDevicesSpy).toHaveBeenCalled();

        mockWS.onmessage({ data: JSON.stringify({ type: 'automations_updated' }) });
        expect(fetchAutosSpy).toHaveBeenCalled();
    });
});
