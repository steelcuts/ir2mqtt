import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { api } from '../services/api';
import { useCommonStore } from './common';
import { useAutomationsStore } from './automations';
import { useLearnStore } from './learn';
import { sanitizeTopicParam } from '../utils';
import { useSettingsStore } from './settings';
import type { IRDevice, IRButton } from '../types';
import { t } from '../i18n';

export type Button = IRButton & { deviceId?: string };
export type Device = IRDevice;

interface KnownCodeSentMessage {
    button_id: string;
}

interface KnownCodeMessage {
    button_id: string;
    ignored?: boolean;
}

export const useDeviceStore = defineStore('devices', () => {
    const commonStore = useCommonStore();
    const automationsStore = useAutomationsStore();
    const learnStore = useLearnStore();
    const settingsStore = useSettingsStore();

    const devices = ref<Device[]>([]);
    const expandedDevices = ref(new Set<string>(JSON.parse(localStorage.getItem('ir2mqtt_expanded_devices') || '[]')));
    const topicsVisibleForDevice = ref(new Set<string>());
    const flashingSendButtons = ref(new Set<string>());
    const flashingReceiveButtons = ref(new Set<string>());
    const flashingIgnoredButtons = ref(new Set<string>());
    const flashingSendTimeouts = new Map<string, ReturnType<typeof setTimeout>>();
    const flashingReceiveTimeouts = new Map<string, ReturnType<typeof setTimeout>>();
    const flashingIgnoredTimeouts = new Map<string, ReturnType<typeof setTimeout>>();
    const newDevice = ref<Partial<Device>>({ name: '', icon: 'remote-tv', target_bridges: [], allowed_bridges: [] });
    const editingDevice = ref<Device | null>(null);
    const editingButton = ref<Button | null>(null);

    watch(expandedDevices, (val) => {
        localStorage.setItem('ir2mqtt_expanded_devices', JSON.stringify(Array.from(val)));
    }, { deep: true });

    const fetchDevices = async () => {
        devices.value = await api<Device[]>('devices') || [];
    };

    const addDevice = async () => {
        if (!newDevice.value.name) return Promise.reject("Device name is missing.");
        try {
            const device = await api<Device>('devices', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(newDevice.value) });
            newDevice.value = { name: '', icon: 'remote-tv', target_bridges: [], allowed_bridges: [] };
            await fetchDevices();
            return device;
        } catch {
            return null;
        }
    };

    const deleteDevice = async (id: string, event: MouseEvent) => {
        const usedIn = automationsStore.getAutomationsUsingDevice(id);
        if (usedIn.length > 0) {
            const names = usedIn.map(a => `- ${a.name}`).join('\n');
            if (!await commonStore.askConfirm(t('store.deviceInUseTitle'), t('store.deviceInUse', { names }), 'danger', t('confirm.deleteAnyway'), event)) {
                return;
            }
        } else {
            if (!await commonStore.askConfirm(t('store.deleteDeviceTitle'), t('store.deleteDeviceConfirm'), 'danger', t('confirm.confirm'), event)) {
                return;
            }
        }
        await api(`devices/${id}`, { method: 'DELETE' });
        await fetchDevices();
        commonStore.addFlashMessage(t('store.deviceDeleted'), 'success');
    };

    const duplicateDevice = (id: string) => {
        return api(`devices/${id}/duplicate`, { method: 'POST' }).then(fetchDevices);
    };

    const reorderDevices = async (newOrderIds: string[]) => {
        // Optimistic update
        const currentDevices = [...devices.value];
        const newDevices: Device[] = [];
        const map = new Map(currentDevices.map(d => [d.id, d]));
        newOrderIds.forEach(id => { if (map.has(id)) { newDevices.push(map.get(id)!); map.delete(id); } });
        map.forEach(d => newDevices.push(d));
        devices.value = newDevices;

        await api('devices/order', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: newOrderIds }) });
    };

    const toggleDevice = (id: string) => {
        if (expandedDevices.value.has(id)) expandedDevices.value.delete(id);
        else expandedDevices.value.add(id);
    };

    const isDeviceExpanded = (id: string) => expandedDevices.value.has(id);

    // Button Actions
    const triggerButton = async (devId: string, btnId: string) => {
        if (settingsStore.settings.enableUiIndications) {
            if (flashingSendTimeouts.has(btnId)) {
                clearTimeout(flashingSendTimeouts.get(btnId));
            }
            flashingSendButtons.value.add(btnId);
            const timeoutId = setTimeout(() => {
                flashingSendButtons.value.delete(btnId);
                flashingSendTimeouts.delete(btnId);
            }, 300); // 300ms für einen klaren visuellen Indikator
            flashingSendTimeouts.set(btnId, timeoutId);
        }
        return api(`devices/${devId}/buttons/${btnId}/trigger`, { method: 'POST' });
    };
    
    const assignCode = async (devId: string, btnId: string) => {
        const codeToAssign = learnStore.learn.last_code;
        if (!codeToAssign) return;
        await api(`devices/${devId}/buttons/${btnId}/assign_code`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ code: codeToAssign }) });
        await fetchDevices();
        learnStore.consumeLearnedCode(codeToAssign);
    };

    const openButtonModal = (devId: string, button: Button | null = null) => {
        if (button) {
            editingButton.value = { ...button, deviceId: devId };
        } else {
            const newBtn: Partial<Button> = { deviceId: devId };
            if (learnStore.learn.last_code) {
                newBtn.code = JSON.parse(JSON.stringify(learnStore.learn.last_code));
            }
            editingButton.value = newBtn as Button;
        }
    };

    const deleteButton = async (devId: string, btnId: string, event: MouseEvent) => {
        const usedIn = automationsStore.getAutomationsUsingButton(devId, btnId);
        if (usedIn.length > 0) {
            const names = usedIn.map(a => `- ${a.name}`).join('\n');
            if (!await commonStore.askConfirm(t('store.buttonInUseTitle'), t('store.buttonInUse', { names }), 'danger', t('confirm.deleteAnyway'), event)) {
                return;
            }
        } else {
            if (!await commonStore.askConfirm(t('store.deleteButtonTitle'), t('store.deleteButtonConfirm'), 'danger', t('confirm.confirm'), event)) {
                return;
            }
        }
        await api(`devices/${devId}/buttons/${btnId}`, { method: 'DELETE' });
        await fetchDevices();
        commonStore.addFlashMessage(t('store.buttonDeleted'), 'success');
    };

    const duplicateButton = async (devId: string, btnId: string) => {
        await api(`devices/${devId}/buttons/${btnId}/duplicate`, { method: 'POST' });
        await fetchDevices();
    };

    const reorderButtons = async (deviceId: string, newOrderIds: string[]) => {
        const device = devices.value.find(d => d.id === deviceId);
        if (!device) return;

        const currentButtons = [...device.buttons];
        const newButtons: (Button)[] = [];
        const map = new Map(currentButtons.map(b => [b.id, b]));
        
        newOrderIds.forEach(id => {
            if (map.has(id)) {
                newButtons.push(map.get(id)!);
                map.delete(id);
            }
        });
        
        map.forEach(b => newButtons.push(b));
        
        device.buttons = newButtons;

        await api(`devices/${deviceId}/buttons/order`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: newOrderIds })
        });
    };

    const getDevice = (id: string) => devices.value.find(d => d.id === id);
    const getButton = (devId: string, btnId: string) => {
        const dev = getDevice(devId);
        return dev ? dev.buttons.find(b => b.id === btnId) : null;
    };
    const getButtonsForDevice = (devId: string) => getDevice(devId)?.buttons || [];
    
    const getDeviceName = (id: string) => getDevice(id)?.name || 'Unknown Device';
    const getButtonName = (devId: string, btnId: string) => getButton(devId, btnId)?.name || 'Unknown Button';
    const getButtonIcon = (devId: string, btnId: string) => getButton(devId, btnId)?.icon || 'help-box';

    // Topic Helpers
    const getCommandTopic = (dev: Device, btn: Button) => {
        if (settingsStore.appMode === 'standalone') {
            if (settingsStore.topicStyle === 'id') return `ir2mqtt/devices/${dev.id}/${btn.id}/in`;
            return `ir2mqtt/devices/${sanitizeTopicParam(dev.name)}/${sanitizeTopicParam(btn.name)}/in`;
        }
        return `ir2mqtt/cmd/${dev.id}/${btn.id}`;
    };

    const getStateTopic = (dev: Device, btn: Button) => {
        if (settingsStore.appMode === 'standalone') {
            if (settingsStore.topicStyle === 'id') return `ir2mqtt/devices/${dev.id}/${btn.id}/out`;
            return `ir2mqtt/devices/${sanitizeTopicParam(dev.name)}/${sanitizeTopicParam(btn.name)}/out`;
        }
        return `ir2mqtt/input/${dev.id}/${btn.id}/state`;
    };

    const getEventTopic = (dev: Device, btn: Button) => {
        if (settingsStore.appMode === 'standalone') {
            if (settingsStore.topicStyle === 'id') return `ir2mqtt/devices/${dev.id}/${btn.id}/event`;
            return `ir2mqtt/devices/${sanitizeTopicParam(dev.name)}/${sanitizeTopicParam(btn.name)}/event`;
        }
        return `ir2mqtt/events/${dev.id}`;
    };

    const handleKnownCode = (msg: KnownCodeMessage, enableUiIndications: boolean, flashIgnored: boolean) => {
        if (msg.ignored && !flashIgnored) return;
        
        if (enableUiIndications) {
            const buttonId = msg.button_id;
            
            const targetSet = msg.ignored ? flashingIgnoredButtons : flashingReceiveButtons;
            const targetTimeouts = msg.ignored ? flashingIgnoredTimeouts : flashingReceiveTimeouts;
            
            if (targetTimeouts.has(buttonId)) {
                clearTimeout(targetTimeouts.get(buttonId));
            }

            targetSet.value.add(buttonId);
            
            const timeoutId = setTimeout(() => {
                targetSet.value.delete(buttonId);
                targetTimeouts.delete(buttonId);
            }, 300); 

            targetTimeouts.set(buttonId, timeoutId);
        }
    };

    const handleCodeSent = (msg: KnownCodeSentMessage, enableUiIndications: boolean) => {
        if (enableUiIndications) {
            const buttonId = msg.button_id;
            
            if (flashingSendTimeouts.has(buttonId)) {
                clearTimeout(flashingSendTimeouts.get(buttonId));
            }

            flashingSendButtons.value.add(buttonId);
            
            const timeoutId = setTimeout(() => {
                flashingSendButtons.value.delete(buttonId);
                flashingSendTimeouts.delete(buttonId);
            }, 300); 

            flashingSendTimeouts.set(buttonId, timeoutId);
        }
    };

    return {
        devices, expandedDevices, topicsVisibleForDevice, flashingSendButtons, flashingReceiveButtons, flashingIgnoredButtons, newDevice, editingDevice, editingButton,
        fetchDevices, addDevice, deleteDevice, reorderDevices, toggleDevice, isDeviceExpanded,
        triggerButton, assignCode, openButtonModal, deleteButton, duplicateButton, reorderButtons, duplicateDevice,
        getDevice, getButton, getButtonsForDevice, getCommandTopic, getStateTopic, getEventTopic, handleKnownCode, handleCodeSent,
        getDeviceName, getButtonName, getButtonIcon
    };
});

export { isButtonValid, isSameCode } from '../utils';