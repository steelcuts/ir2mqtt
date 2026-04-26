import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useBridgeStore } from '../bridges';
import { useCommonStore } from '../common';
import { api } from '../../services/api';

vi.mock('../../services/api', () => ({
    api: vi.fn(),
}));

vi.mock('../../i18n', () => ({
    t: vi.fn((key, params) => {
        if (key === 'store.bridgeDeleted') return `Bridge '${params?.name}' deleted.`;
        if (key === 'store.bridgeDiscovered') return `Bridge '${params?.name}' discovered.`;
        if (key === 'store.bridgeRemoved') return `Bridge '${params?.name}' was removed.`;
        if (key === 'store.bridgeStatusChanged') return `Bridge '${params?.name}' is now ${params?.status}.`;
        return key;
    }),
    useI18n: () => ({ t: vi.fn((k) => k) })
}));

vi.useFakeTimers();

describe('bridges.ts', () => {
    let bridgeStore;
    let commonStore;

    beforeEach(() => {

        setActivePinia(createPinia());
        bridgeStore = useBridgeStore();
        commonStore = useCommonStore();
        commonStore.addFlashMessage = vi.fn();
        commonStore.askConfirm = vi.fn();
        // Provide a default successful mock for the api
        api.mockClear();
        api.mockResolvedValue(null);
    });

    afterEach(() => {

        // Restore all mocks to their original state after each test
        vi.restoreAllMocks();
    });

    it('fetchBridges updates the bridges ref', async () => {
        const mockBridges = [{ id: '1', name: 'Test Bridge', status: 'online' }];
        api.mockResolvedValue(mockBridges);
        await bridgeStore.fetchBridges();
        expect(bridgeStore.bridges).toEqual(mockBridges);
        expect(api).toHaveBeenCalledWith('bridges');
    });

    describe('deleteBridge', () => {
        it('does nothing if confirmation is denied', async () => {
            commonStore.askConfirm.mockResolvedValue(false);
            await bridgeStore.deleteBridge('1', new MouseEvent('click'));
            expect(api).not.toHaveBeenCalled();
        });

        it('calls API and shows message on confirmed deletion', async () => {
            commonStore.askConfirm.mockResolvedValue(true);
            bridgeStore.bridges = [{ id: '1', name: 'Test Bridge', status: 'online' }];

            await bridgeStore.deleteBridge('1', new MouseEvent('click'));

            expect(api).toHaveBeenCalledWith('bridges/1', { method: 'DELETE' });
            expect(commonStore.addFlashMessage).toHaveBeenCalledWith("Bridge 'Test Bridge' deleted.", 'success');
            expect(bridgeStore.recentlyDeletedBridges.has('1')).toBe(true);

            // Fast-forward timers
            vi.advanceTimersByTime(5000);
            expect(bridgeStore.recentlyDeletedBridges.has('1')).toBe(false);
        }, 6000);

        it('handles API failure during deletion', async () => {
            commonStore.askConfirm.mockResolvedValue(true);
            api.mockRejectedValue(new Error('API Error'));
            bridgeStore.bridges = [{ id: '1', name: 'Test Bridge', status: 'online' }];

            await bridgeStore.deleteBridge('1', new MouseEvent('click'));

            expect(bridgeStore.recentlyDeletedBridges.has('1')).toBe(false);
            expect(commonStore.addFlashMessage).not.toHaveBeenCalled();
        });
    });
    
    it('updateBridgeProtocols calls the correct API endpoint', async () => {
        const protocols = ['nec', 'sony'];
        await bridgeStore.updateBridgeProtocols('bridge-1', protocols);
        expect(api).toHaveBeenCalledWith('bridges/bridge-1/protocols', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ protocols }),
        });
    });

    it('updateBridgeSettings calls the correct API endpoint', async () => {
        const settings = { echo_suppression: { timeout: 100 }};
        await bridgeStore.updateBridgeSettings('bridge-1', settings);
        expect(api).toHaveBeenCalledWith('bridges/bridge-1/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings),
        });
    });

    describe('handleBridgesUpdated', () => {
        it('handles initial bridge load', () => {
            const initialBridges = [{ id: '1', name: 'First', status: 'online' }];
            bridgeStore.handleBridgesUpdated({ bridges: initialBridges });
            expect(bridgeStore.bridges).toEqual(initialBridges);
            expect(commonStore.addFlashMessage).not.toHaveBeenCalled();
        });

        it('preserves settings if omitted in WS update', () => {
            const initialBridges = [{ id: '1', name: 'First', status: 'online', settings: { echo_enabled: true } }];
            bridgeStore.handleBridgesUpdated({ bridges: initialBridges });

            const updatedBridges = [{ id: '1', name: 'First', status: 'online' }]; // settings missing
            bridgeStore.handleBridgesUpdated({ bridges: updatedBridges });
            
            expect(bridgeStore.bridges[0].settings.echo_enabled).toBe(true);
        });

        it('shows notification for newly discovered bridge', () => {
            // Initial load
            bridgeStore.handleBridgesUpdated({ bridges: [{ id: '1', name: 'First', status: 'online' }] });

            // New bridge appears
            const newBridges = [
                { id: '1', name: 'First', status: 'online' },
                { id: '2', name: 'Second', status: 'online' },
            ];
            bridgeStore.handleBridgesUpdated({ bridges: newBridges });
            
            expect(commonStore.addFlashMessage).toHaveBeenCalledWith("Bridge 'Second' discovered.", 'info');
            expect(bridgeStore.bridges).toEqual(newBridges);
        });

        it('shows notification for removed bridge', () => {
            // Initial load
            const initialBridges = [{ id: '1', name: 'First', status: 'online' }];
            bridgeStore.handleBridgesUpdated({ bridges: initialBridges });

            // Bridge disappears
            bridgeStore.handleBridgesUpdated({ bridges: [] });
            
            expect(commonStore.addFlashMessage).toHaveBeenCalledWith("Bridge 'First' was removed.", 'error');
        });
        
        it('does not show notification for recently deleted bridge', () => {
            // Initial load
            const initialBridges = [{ id: '1', name: 'First', status: 'online' }];
            bridgeStore.handleBridgesUpdated({ bridges: initialBridges });
            bridgeStore.recentlyDeletedBridges.add('1');

            // Bridge disappears
            bridgeStore.handleBridgesUpdated({ bridges: [] });
            
            expect(commonStore.addFlashMessage).not.toHaveBeenCalled();
        });

        it('shows notification for bridge status change after a delay', () => {
            // Initial load
            const initialBridges = [{ id: '1', name: 'First', status: 'online' }];
            bridgeStore.handleBridgesUpdated({ bridges: initialBridges });
            
            // Status changes to offline
            const updatedBridges = [{ id: '1', name: 'First', status: 'offline' }];
            bridgeStore.handleBridgesUpdated({ bridges: updatedBridges });
            
            // Should not be called immediately
            expect(commonStore.addFlashMessage).not.toHaveBeenCalled();
            
            // Fast-forward time
            vi.advanceTimersByTime(5000);
            
            expect(commonStore.addFlashMessage).toHaveBeenCalledWith("Bridge 'First' is now offline.", 'error');
        }, 6000);

        it('clears existing timer if status flaps', () => {
            const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout');
            // Initial load
            const initialBridges = [{ id: '1', name: 'First', status: 'online' }];
            bridgeStore.handleBridgesUpdated({ bridges: initialBridges });

            // Status changes to offline
            const offlineBridges = [{ id: '1', name: 'First', status: 'offline' }];
            bridgeStore.handleBridgesUpdated({ bridges: offlineBridges });

            // Status changes back to online before timer fires
            const onlineBridges = [{ id: '1', name: 'First', status: 'online' }];
            bridgeStore.handleBridgesUpdated({ bridges: onlineBridges });

            expect(clearTimeoutSpy).toHaveBeenCalledTimes(1);
            
            // Fast-forward time
            vi.advanceTimersByTime(5000);

            // The first notification (offline) should have been cancelled
            // The second notification (online) should be sent
            expect(commonStore.addFlashMessage).toHaveBeenCalledTimes(1);
            expect(commonStore.addFlashMessage).toHaveBeenCalledWith("Bridge 'First' is now online.", 'success');
        }, 6000);
    });

    describe('Serial Bridge Functions', () => {
        describe('listSerialPorts', () => {
            it('fetches available serial ports', async () => {
                const mockPorts = [
                    { port: '/dev/ttyUSB0', description: 'USB to Serial', hwid: 'USB VID:PID=1234:5678' },
                    { port: '/dev/ttyUSB1', description: 'CH340', hwid: 'USB VID:PID=1a86:7523' },
                ];
                api.mockResolvedValue(mockPorts);
                
                await bridgeStore.listSerialPorts();
                
                expect(bridgeStore.availableSerialPorts).toEqual(mockPorts);
                expect(api).toHaveBeenCalledWith('bridges/serial/ports');
                expect(bridgeStore.loadingSerialPorts).toBe(false);
            });

            it('sets loadingSerialPorts flag during fetch', async () => {
                // Use a promise that resolves immediately
                let resolveApi;
                const apiPromise = new Promise(resolve => {
                    resolveApi = resolve;
                });
                api.mockReturnValue(apiPromise);
                
                const promise = bridgeStore.listSerialPorts();
                expect(bridgeStore.loadingSerialPorts).toBe(true);
                
                resolveApi([]);
                await promise;
                expect(bridgeStore.loadingSerialPorts).toBe(false);
            });
        });

        describe('testSerialConnection', () => {
            it('tests a serial connection successfully', async () => {
                const mockResult = {
                    status: 'success',
                    message: 'Serial connection works!',
                    config: { id: 'serial_test', name: 'Test Bridge' }
                };
                api.mockResolvedValue(mockResult);
                
                const result = await bridgeStore.testSerialConnection('/dev/ttyUSB0', 115200);
                
                expect(result).toEqual(mockResult);
                expect(api).toHaveBeenCalledWith('bridges/serial/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ port: '/dev/ttyUSB0', baudrate: 115200 })
                });
                expect(bridgeStore.testingSerialConnection).toBe(false);
            });

            it('handles test connection failure', async () => {
                api.mockRejectedValue(new Error('Connection timeout'));
                
                let error;
                try {
                    await bridgeStore.testSerialConnection('/dev/ttyUSB999', 115200);
                } catch (e) {
                    error = e;
                }
                
                expect(error).toBeDefined();
                expect(bridgeStore.testingSerialConnection).toBe(false);
            });

            it('uses default baudrate', async () => {
                api.mockResolvedValue({ status: 'success' });
                
                await bridgeStore.testSerialConnection('/dev/ttyUSB0');
                
                const callArgs = api.mock.calls[0];
                expect(JSON.parse(callArgs[1].body).baudrate).toBe(115200);
            });
        });

        describe('createSerialBridge', () => {
            it('creates a new serial bridge', async () => {
                const mockResult = {
                    status: 'ok',
                    bridge_id: 'serial_dev_ttyUSB0',
                    message: 'Serial bridge created and connecting...'
                };
                api.mockResolvedValue(mockResult);
                
                const result = await bridgeStore.createSerialBridge('/dev/ttyUSB0', 115200);
                
                expect(result).toEqual(mockResult);
                expect(api).toHaveBeenCalledWith('bridges/serial', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ port: '/dev/ttyUSB0', baudrate: 115200 })
                });
                expect(bridgeStore.creatingSerialBridge).toBe(false);
            });

            it('handles creation failure', async () => {
                api.mockRejectedValue(new Error('Port already in use'));
                
                let error;
                try {
                    await bridgeStore.createSerialBridge('/dev/ttyUSB0', 115200);
                } catch (e) {
                    error = e;
                }
                
                expect(error).toBeDefined();
                expect(bridgeStore.creatingSerialBridge).toBe(false);
            });
        });

        describe('deleteSerialBridge', () => {
            it('does nothing if confirmation is denied', async () => {
                commonStore.askConfirm.mockResolvedValue(false);
                await bridgeStore.deleteBridge('serial_dev_ttyUSB0', new MouseEvent('click'));
                expect(api).not.toHaveBeenCalled();
            });

            it('calls API and shows message on confirmed deletion', async () => {
                commonStore.askConfirm.mockResolvedValue(true);
                bridgeStore.bridges = [{ id: 'serial_dev_ttyUSB0', name: 'Test Serial Bridge', status: 'online', connection_type: 'serial' }];

                await bridgeStore.deleteBridge('serial_dev_ttyUSB0', new MouseEvent('click'));

                expect(api).toHaveBeenCalledWith('bridges/serial/serial_dev_ttyUSB0', { method: 'DELETE' });
                expect(commonStore.addFlashMessage).toHaveBeenCalledWith("Bridge 'Test Serial Bridge' deleted.", 'success');
                expect(bridgeStore.recentlyDeletedBridges.has('serial_dev_ttyUSB0')).toBe(true);

                // Fast-forward timers
                vi.advanceTimersByTime(5000);
                expect(bridgeStore.recentlyDeletedBridges.has('serial_dev_ttyUSB0')).toBe(false);
            }, 6000);

            it('handles API failure during deletion', async () => {
                commonStore.askConfirm.mockResolvedValue(true);
                api.mockRejectedValue(new Error('API Error'));
                bridgeStore.bridges = [{ id: 'serial_dev_ttyUSB0', name: 'Test Serial Bridge', status: 'online', connection_type: 'serial' }];

                await bridgeStore.deleteBridge('serial_dev_ttyUSB0', new MouseEvent('click'));

                expect(bridgeStore.recentlyDeletedBridges.has('serial_dev_ttyUSB0')).toBe(false);
                expect(commonStore.addFlashMessage).not.toHaveBeenCalled();
            });
        });
    });
});
