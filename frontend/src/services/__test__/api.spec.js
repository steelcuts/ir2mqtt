import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useCommonStore } from '../../stores/common';
import { api } from '../api';

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('api.ts', () => {
    let commonStore;

    beforeEach(() => {
        setActivePinia(createPinia());
        commonStore = useCommonStore();
        commonStore.addFlashMessage = vi.fn();
    });

    afterEach(() => {
        vi.clearAllMocks();
    });

    it('returns JSON on successful request (200 OK)', async () => {
        const mockData = { message: 'Success' };
        mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () => Promise.resolve(mockData),
        });

        const result = await api('test');
        expect(result).toEqual(mockData);
        expect(mockFetch).toHaveBeenCalledWith('/api/test', undefined);
    });

    it('returns null on successful request with no content (204)', async () => {
        mockFetch.mockResolvedValue({
            ok: true,
            status: 204,
        });

        const result = await api('test');
        expect(result).toBeNull();
    });

    it('throws an error and shows flash message on API error', async () => {
        mockFetch.mockResolvedValue({
            ok: false,
            status: 500,
            statusText: 'Internal Server Error',
            json: () => Promise.resolve({}),
        });

        await expect(api('test')).rejects.toThrow('Internal Server Error');
        expect(commonStore.addFlashMessage).toHaveBeenCalledWith('API Error: Internal Server Error', 'error');
    });

    it('uses error detail from JSON response if available', async () => {
        mockFetch.mockResolvedValue({
            ok: false,
            status: 400,
            statusText: 'Bad Request',
            json: () => Promise.resolve({ detail: 'Invalid input' }),
        });

        await expect(api('test')).rejects.toThrow('Invalid input');
        expect(commonStore.addFlashMessage).toHaveBeenCalledWith('API Error: Invalid input', 'error');
    });
    
    it('throws a specific error for 409 Conflict without calling flash message', async () => {
        mockFetch.mockResolvedValue({
            ok: false,
            status: 409,
            statusText: 'Conflict',
            json: () => Promise.resolve({ detail: 'Resource exists' }),
        });

        try {
            await api('test');
        } catch (e) {
            expect(e.message).toBe('Resource exists');
            expect(e.status).toBe(409);
        }
        expect(commonStore.addFlashMessage).not.toHaveBeenCalled();
    });

    it('throws an error on network failure', async () => {
        const networkError = new Error('Network failure');
        mockFetch.mockRejectedValue(networkError);

        await expect(api('test')).rejects.toThrow(networkError);
        // In this case, the error is thrown before the flash message can be called.
        expect(commonStore.addFlashMessage).not.toHaveBeenCalled();
    });
});
