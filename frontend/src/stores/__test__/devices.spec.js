import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useCommonStore } from '../common';
import { useLearnStore } from '../learn';
import { useDeviceStore } from '../devices';
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

describe('Device Store', () => {
    let deviceStore;
    let commonStore;

    beforeEach(() => {
        setActivePinia(createPinia());
        deviceStore = useDeviceStore();
        commonStore = useCommonStore();
        commonStore.askConfirm = vi.fn();
        commonStore.addFlashMessage = vi.fn();
        vi.clearAllMocks();
    });

    it('fetches devices correctly', async () => {
        const mockDevices = [{ id: 'd1', name: 'TV' }];
        api.mockResolvedValue(mockDevices);
        
        await deviceStore.fetchDevices();
        expect(deviceStore.devices).toEqual(mockDevices);
    });

    it('addDevice rejects if name is missing', async () => {
        deviceStore.newDevice = { name: '' };
        await expect(deviceStore.addDevice()).rejects.toEqual("Device name is missing.");
    });

    it('addDevice calls API and resets state on success', async () => {
        deviceStore.newDevice = { name: 'New TV', icon: 'tv' };
        api.mockResolvedValue({ id: 'd2', name: 'New TV' });
        
        await deviceStore.addDevice();
        
        expect(api).toHaveBeenCalledWith('devices', expect.objectContaining({ method: 'POST' }));
        expect(deviceStore.newDevice.name).toBe(''); // Reset check
    });

    it('deleteDevice asks for confirmation', async () => {
        commonStore.askConfirm.mockResolvedValue(false);
        await deviceStore.deleteDevice('d1', new MouseEvent('click'));
        expect(api).not.toHaveBeenCalledWith('devices/d1', expect.anything());

        commonStore.askConfirm.mockResolvedValue(true);
        await deviceStore.deleteDevice('d1', new MouseEvent('click'));
        expect(api).toHaveBeenCalledWith('devices/d1', { method: 'DELETE' });
    });

    it('handleKnownCode triggers flashing button', async () => {
        vi.useFakeTimers();
        const msg = { button_id: 'btn1' };
        
        // UI indications enabled (default)
        deviceStore.handleKnownCode(msg, true);
        
        // Wait for nextTick inside store
        await Promise.resolve(); 
        
        expect(deviceStore.flashingReceiveButtons.has('btn1')).toBe(true);
        
        vi.advanceTimersByTime(1000);
        expect(deviceStore.flashingReceiveButtons.has('btn1')).toBe(false);
        vi.useRealTimers();
    });

    it('duplicates device', async () => {
        await deviceStore.duplicateDevice('d1');
        expect(api).toHaveBeenCalledWith('devices/d1/duplicate', { method: 'POST' });
        expect(api).toHaveBeenCalledWith('devices'); // fetchDevices called
    });

    it('reorders devices', async () => {
        deviceStore.devices = [{ id: 'd1' }, { id: 'd2' }];
        await deviceStore.reorderDevices(['d2', 'd1']);
        expect(deviceStore.devices[0].id).toBe('d2');
        expect(api).toHaveBeenCalledWith('devices/order', expect.objectContaining({ method: 'PUT' }));
    });

    it('toggles device expansion', () => {
        deviceStore.toggleDevice('d1');
        expect(deviceStore.expandedDevices.has('d1')).toBe(true);
        expect(deviceStore.isDeviceExpanded('d1')).toBe(true);
        deviceStore.toggleDevice('d1');
        expect(deviceStore.expandedDevices.has('d1')).toBe(false);
    });

    it('triggers button', async () => {
        await deviceStore.triggerButton('d1', 'b1');
        expect(api).toHaveBeenCalledWith('devices/d1/buttons/b1/trigger', { method: 'POST' });
    });

    it('assigns code to button', async () => {
        const learnStore = useLearnStore();
        learnStore.learn.last_code = { protocol: 'nec' };
        
        await deviceStore.assignCode('d1', 'b1');
        
        expect(api).toHaveBeenCalledWith('devices/d1/buttons/b1/assign_code', expect.objectContaining({ method: 'POST' }));
        expect(learnStore.learn.received_codes).toHaveLength(0); // consumeLearnedCode called
    });

    it('opens button modal', () => {
        // New button
        deviceStore.openButtonModal('d1');
        expect(deviceStore.editingButton).toEqual(expect.objectContaining({ deviceId: 'd1' }));
        
        // Edit button
        const btn = { id: 'b1', name: 'Btn' };
        deviceStore.openButtonModal('d1', btn);
        expect(deviceStore.editingButton).toEqual(expect.objectContaining({ id: 'b1', deviceId: 'd1' }));
    });

    it('deletes button with confirmation', async () => {
        commonStore.askConfirm.mockResolvedValue(true);
        await deviceStore.deleteButton('d1', 'b1', new MouseEvent('click'));
        expect(api).toHaveBeenCalledWith('devices/d1/buttons/b1', { method: 'DELETE' });
    });

    it('duplicates button', async () => {
        await deviceStore.duplicateButton('d1', 'b1');
        expect(api).toHaveBeenCalledWith('devices/d1/buttons/b1/duplicate', { method: 'POST' });
    });

    it('reorders buttons', async () => {
        deviceStore.devices = [{ id: 'd1', buttons: [{ id: 'b1' }, { id: 'b2' }] }];
        await deviceStore.reorderButtons('d1', ['b2', 'b1']);
        expect(deviceStore.devices[0].buttons[0].id).toBe('b2');
        expect(api).toHaveBeenCalledWith('devices/d1/buttons/order', expect.objectContaining({ method: 'PUT' }));
    });

    it('generates correct topics', () => {
        const settingsStore = useSettingsStore();
        const dev = { id: 'd1', name: 'My TV' };
        const btn = { id: 'b1', name: 'Power On' };

        // HA Mode
        settingsStore.appMode = 'home_assistant';
        expect(deviceStore.getCommandTopic(dev, btn)).toBe('ir2mqtt/cmd/d1/b1');
        expect(deviceStore.getStateTopic(dev, btn)).toBe('ir2mqtt/input/d1/b1/state');
        expect(deviceStore.getEventTopic(dev, btn)).toBe('ir2mqtt/events/d1');

        // Standalone ID
        settingsStore.appMode = 'standalone';
        settingsStore.topicStyle = 'id';
        expect(deviceStore.getCommandTopic(dev, btn)).toBe('ir2mqtt/devices/d1/b1/in');
        
        // Standalone Name
        settingsStore.topicStyle = 'name';
        expect(deviceStore.getCommandTopic(dev, btn)).toBe('ir2mqtt/devices/my_tv/power_on/in');
    });
});
