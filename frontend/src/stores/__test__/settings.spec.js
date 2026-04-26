import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useSettingsStore } from '../settings';
import { useCommonStore } from '../common';
import { api } from '../../services/api';

vi.mock('../../services/api', () => ({
    api: vi.fn(),
}));

describe('Settings Store', () => {
    let store;
    let commonStore;

    beforeEach(() => {
        setActivePinia(createPinia());
        store = useSettingsStore();
        commonStore = useCommonStore();
        commonStore.askConfirm = vi.fn();
        commonStore.addFlashMessage = vi.fn();
        vi.clearAllMocks();
    });

    it('fetches app mode', async () => {
        api.mockResolvedValue({ mode: 'standalone', topic_style: 'id', locked: true, log_level: 'DEBUG' });
        await store.fetchAppMode();
        expect(store.appMode).toBe('standalone');
        expect(store.topicStyle).toBe('id');
        expect(store.appModeLocked).toBe(true);
        expect(store.settings.logLevel).toBe('DEBUG');
    });

    it('updates app mode', async () => {
        await store.updateAppMode('home_assistant', 'name');
        expect(api).toHaveBeenCalledWith('settings/app', expect.objectContaining({
            method: 'PUT',
            body: JSON.stringify({ mode: 'home_assistant', topic_style: 'name', migrate: false })
        }));
    });

    it('fetches mqtt settings', async () => {
        const mockSettings = { broker: '1.2.3.4', port: 1883, user: '', password: '' };
        api.mockResolvedValue(mockSettings);
        await store.fetchMqttSettings();
        expect(store.mqttSettings).toEqual(mockSettings);
    });

    it('saves mqtt settings', async () => {
        const s = { broker: '1.2.3.4', port: 1883, user: 'u', password: 'p' };
        await store.saveMqttSettings(s);
        expect(api).toHaveBeenCalledWith('settings/mqtt', expect.objectContaining({ method: 'PUT' }));
    });

    it('tests mqtt settings', async () => {
        const s = { broker: '1.2.3.4', port: 1883, user: 'u', password: 'p' };
        await store.testMqttSettings(s);
        expect(api).toHaveBeenCalledWith('settings/mqtt/test', expect.objectContaining({ method: 'POST' }));
    });

    it('updates log level', async () => {
        await store.updateLogLevel('DEBUG');
        expect(api).toHaveBeenCalledWith('settings/log_level', expect.objectContaining({ method: 'PUT' }));
    });

    it('performs factory reset if confirmed', async () => {
        commonStore.askConfirm.mockResolvedValue(true);
        await store.factoryReset(new MouseEvent('click'));
        expect(api).toHaveBeenCalledWith('reset', { method: 'POST' });
        expect(commonStore.addFlashMessage).toHaveBeenCalledWith(expect.stringContaining('reset complete'), 'success');
    });

    it('aborts factory reset if not confirmed', async () => {
        commonStore.askConfirm.mockResolvedValue(false);
        await store.factoryReset(new MouseEvent('click'));
        expect(api).not.toHaveBeenCalledWith('reset', expect.anything());
    });

    it('starts and stops loopback test', async () => {
        await store.startLoopbackTest('tx', 'rx');
        expect(api).toHaveBeenCalledWith('test/loopback?tx=tx&rx=rx&repeats=3&timeout=3', { method: 'POST' });

        await store.stopLoopbackTest();
        expect(api).toHaveBeenCalledWith('test/loopback', { method: 'DELETE' });
    });

    it('handles test messages', () => {
        store.handleTestMessage({ type: 'test_start', total: 10 });
        expect(store.testState.running).toBe(true);
        expect(store.testState.total).toBe(10);

        store.handleTestMessage({ type: 'test_progress', index: 0, status: 'passed' });
        expect(store.testState.results).toHaveLength(1);
        expect(store.testState.progress).toBe(1);
    });
});