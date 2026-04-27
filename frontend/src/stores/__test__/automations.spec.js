import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAutomationsStore } from '../automations';
import { useCommonStore } from '../common';
import { useSettingsStore } from '../settings';
import { api } from '../../services/api';

vi.mock('../../services/api', () => ({
    api: vi.fn(),
}));

describe('Automations Store', () => {
    let store;
    let commonStore;
    let settingsStore;

    beforeEach(() => {
        setActivePinia(createPinia());
        store = useAutomationsStore();
        commonStore = useCommonStore();
        settingsStore = useSettingsStore();
        
        commonStore.askConfirm = vi.fn();
        commonStore.addFlashMessage = vi.fn();
        vi.clearAllMocks();
    });

    it('fetches automations', async () => {
        const mockAutos = [{ id: 'a1', name: 'Auto 1' }];
        api.mockResolvedValue(mockAutos);
        await store.fetchAutomations();
        expect(store.automations).toEqual(mockAutos);
    });

    it('deletes automation after confirmation', async () => {
        commonStore.askConfirm.mockResolvedValue(true);
        await store.deleteAutomation('a1', new MouseEvent('click'));
        expect(api).toHaveBeenCalledWith('automations/a1', { method: 'DELETE' });
        expect(commonStore.addFlashMessage).toHaveBeenCalled();
    });

    it('does not delete automation if not confirmed', async () => {
        commonStore.askConfirm.mockResolvedValue(false);
        await store.deleteAutomation('a1', new MouseEvent('click'));
        expect(api).not.toHaveBeenCalledWith('automations/a1', expect.anything());
    });

    it('duplicates automation', async () => {
        await store.duplicateAutomation('a1');
        expect(api).toHaveBeenCalledWith('automations/a1/duplicate', { method: 'POST' });
    });

    it('reorders automations', async () => {
        store.automations = [{ id: 'a1' }, { id: 'a2' }];
        await store.reorderAutomations(['a2', 'a1']);
        expect(store.automations[0].id).toBe('a2');
        expect(api).toHaveBeenCalledWith('automations/order', expect.objectContaining({ method: 'PUT' }));
    });

    it('triggers automation', async () => {
        await store.triggerAutomation('a1');
        expect(api).toHaveBeenCalledWith('automations/a1/trigger', { method: 'POST' });
    });

    it('gets automations using device', () => {
        store.automations = [
            { id: 'a1', triggers: [{ device_id: 'd1' }] },
            { id: 'a2', triggers: [{ device_id: 'd2' }] },
            { id: 'a3', actions: [{ type: 'ir_send', device_id: 'd1' }] }
        ];
        const result = store.getAutomationsUsingDevice('d1');
        expect(result).toHaveLength(2);
        expect(result.map(a => a.id)).toContain('a1');
        expect(result.map(a => a.id)).toContain('a3');
    });

    it('gets automations using button', () => {
        store.automations = [
            { id: 'a1', triggers: [{ device_id: 'd1', button_id: 'b1' }] },
            { id: 'a2', triggers: [{ device_id: 'd1', button_id: 'b2' }] }
        ];
        const result = store.getAutomationsUsingButton('d1', 'b1');
        expect(result).toHaveLength(1);
        expect(result[0].id).toBe('a1');
    });

    it('handles automation progress (running)', () => {
        settingsStore.settings.enableUiIndications = true;
        vi.useFakeTimers();
        
        const msg = {
            id: 'a1',
            run_id: 'r1',
            status: 'running',
            running_count: 1,
            current_action_index: 0
        };
        
        store.handleAutomationProgress(msg);
        
        expect(store.runningAutomations.has('a1')).toBe(true);
        expect(store.flashingActions.has('a1')).toBe(true);
        expect(store.flashingActions.get('a1').get(0)).toBeDefined(); // Color index

        vi.advanceTimersByTime(600);
        expect(store.flashingActions.has('a1')).toBe(false);
        
        vi.useRealTimers();
    });

    it('handles automation progress (idle)', () => {
        store.runningAutomations.set('a1', { count: 1, instances: new Map([['r1', {}]]) });
        
        store.handleAutomationProgress({
            id: 'a1',
            run_id: 'r1',
            status: 'idle',
            running_count: 0
        });
        
        expect(store.runningAutomations.has('a1')).toBe(false);
    });

    it('handles trigger progress', () => {
        store.handleTriggerProgress({ id: 'a1', trigger_index: 0, current: 1, target: 2 });
        expect(store.triggerProgress.get('a1_0')).toEqual({ current: 1, target: 2 });

        store.handleTriggerProgress({ id: 'a1', trigger_index: 0, current: 0, target: 2 });
        expect(store.triggerProgress.has('a1_0')).toBe(false);
    });

    // --- device_inactivity ---

    it('handleInactivityState: stores armed state using frontend clock', () => {
        const fakeNow = 5000000;
        vi.spyOn(Date, 'now').mockReturnValueOnce(fakeNow * 1000);
        store.handleInactivityState({
            id: 'a1', trigger_index: 0,
            state: 'armed', timeout_s: 30, armed_at: 1000
        });
        const s = store.getInactivityState('a1', 0);
        expect(s).toBeDefined();
        expect(s.state).toBe('armed');
        expect(s.timeout_s).toBe(30);
        expect(s.armed_at).toBe(fakeNow);
    });

    it('handleInactivityState: stores cooldown state using frontend clock', () => {
        const fakeNow = 5000000;
        vi.spyOn(Date, 'now').mockReturnValueOnce(fakeNow * 1000);
        store.handleInactivityState({
            id: 'a1', trigger_index: 1,
            state: 'cooldown', cooldown_s: 10, cooldown_until: 9999
        });
        const s = store.getInactivityState('a1', 1);
        expect(s.state).toBe('cooldown');
        expect(s.cooldown_s).toBe(10);
        expect(s.cooldown_until).toBe(fakeNow + 10);
    });

    it('handleInactivityState: idle removes entry from map', () => {
        store.handleInactivityState({ id: 'a1', trigger_index: 0, state: 'armed', timeout_s: 30, armed_at: 1000 });
        expect(store.getInactivityState('a1', 0)).toBeDefined();

        store.handleInactivityState({ id: 'a1', trigger_index: 0, state: 'idle' });
        expect(store.getInactivityState('a1', 0)).toBeUndefined();
    });

    it('handleInactivityState: multiple triggers on same automation are independent', () => {
        store.handleInactivityState({ id: 'a1', trigger_index: 0, state: 'armed', timeout_s: 30, armed_at: 1 });
        store.handleInactivityState({ id: 'a1', trigger_index: 1, state: 'cooldown', cooldown_s: 5, cooldown_until: 2 });

        expect(store.getInactivityState('a1', 0).state).toBe('armed');
        expect(store.getInactivityState('a1', 1).state).toBe('cooldown');

        store.handleInactivityState({ id: 'a1', trigger_index: 0, state: 'idle' });
        expect(store.getInactivityState('a1', 0)).toBeUndefined();
        expect(store.getInactivityState('a1', 1)).toBeDefined();
    });

    it('getInactivityState: returns undefined for unknown key', () => {
        expect(store.getInactivityState('nonexistent', 0)).toBeUndefined();
    });

    it('fetchAutomations: prunes stale inactivity states when automation is removed', async () => {
        // Arm a state for a1 and a2
        store.handleInactivityState({ id: 'a1', trigger_index: 0, state: 'armed', timeout_s: 30, armed_at: 1 });
        store.handleInactivityState({ id: 'a2', trigger_index: 0, state: 'armed', timeout_s: 30, armed_at: 1 });
        expect(store.getInactivityState('a1', 0)).toBeDefined();
        expect(store.getInactivityState('a2', 0)).toBeDefined();

        // API now only returns a1 (a2 was deleted)
        api.mockResolvedValue([{ id: 'a1', name: 'Auto 1' }]);
        await store.fetchAutomations();

        expect(store.getInactivityState('a1', 0)).toBeDefined();  // still exists
        expect(store.getInactivityState('a2', 0)).toBeUndefined(); // pruned
    });

    it('fetchAutomations: handles non-array API response without crashing', async () => {
        store.handleInactivityState({ id: 'a1', trigger_index: 0, state: 'armed', timeout_s: 30, armed_at: 1 });

        api.mockResolvedValue(null);
        await store.fetchAutomations();
        expect(store.automations).toEqual([]);
    });
});