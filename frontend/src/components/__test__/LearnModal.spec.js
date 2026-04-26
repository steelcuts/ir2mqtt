import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import LearnModal from '../LearnModal.vue';
import { useLearnStore } from '../../stores/learn';
import { useBridgeStore } from '../../stores/bridges';
import Switch from '../Switch.vue';

describe('LearnModal.vue', () => {
    let pinia;
    let learnStore;
    let bridgeStore;

    beforeEach(() => {
        pinia = createPinia();
        setActivePinia(pinia);
        learnStore = useLearnStore();
        bridgeStore = useBridgeStore();
    });

    it('renders correctly when show is true', () => {
        bridgeStore.bridges = [{ id: 'bridge1', name: 'Test Bridge', status: 'online' }];
        const wrapper = mount(LearnModal, {
            props: { show: true },
            global: {
                plugins: [pinia],
                components: { Switch },
            },
        });
        expect(wrapper.find('h2').text()).toBe('Learn IR Code');
        // When bridges are online, BridgeSelector is shown (not a plain <select>)
        expect(wrapper.text()).toContain('Test Bridge');
    });

    it('disables start button if no bridges are online', () => {
        bridgeStore.bridges = [];
        const wrapper = mount(LearnModal, {
            props: { show: true },
            global: {
                plugins: [pinia],
                components: { Switch },
            },
        });
        expect(wrapper.find('.btn-primary').attributes('disabled')).toBeDefined();
        expect(wrapper.find('select').attributes('disabled')).toBeDefined();
        expect(wrapper.find('option').element.textContent.trim()).toBe('No bridges online');
    });

    it('disables start button if learning is active', () => {
        learnStore.learn.active = true;
        bridgeStore.bridges = [{ id: 'bridge1', name: 'Test Bridge', status: 'online' }];
        const wrapper = mount(LearnModal, {
            props: { show: true },
            global: {
                plugins: [pinia],
                components: { Switch },
            },
        });
        expect(wrapper.find('.btn-primary').attributes('disabled')).toBeDefined();
        expect(wrapper.find('.btn-primary span').text()).toBe('Listening...');
    });

    it('calls startLearn and emits close on start button click', async () => {
        learnStore.startLearn = vi.fn();
        bridgeStore.bridges = [{ id: 'bridge1', name: 'Test Bridge', status: 'online' }];
        const wrapper = mount(LearnModal, {
            props: { show: true },
            global: {
                plugins: [pinia],
                components: { Switch },
            },
        });

        await wrapper.find('.btn-primary').trigger('click');

        expect(learnStore.startLearn).toHaveBeenCalled();
        expect(wrapper.emitted('close')).toBeTruthy();
    });

    it('does not call startLearn if already active', async () => {
        learnStore.learn.active = true;
        learnStore.startLearn = vi.fn();
        bridgeStore.bridges = [{ id: 'bridge1', name: 'Test Bridge', status: 'online' }];
        const wrapper = mount(LearnModal, {
            props: { show: true },
            global: {
                plugins: [pinia],
                components: { Switch },
            },
        });

        // The button is disabled, but we can call the function directly to test the guard
        await wrapper.vm.startAndClose();

        expect(learnStore.startLearn).not.toHaveBeenCalled();
    });

    it('emits close on cancel button click', async () => {
        const wrapper = mount(LearnModal, {
            props: { show: true },
            global: {
                plugins: [pinia],
                components: { Switch },
            },
        });
        await wrapper.find('.btn').trigger('click');
        expect(wrapper.emitted('close')).toBeTruthy();
    });

    it('emits close on background click', async () => {
        const wrapper = mount(LearnModal, {
            props: { show: true },
            global: {
                plugins: [pinia],
                components: { Switch },
            },
        });
        await wrapper.find('.fixed.inset-0').trigger('click');
        expect(wrapper.emitted('close')).toBeTruthy();
    });

    it('toggles smart learn switch', async () => {
        const wrapper = mount(LearnModal, {
            props: { show: true },
            global: {
                plugins: [pinia],
                components: { Switch },
            },
        });
        expect(learnStore.learn.smart).toBe(false);
        await wrapper.find('.cursor-pointer').trigger('click');
        expect(learnStore.learn.smart).toBe(true);
    });
});
