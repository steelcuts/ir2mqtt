import {
  describe, it, expect, vi, beforeEach
} from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import IrDbPicker from '../IrDbPicker.vue';
import { useIrdbStore } from '../../stores/irdb';
import { useBridgeStore } from '../../stores/bridges';

describe('IrDbPicker', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const irdbStore = useIrdbStore();
    irdbStore.fetchIrdbStatus = vi.fn().mockResolvedValue(undefined);
    irdbStore.browseIrdb = vi.fn();
    irdbStore.searchIrdb = vi.fn();
    irdbStore.loadIrdbFile = vi.fn();
    irdbStore.updateIrdb = vi.fn().mockResolvedValue(undefined);
    irdbStore.sendIrCode = vi.fn().mockResolvedValue(undefined);
    irdbStore.irdbStatus = { exists: false };
    irdbStore.irdbProgress = null;

    const bridgeStore = useBridgeStore();
    bridgeStore.bridges = [];
  });

  it('does not render when show prop is false', () => {
    const wrapper = mount(IrDbPicker, { props: { show: false } });
    expect(wrapper.find('.fixed').exists()).toBe(false);
  });

  it('renders when show prop is true', () => {
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    expect(wrapper.find('.fixed').exists()).toBe(true);
  });

  it('shows "No IR Databases installed" message', async () => {
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('No IR Databases installed.');
  });

  it('starts the database update process', async () => {
    const irdbStore = useIrdbStore();
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await wrapper.vm.$nextTick();

    wrapper.vm.updateFlipper = true;
    wrapper.vm.updateProbono = true;
    await wrapper.vm.$nextTick();

    await wrapper.find('button.btn-primary').trigger('click');

    expect(irdbStore.updateIrdb).toHaveBeenCalledWith({ flipper: true, probono: true });
  });

  it('browses the database', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValue([
      { name: 'TVs', path: 'TVs', type: 'dir' },
      { name: 'Fans', path: 'Fans', type: 'dir' },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });

    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    await new Promise(resolve => setTimeout(resolve, 0)); // Wait for promises

    expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    expect(wrapper.text()).toContain('TVs');
    expect(wrapper.text()).toContain('Fans');

    // Simulate clicking on 'TVs'
    irdbStore.browseIrdb.mockResolvedValueOnce([
      { name: 'Samsung', path: 'TVs/Samsung', type: 'dir' },
    ]);
    await wrapper.findAll('.group')[0].trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(irdbStore.browseIrdb).toHaveBeenCalledWith('TVs');
  });

  it('searches the database', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.searchIrdb.mockResolvedValue([
      { name: 'MyTV', path: 'TVs/MyTV', type: 'file' },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    await new Promise(resolve => setTimeout(resolve, 0));

    const searchInput = wrapper.find('input[placeholder="Search devices..."]');
    await searchInput.setValue('MyTV');
    await new Promise((r) => { setTimeout(r, 400); });

    expect(irdbStore.searchIrdb).toHaveBeenCalledWith('MyTV');
  });

  it('views a file and selects a single button', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValue([{ name: 'TV.ir', path: 'TVs/TV.ir', type: 'file' }]);
    const mockButton = { name: 'Power', icon: 'power', code: { protocol: 'NEC', address: '0x00', command: '0x00' } };
    irdbStore.loadIrdbFile.mockResolvedValue([mockButton]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    await new Promise(resolve => setTimeout(resolve, 0));

    await wrapper.find('.group').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(irdbStore.loadIrdbFile).toHaveBeenCalledWith('TVs/TV.ir');

    await wrapper.find('.group').trigger('click');
    await wrapper.vm.$nextTick();

    expect(wrapper.emitted().select[0][0]).toEqual(mockButton);
    expect(wrapper.emitted().close).toBeDefined();
  });

  it('views a file and selects multiple buttons', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValue([{ name: 'TV.ir', path: 'TVs/TV.ir', type: 'file' }]);
    const mockButtons = [
      { name: 'Power', icon: 'power', code: { protocol: 'NEC', address: '0x00', command: '0x00' } },
      { name: 'Vol+', icon: 'volume-plus', code: { protocol: 'NEC', address: '0x00', command: '0x01' } },
    ];
    irdbStore.loadIrdbFile.mockResolvedValue(mockButtons);

    const wrapper = mount(IrDbPicker, { props: { show: true, selectionMode: 'multi' } });
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    await new Promise(resolve => setTimeout(resolve, 0));

    await wrapper.find('.group').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(irdbStore.loadIrdbFile).toHaveBeenCalledWith('TVs/TV.ir');
    expect(wrapper.text()).toContain('Select All (2)');

    await wrapper.findAll('.group')[0].trigger('click');
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('Select All (1)');

    await wrapper.find('button.btn-primary').trigger('click');

    expect(wrapper.emitted().select[0][0]).toEqual([mockButtons[1]]);
    expect(wrapper.emitted().close).toBeDefined();
  });

  it('sends an IR code', async () => {
    const irdbStore = useIrdbStore();
    const bridgeStore = useBridgeStore();
    irdbStore.irdbStatus = { exists: true };
    bridgeStore.bridges = [{
      id: '1', name: 'Test Bridge', status: 'online', ip: '1.1.1.1', type: 'dummy'
    }];
    irdbStore.browseIrdb.mockResolvedValue([{ name: 'TV.ir', path: 'TVs/TV.ir', type: 'file' }]);
    const mockButton = { name: 'Power', icon: 'power', code: { protocol: 'NEC', address: '0x00', command: '0x00' } };
    irdbStore.loadIrdbFile.mockResolvedValue([mockButton]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    await new Promise(resolve => setTimeout(resolve, 0));

    await wrapper.find('.group').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.vm.$nextTick();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(irdbStore.loadIrdbFile).toHaveBeenCalledWith('TVs/TV.ir');

    // Select the bridge target first (required before send is enabled)
    await wrapper.find('[data-tour-id="target-selector-btn"]').trigger('click');
    await wrapper.vm.$nextTick();

    const bridgeCheckbox = wrapper.find('input[type="checkbox"]');
    await bridgeCheckbox.setValue(true);
    await wrapper.vm.$nextTick();

    await wrapper.find('button[title="Send IR Code"]').trigger('click');
    await wrapper.vm.$nextTick();

    expect(irdbStore.sendIrCode).toHaveBeenCalledWith(mockButton.code, ['1']);
  });
});
