import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import App from '../App.vue';
import { useCommonStore } from '../stores/common';
import { useDeviceStore } from '../stores/devices';
import { useAutomationsStore } from '../stores/automations';
import { useSettingsStore } from '../stores/settings';
import { useBridgeStore } from '../stores/bridges';

vi.mock('../tour', () => ({
    startAutomationTour: vi.fn(),
    startDevicesTour: vi.fn(),
    startBridgesTour: vi.fn(),
    startSettingsTour: vi.fn(),
}));

describe('App.vue', () => {
    let pinia;

    afterEach(async () => {
        await flushPromises();
    });

    beforeEach(() => {
        pinia = createPinia();
        setActivePinia(pinia);

        // Mock store actions
        const deviceStore = useDeviceStore();
        deviceStore.fetchDevices = vi.fn();

        const automationsStore = useAutomationsStore();
        automationsStore.fetchAutomations = vi.fn();
        
        const commonStore = useCommonStore();
        commonStore.connectWs = vi.fn();

        const bridgeStore = useBridgeStore();
        bridgeStore.fetchBridges = vi.fn();

        const settingsStore = useSettingsStore();
        settingsStore.fetchAppMode = vi.fn();
    });

    it('renders the default view and side navigation', async () => {
        const commonStore = useCommonStore();
        commonStore.activeView = 'Devices'; // Set initial view

        const wrapper = mount(App, {
            global: {
                plugins: [pinia],
                stubs: {
                    SideNav: true,
                    FlashMessages: true,
                    ConfirmModal: true,
                    IrDbPicker: true,
                    DeviceModal: true,
                    ButtonModal: true,
                    AutomationModal: true,
                    Devices: true,
                    Automations: true,
                    Bridges: true,
                    Settings: true,
                    Status: true,
                    Manual: true,
                },
            },
        });

        // Wait for async components to load
        await wrapper.vm.$nextTick();
        await wrapper.vm.$nextTick();

        expect(wrapper.findComponent({ name: 'SideNav' }).exists()).toBe(true);
        expect(wrapper.find('h1').text()).toContain('Devices');
        wrapper.unmount();
    });

    it('updates theme class on body', async () => {
        const settingsStore = useSettingsStore();
        settingsStore.settings.theme = 'theme-dark';

        const wrapper = mount(App, { global: { plugins: [pinia], stubs: { SideNav: true, FlashMessages: true, ConfirmModal: true, IrDbPicker: true, DeviceModal: true, ButtonModal: true, AutomationModal: true, Devices: true } } });

        expect(document.body.classList.contains('theme-dark')).toBe(true);

        settingsStore.settings.theme = 'theme-light';
        await flushPromises(); // Wait for watcher and async components

        expect(document.body.classList.contains('theme-light')).toBe(true);
        expect(document.body.classList.contains('theme-dark')).toBe(false);
        wrapper.unmount();
    });

    it('updates active view based on hash', async () => {
        const commonStore = useCommonStore();
        window.location.hash = '#Settings';
        
        const wrapper = mount(App, { global: { plugins: [pinia], stubs: { SideNav: true, FlashMessages: true, ConfirmModal: true, IrDbPicker: true, DeviceModal: true, ButtonModal: true, AutomationModal: true, Settings: true } } });
        
        await flushPromises();
        expect(commonStore.activeView).toBe('Settings');
        wrapper.unmount();
    });
});
