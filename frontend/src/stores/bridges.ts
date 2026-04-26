import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api } from '../services/api';
import { useCommonStore } from './common';
import type { Bridge, BridgeSettings } from '../types';
import { t } from '../i18n';

export interface SerialPort {
  port: string;
  description: string;
  hwid: string;
}

export const useBridgeStore = defineStore('bridges', () => {
    const commonStore = useCommonStore();
    const bridges = ref<Bridge[]>([]);
    const pendingProtocols = ref(new Set<string>());
    const recentlyDeletedBridges = new Set<string>();
    const recentlyCreatedBridges = new Set<string>();
    
    // Serial Bridge related state
    const availableSerialPorts = ref<SerialPort[]>([]);
    const loadingSerialPorts = ref(false);
    const testingSerialConnection = ref(false);
    const creatingSerialBridge = ref(false);
    
    let initialBridgesLoaded = false;
    const bridgeStatusTimers = new Map<string, number>();

    const ignoredBridgeIds = ref<string[]>([]);

    const onlineBridges = computed(() => bridges.value.filter(b => b.status === 'online'));
    const hasOnlineBridges = computed(() => onlineBridges.value.length > 0);

    const fetchBridges = async () => {
        bridges.value = await api<Bridge[]>('bridges') || [];
    };

    const fetchIgnoredBridges = async () => {
        const result = await api<{ ignored: string[] }>('bridges/ignored');
        ignoredBridgeIds.value = result?.ignored ?? [];
    };

    const ignoreBridge = async (id: string, event: MouseEvent) => {
        const bridge = bridges.value.find(b => b.id === id);
        const displayName = bridge ? bridge.name : id;

        if (await commonStore.askConfirm(t('store.ignoreBridgeTitle'), t('store.ignoreBridgeConfirm', { name: displayName }), 'warning', t('confirm.ignore'), event)) {
            await api(`bridges/ignored/${encodeURIComponent(id)}`, { method: 'POST' });
            await fetchIgnoredBridges();
            commonStore.addFlashMessage(t('store.bridgeIgnored', { name: displayName }), 'info');
        }
    };

    const unignoreBridge = async (id: string) => {
        await api(`bridges/ignored/${encodeURIComponent(id)}`, { method: 'DELETE' });
        await fetchIgnoredBridges();
        commonStore.addFlashMessage(t('store.bridgeUnignored', { name: id }), 'success');
    };

    const deleteBridge = async (id: string, event: MouseEvent) => {
        const bridge = bridges.value.find(b => b.id === id);
        const displayName = bridge ? bridge.name : id;

        const isSerial = bridge?.connection_type === 'serial';
        const confirmMsg = isSerial 
            ? t('store.deleteSerialBridgeConfirm', { name: displayName })
            : t('store.deleteBridgeConfirm', { name: displayName });

        if (await commonStore.askConfirm(t('store.deleteBridgeTitle'), confirmMsg, 'danger', t('confirm.confirm'), event)) {
            recentlyDeletedBridges.add(id);
            try {
                const endpoint = isSerial ? `bridges/serial/${id}` : `bridges/${id}`;
                await api(endpoint, { method: 'DELETE' });
                commonStore.addFlashMessage(t('store.bridgeDeleted', { name: displayName }), 'success');
                setTimeout(() => recentlyDeletedBridges.delete(id), 5000);
            } catch {
                recentlyDeletedBridges.delete(id);
            }
        }
    };

    const updateBridgeProtocols = (bridgeId: string, protocols: string[]) => {
        return api(`bridges/${bridgeId}/protocols`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ protocols }) });
    };

    const updateBridgeSettings = (bridgeId: string, settings: BridgeSettings) => {
        return api(`bridges/${bridgeId}/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) });
    };

    const handleBridgesUpdated = (msg: { bridges: Bridge[] }) => {
        const oldBridges = [...bridges.value];
        const newBridges = msg.bridges;

        // Preserve settings if omitted from fast WS status updates
        newBridges.forEach(newBridge => {
            const oldBridge = oldBridges.find(b => b.id === newBridge.id);
            if (oldBridge && newBridge.settings === undefined && oldBridge.settings !== undefined) {
                newBridge.settings = JSON.parse(JSON.stringify(oldBridge.settings));
            }
        });

        if (initialBridgesLoaded) {
            newBridges.forEach(newBridge => {
                const oldBridge = oldBridges.find(b => b.id === newBridge.id);

                if (oldBridge) {
                    if (oldBridge.status !== newBridge.status) {
                        const bridgeId = newBridge.id;
                        if (bridgeStatusTimers.has(bridgeId)) {
                            clearTimeout(bridgeStatusTimers.get(bridgeId));
                        }
                        
                        if (newBridge.status !== 'connecting') {
                            const timer = setTimeout(() => {
                                if (!recentlyCreatedBridges.has(bridgeId)) {
                                    commonStore.addFlashMessage(t('store.bridgeStatusChanged', { name: newBridge.name, status: newBridge.status }), newBridge.status === 'online' ? 'success' : 'error');
                                }
                                bridgeStatusTimers.delete(bridgeId);
                            }, 500);
                            // eslint-disable-next-line @typescript-eslint/no-explicit-any
                            bridgeStatusTimers.set(bridgeId, timer as any);
                        }
                    }
                } else {
                if (!recentlyDeletedBridges.has(newBridge.id) && !recentlyCreatedBridges.has(newBridge.id) && newBridge.status !== 'connecting') {
                        commonStore.addFlashMessage(t('store.bridgeDiscovered', { name: newBridge.name }), 'info');
                    }
                }
            });

            oldBridges.forEach(oldBridge => {
                if (!newBridges.some(b => b.id === oldBridge.id)) {
                    if (!recentlyDeletedBridges.has(oldBridge.id) && oldBridge.status !== 'connecting') {
                        commonStore.addFlashMessage(t('store.bridgeRemoved', { name: oldBridge.name }), 'error');
                    }
                }
            });
        } else {
            initialBridgesLoaded = true;
        }

        bridges.value = msg.bridges;
    };

    // Serial Bridge functions
    const listSerialPorts = async () => {
        loadingSerialPorts.value = true;
        try {
            availableSerialPorts.value = await api<SerialPort[]>('bridges/serial/ports') || [];
        } finally {
            loadingSerialPorts.value = false;
        }
    };

    const testSerialConnection = async (port: string, baudrate: number = 115200) => {
        testingSerialConnection.value = true;
        try {
            const result = await api<{ status: string; message: string; config: Record<string, unknown> }>(
                'bridges/serial/test',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ port, baudrate })
                }
            );
            return result;
        } finally {
            testingSerialConnection.value = false;
        }
    };

    const createSerialBridge = async (port: string, baudrate: number = 115200, bridge_id?: string) => {
        creatingSerialBridge.value = true;
        try {
            const result = await api<{ status: string; bridge_id: string; message: string }>(
                'bridges/serial',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ port, baudrate, bridge_id })
                }
            );
            if (result && result.status === 'ok' && result.bridge_id) {
                recentlyCreatedBridges.add(result.bridge_id);
                setTimeout(() => recentlyCreatedBridges.delete(result.bridge_id), 5000);
            }
            return result;
        } finally {
            creatingSerialBridge.value = false;
        }
    };

    return {
        bridges,
        pendingProtocols,
        recentlyDeletedBridges,
        recentlyCreatedBridges,
        onlineBridges,
        hasOnlineBridges,
        fetchBridges,
        deleteBridge,
        updateBridgeProtocols,
        updateBridgeSettings,
        handleBridgesUpdated,
        // Ignored bridges
        ignoredBridgeIds,
        fetchIgnoredBridges,
        ignoreBridge,
        unignoreBridge,
        // Serial Bridge related
        availableSerialPorts,
        loadingSerialPorts,
        testingSerialConnection,
        creatingSerialBridge,
        listSerialPorts,
        testSerialConnection,
        createSerialBridge
    };
});