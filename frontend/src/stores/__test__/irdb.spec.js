import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useIrdbStore } from '../irdb';
import { useCommonStore } from '../common';
import { api } from '../../services/api';

vi.mock('../../services/api', () => ({
    api: vi.fn(),
}));

vi.useFakeTimers();

describe('IRDB Store', () => {
    let store;
    let commonStore;

    beforeEach(() => {
        setActivePinia(createPinia());
        store = useIrdbStore();
        commonStore = useCommonStore();
        commonStore.addFlashMessage = vi.fn();
        vi.resetAllMocks();
    });

    it('fetches status', async () => {
        api.mockResolvedValue({ exists: true });
        await store.fetchIrdbStatus();
        expect(store.irdbStatus.exists).toBe(true);
    });

    it('updates irdb successfully', async () => {
        await store.updateIrdb();
        expect(api).toHaveBeenCalledWith('irdb/sync', expect.anything());
    });

    it('handles update error', async () => {
        api.mockRejectedValueOnce(new Error('Fail'));
        await store.updateIrdb();
        expect(commonStore.addFlashMessage).toHaveBeenCalledWith(expect.stringContaining('Failed'), 'error');
    });

    it('handles progress and completion', () => {
        api.mockResolvedValue({});
        store.handleIrdbProgress({ status: 'downloading', percent: 50 });
        expect(store.irdbProgress.percent).toBe(50);

        store.handleIrdbProgress({ status: 'done' });
        expect(commonStore.addFlashMessage).toHaveBeenCalledWith(expect.stringContaining('successfully'), 'success');
        
        vi.advanceTimersByTime(2000);
        expect(store.irdbProgress).toBeNull();
    });
});