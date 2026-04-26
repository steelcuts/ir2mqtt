import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useLearnStore } from '../learn';
import { useBridgeStore } from '../bridges';
import { useCommonStore } from '../common';
import { api } from '../../services/api';

vi.mock('../../services/api', () => ({
    api: vi.fn(),
}));

describe('Learn Store', () => {
    let store;
    let bridgeStore;
    let commonStore;

    beforeEach(() => {
        setActivePinia(createPinia());
        store = useLearnStore();
        bridgeStore = useBridgeStore();
        commonStore = useCommonStore();
        
        commonStore.addFlashMessage = vi.fn();
        vi.clearAllMocks();
    });

    it('starts learning if bridges online', () => {
        // Mock getter hasOnlineBridges via state
        bridgeStore.bridges = [{ status: 'online' }];
        
        store.startLearn();
        expect(api).toHaveBeenCalledWith(expect.stringContaining('learn?'), expect.objectContaining({ method: 'POST' }));
        expect(store.learn.received_codes).toEqual([]);
    });

    it('does not start learning if no bridges online', () => {
        bridgeStore.bridges = [];
        store.startLearn();
        expect(api).not.toHaveBeenCalled();
        expect(commonStore.addFlashMessage).toHaveBeenCalledWith(expect.stringContaining('No online bridges'), 'error');
    });

    it('cancels learning', () => {
        store.cancelLearn();
        expect(api).toHaveBeenCalledWith('learn/cancel', { method: 'POST' });
    });

    it('consumes learned code', () => {
        const code = { protocol: 'nec', payload: { address: '0x1', command: '0x2' } };
        store.learn.last_code = code;
        store.learn.received_codes = [code];
        
        store.consumeLearnedCode(code);
        
        expect(store.learn.received_codes).toHaveLength(0);
        expect(store.learn.last_code).toBeNull();
    });

    it('handles learning status update', () => {
        store.handleLearningStatus({ active: true, bridges: ['b1'], mode: 'smart' });
        expect(store.learn.active).toBe(true);
        expect(store.learn.activeOn).toEqual(['b1']);
        expect(store.learn.mode).toBe('smart');
        expect(store.learn.progress).toBe(0);
    });

    it('handles learned code', () => {
        vi.useFakeTimers();
        const code = { protocol: 'nec' };
        store.handleLearnedCode({ code, bridge: 'b1' });
        
        expect(store.learn.received_codes).toContainEqual(code);
        expect(store.learn.last_code).toEqual(code);
        
        vi.advanceTimersByTime(300);
        expect(api).toHaveBeenCalledWith('learn/cancel', { method: 'POST' });
        vi.useRealTimers();
    });
});