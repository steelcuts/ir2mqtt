import { mount } from '@vue/test-utils';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import IrDbPicker from '../IrDbPicker.vue';
import Switch from '../Switch.vue';
import { useIrdbStore } from '../../stores/irdb';
import { useBridgeStore } from '../../stores/bridges';

// Mock API
vi.mock('../../services/api', () => ({
  api: vi.fn()
}))

describe('IrDbPicker.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const irdbStore = useIrdbStore();
    const bridgeStore = useBridgeStore();

    // Mock store actions and state
    irdbStore.fetchIrdbStatus = vi.fn().mockResolvedValue();
    irdbStore.updateIrdb = vi.fn().mockResolvedValue();
    irdbStore.sendIrCode = vi.fn().mockResolvedValue();
    
    // Mock browseIrdb implementation to simulate file system structure
    irdbStore.browseIrdb = vi.fn().mockImplementation((path) => {
      if (path === '') {
        return Promise.resolve([
          { name: 'RootFolder1', path: 'RootFolder1', type: 'dir' },
          { name: 'RootFile1.json', path: 'RootFile1.json', type: 'file' },
        ]);
      }
      if (path === 'Folder1') {
        return Promise.resolve([{ name: 'SubFile.json', path: 'Folder1/SubFile.json', type: 'file' }]);
      }
      return Promise.resolve([]); 
    });

    irdbStore.loadIrdbFile = vi.fn().mockResolvedValue([]);
    irdbStore.searchIrdb = vi.fn().mockResolvedValue([]);
    
    irdbStore.irdbStatus = { exists: false };
    irdbStore.irdbProgress = null;
    
    bridgeStore.bridges = [{ id: 'bridge1', name: 'Test Bridge', status: 'online' }];
  });

  afterEach(() => {
    // Clean up
  });

  it('renders nothing when show is false', () => {
    const wrapper = mount(IrDbPicker, { props: { show: false } });
    expect(wrapper.find('.fixed.inset-0').exists()).toBe(false);
  });

  it('renders the modal when show is true', async () => {
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await wrapper.vm.$nextTick(); 
    expect(wrapper.find('.fixed.inset-0').exists()).toBe(true);
    expect(wrapper.text()).toContain('IR Database');
  });

  it('displays "No IR Databases installed" when irdbStatus.exists is false', async () => { 
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: false };
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('No IR Databases installed.'); 
      expect(wrapper.find('.btn-primary').text()).toContain('Download Database');
    });
  });

  it('enables/disables "Download Database" button based on switch states', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: false };
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => { 
      expect(wrapper.text()).toContain('No IR Databases installed.');
    });

    const downloadButton = wrapper.find('.btn-primary');
    expect(downloadButton.attributes('disabled')).toBeDefined(); 

    const switches = wrapper.findAllComponents(Switch);
    expect(switches.length).toBe(2);

    // Enable Flipper Zero IRDB
    await switches[0].vm.$emit('update:modelValue', true);
    await wrapper.vm.$nextTick();
    expect(downloadButton.attributes('disabled')).toBeUndefined();

    // Disable both
    await switches[0].vm.$emit('update:modelValue', false);
    await switches[1].vm.$emit('update:modelValue', false);
    await wrapper.vm.$nextTick();
    expect(downloadButton.attributes('disabled')).toBeDefined();

    // Enable Probono IRDB
    await switches[1].vm.$emit('update:modelValue', true);
    await wrapper.vm.$nextTick();
    expect(downloadButton.attributes('disabled')).toBeUndefined();
  });

  it('calls updateIrdb when "Download Database" is clicked', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: false };
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('No IR Databases installed.');
    });

    const switches = wrapper.findAllComponents(Switch);
    await switches[0].vm.$emit('update:modelValue', true); 
    await switches[1].vm.$emit('update:modelValue', false); 
    await wrapper.find('.btn-primary').trigger('click');

    expect(irdbStore.updateIrdb).toHaveBeenCalledWith({ flipper: true, probono: false });
  });

  it('displays update options when "Update DBs" is clicked', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.fetchIrdbStatus).toHaveBeenCalled();
    });

    expect(wrapper.find('[data-tour-id="irdb-update-options-overlay"]').exists()).toBe(false); 
    await wrapper.find('[data-tour-id="irdb-update-options-btn"]').trigger('click'); 
    expect(wrapper.find('[data-tour-id="irdb-update-options-overlay"]').exists()).toBe(true); 

    await wrapper.find('[data-tour-id="irdb-confirm-update-btn"]').trigger('click'); 
    expect(irdbStore.updateIrdb).toHaveBeenCalledWith({ flipper: true, probono: true }); 
    expect(wrapper.find('[data-tour-id="irdb-update-options-overlay"]').exists()).toBe(false); 
  });

  it('displays progress when irdbProgress is active', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: false };
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    irdbStore.irdbProgress = { message: 'Downloading', status: 'in progress', percent: 50 };
    await wrapper.vm.$nextTick();

    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('Downloading');
      expect(wrapper.text()).toContain('50%');
      expect(wrapper.find('.w-full.bg-gray-700').exists()).toBe(true);
    });

    irdbStore.irdbProgress = { message: 'Finishing', status: 'done' }; 
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('Finishing');
    expect(wrapper.find('.animate-spin').exists()).toBe(true);
  });

  it('loads path and displays items when DB exists', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValueOnce([
      { name: 'Folder1', path: 'Folder1', type: 'dir' },
      { name: 'File1.json', path: 'Folder1/File1.json', type: 'file' },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.fetchIrdbStatus).toHaveBeenCalled();
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });

    expect(wrapper.text()).toContain('Folder1');
    expect(wrapper.text()).toContain('File1.json');
    expect(wrapper.find('.mdi-folder').exists()).toBe(true);
    expect(wrapper.find('.mdi-file-document-outline').exists()).toBe(true);
  });

  it('navigates into a directory and back up', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    
    // Setup mock implementation for stable returns based on path
    irdbStore.browseIrdb.mockImplementation((path) => {
      if (path === '') {
        return Promise.resolve([
          { name: 'RootFolder1', path: 'RootFolder1', type: 'dir' },
          { name: 'RootFile1.json', path: 'RootFile1.json', type: 'file' },
        ]);
      }
      if (path === 'Folder1') {
        return Promise.resolve([
          { name: 'SubFile.json', path: 'Folder1/SubFile.json', type: 'file' },
        ]);
      }
      return Promise.resolve([]);
    });

    // Override ONLY the first call to simulate the initial state required by the test
    irdbStore.browseIrdb.mockResolvedValueOnce([
      { name: 'Folder1', path: 'Folder1', type: 'dir' },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });

    // Navigate into Folder1
    await wrapper.find('.mdi-folder').trigger('click');
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('Folder1'); 
      expect(wrapper.text()).toContain('SubFile.json');
      expect(wrapper.find('.mb-4.text-sm').text()).toContain('Folder1'); 
    });

    // Go up
    // Targeted selector to avoid ambiguous 'button.text-xs' match
    await wrapper.find('.mdi-arrow-left').trigger('click'); 
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith(''); 
      expect(wrapper.text()).toContain('RootFolder1'); 
      expect(wrapper.text()).toContain('RootFile1.json'); 
      expect(wrapper.text()).not.toContain('SubFile.json');
    });
  });

  it('loads a file and displays its buttons', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValueOnce([
      { name: 'File1.json', path: 'File1.json', type: 'file' },
    ]);
    irdbStore.loadIrdbFile.mockResolvedValueOnce([
      { name: 'Power', icon: 'power', code: { protocol: 'NEC', payload: { address: '0x00', command: '0x01' } } },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });

    await wrapper.find('.mdi-file-document-outline').trigger('click');
    await vi.waitFor(() => {
      expect(irdbStore.loadIrdbFile).toHaveBeenCalledWith('File1.json');
      expect(wrapper.text()).toContain('Power');
      expect(wrapper.text()).toContain('NEC');
      expect(wrapper.text()).toContain('address');
      expect(wrapper.text()).toContain('0x00');
      expect(wrapper.text()).toContain('command');
      expect(wrapper.text()).toContain('0x01');
    });
  });

  it('emits "select" and "close" when a button is clicked in single selection mode', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValueOnce([
      { name: 'File1.json', path: 'File1.json', type: 'file' },
    ]);
    const mockButton = { name: 'Power', icon: 'power', code: { protocol: 'NEC', payload: { address: '0x00', command: '0x01' } } };
    irdbStore.loadIrdbFile.mockResolvedValueOnce([mockButton]);

    const wrapper = mount(IrDbPicker, { props: { show: true, selectionMode: 'single' } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });
    await wrapper.find('.mdi-file-document-outline').trigger('click');
    await vi.waitFor(() => {
      expect(irdbStore.loadIrdbFile).toHaveBeenCalled();
    });

    await wrapper.find('.group.relative.p-3').trigger('click'); 

    expect(wrapper.emitted().select).toBeTruthy();
    expect(wrapper.emitted().select[0][0]).toEqual(mockButton);
    expect(wrapper.emitted().close).toBeTruthy();
  });

  it('handles multi-selection mode correctly', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValueOnce([
      { name: 'File1.json', path: 'File1.json', type: 'file' },
    ]);
    const mockButtons = [
      { name: 'Power', icon: 'power', code: { protocol: 'NEC', payload: { address: '0x00', command: '0x01' } } },
      { name: 'Volume Up', icon: 'volume-high', code: { protocol: 'NEC', payload: { address: '0x00', command: '0x02' } } },
    ];
    irdbStore.loadIrdbFile.mockResolvedValueOnce(mockButtons);

    const wrapper = mount(IrDbPicker, { props: { show: true, selectionMode: 'multi' } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });
    await wrapper.find('.mdi-file-document-outline').trigger('click');
    await vi.waitFor(() => {
      expect(irdbStore.loadIrdbFile).toHaveBeenCalled();
    });

    const buttonElements = wrapper.findAll('.group.relative.p-3');
    expect(buttonElements.length).toBe(2);

    // Initially all selected in multi-mode
    expect(wrapper.find('input[type="checkbox"][checked]').exists()).toBe(true); 
    expect(wrapper.text()).toContain('Select All (2)');

    // Deselect one
    await buttonElements[0].trigger('click');
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('Select All (1)');

    // Select it again
    await buttonElements[0].trigger('click');
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('Select All (2)');

    // Toggle all off
    const selectAllCheckbox = wrapper.find('label.flex.items-center.gap-2 input[type="checkbox"]');
    await selectAllCheckbox.setChecked(false);
    expect(wrapper.text()).toContain('Select All (0)');

    // Toggle all on
    await selectAllCheckbox.setChecked(true);
    expect(wrapper.text()).toContain('Select All (2)');

    // Import selected
    await wrapper.find('.btn-primary').trigger('click'); 
    expect(wrapper.emitted().select).toBeTruthy();
    expect(wrapper.emitted().select[0][0]).toEqual(mockButtons); 
    expect(wrapper.emitted().close).toBeTruthy();
  });

  it('performs search and displays results', async () => {
    vi.useFakeTimers();
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValueOnce([]); 
    irdbStore.searchIrdb.mockResolvedValueOnce([
      { name: 'SearchRes1', path: 'path/to/SearchRes1.json' },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });

    const searchInput = wrapper.find('input[placeholder="Search devices..."]');
    await searchInput.setValue('test');

    vi.advanceTimersByTime(300); 
    await vi.waitFor(() => {
      expect(irdbStore.searchIrdb).toHaveBeenCalledWith('test');
      expect(wrapper.text()).toContain('SearchRes1');
    });

    // Clear search
    await searchInput.setValue('');
    vi.advanceTimersByTime(300);
    await vi.waitFor(() => {
      expect(wrapper.text()).not.toContain('SearchRes1');
      expect(irdbStore.browseIrdb).toHaveBeenCalledTimes(2); 
    });
    vi.useRealTimers();
  });

  it('handles empty search results', async () => {
    vi.useFakeTimers();
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValueOnce([]);
    irdbStore.searchIrdb.mockResolvedValueOnce([]); 

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });

    const searchInput = wrapper.find('input[placeholder="Search devices..."]');
    await searchInput.setValue('noresults');

    vi.advanceTimersByTime(300);
    await vi.waitFor(() => {
      expect(irdbStore.searchIrdb).toHaveBeenCalledWith('noresults');
      expect(wrapper.text()).toContain('No results found.');
    });
    vi.useRealTimers();
  });

  it('closes the modal when close button is clicked', async () => {
    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await wrapper.vm.$nextTick(); 
    await wrapper.find('.mdi-close').trigger('click');
    expect(wrapper.emitted().close).toBeTruthy();
  });

  it('formats code details correctly', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValueOnce([
      { name: 'File1.json', path: 'File1.json', type: 'file' },
    ]);
    irdbStore.loadIrdbFile.mockResolvedValueOnce([
      { name: 'Raw', icon: 'remote', code: { protocol: 'raw', payload: { timings: [123, 456] } } },
      { name: 'NEC', icon: 'remote', code: { protocol: 'NEC', payload: { address: '0x00', command: '0x01' } } },
      { name: 'Sony', icon: 'remote', code: { protocol: 'sony', payload: { data: '0xE0E0', nbits: '12' } } },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });
    await wrapper.find('.mdi-file-document-outline').trigger('click');
    await vi.waitFor(() => {
      expect(irdbStore.loadIrdbFile).toHaveBeenCalled();
    });

    const buttonElements = wrapper.findAll('.group.relative.p-3');
    expect(buttonElements[0].text()).toContain('pulses');
    expect(buttonElements[0].text()).toContain('2');
    expect(buttonElements[1].text()).toContain('address');
    expect(buttonElements[1].text()).toContain('0x00');
    expect(buttonElements[1].text()).toContain('command');
    expect(buttonElements[1].text()).toContain('0x01');
    expect(buttonElements[2].text()).toContain('data');
    expect(buttonElements[2].text()).toContain('0xE0E0');
  });

  it('handles error when loading IR file', async () => {
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    irdbStore.browseIrdb.mockResolvedValueOnce([
      { name: 'File1.json', path: 'File1.json', type: 'file' },
    ]);
    irdbStore.loadIrdbFile.mockRejectedValueOnce(new Error('File not found'));
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });

    await wrapper.find('.mdi-file-document-outline').trigger('click');
    await vi.waitFor(() => {
      expect(irdbStore.loadIrdbFile).toHaveBeenCalledWith('File1.json');
      expect(alertSpy).toHaveBeenCalledWith('Error loading file: File not found');
    });
    alertSpy.mockRestore();
  });

  it('navigates from search result to file view and then back to root', async () => {
    vi.useFakeTimers();
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    
    // Reset to ensure clean state and define implementation
    irdbStore.browseIrdb.mockReset();
    irdbStore.browseIrdb.mockImplementation((path) => {
        if (path === '') return Promise.resolve([
            { name: 'RootFolder1', path: 'RootFolder1', type: 'dir' },
            { name: 'RootFile1.json', path: 'RootFile1.json', type: 'file' },
        ]);
        return Promise.resolve([]);
    });

    irdbStore.browseIrdb.mockResolvedValueOnce([
        { name: 'RootFolder1', path: 'RootFolder1', type: 'dir' },
        { name: 'RootFile1.json', path: 'RootFile1.json', type: 'file' },
    ]); // Initial load

    irdbStore.searchIrdb.mockResolvedValueOnce([
      { name: 'SearchedFile.json', path: 'SearchedFile.json', type: 'file' },
    ]);
    irdbStore.loadIrdbFile.mockResolvedValueOnce([
      { name: 'Power', icon: 'power', code: { protocol: 'NEC', payload: { address: '0x00', command: '0x01' } } },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });

    const searchInput = wrapper.find('input[placeholder="Search devices..."]');
    await searchInput.setValue('searchterm');
    vi.advanceTimersByTime(300);
    await vi.waitFor(() => {
      expect(irdbStore.searchIrdb).toHaveBeenCalledWith('searchterm');
      expect(wrapper.text()).toContain('SearchedFile.json');
    });

    // Click on search result to open file, ensure it's rendered first
    await vi.waitFor(() => expect(wrapper.find('.group.items-center').exists()).toBe(true));
    await wrapper.find('.group.items-center').trigger('click');
    await vi.waitFor(() => {
      expect(irdbStore.loadIrdbFile).toHaveBeenCalledWith('SearchedFile.json');
      expect(wrapper.text()).toContain('Power');
    });

    // Click "Back" button
    await wrapper.find('.mdi-arrow-left').trigger('click');
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith(''); 
      expect(wrapper.text()).toContain('RootFolder1'); 
      expect(wrapper.text()).toContain('RootFile1.json'); 
      expect(wrapper.text()).not.toContain('Power'); 
      expect(wrapper.text()).not.toContain('SearchedFile.json'); 
    });
    vi.useRealTimers();
  });
  
  it('navigates from search result (directory) to directory view and then back to root', async () => {
    vi.useFakeTimers();
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    
    irdbStore.browseIrdb.mockReset();
    irdbStore.browseIrdb.mockImplementation((path) => {
        if (path === '') return Promise.resolve([
            { name: 'RootFolder1', path: 'RootFolder1', type: 'dir' },
            { name: 'RootFile1.json', path: 'RootFile1.json', type: 'file' },
        ]);
        if (path === 'SearchedDir') return Promise.resolve([
            { name: 'FileInDir.json', path: 'SearchedDir/FileInDir.json', type: 'file' },
        ]);
        return Promise.resolve([]);
    });

    irdbStore.browseIrdb.mockResolvedValueOnce([]); 

    irdbStore.searchIrdb.mockResolvedValueOnce([
      { name: 'SearchedDir', path: 'SearchedDir', type: 'dir' },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });

    const searchInput = wrapper.find('input[placeholder="Search devices..."]');
    await searchInput.setValue('searchterm');
    vi.advanceTimersByTime(300);
    await vi.waitFor(() => {
      expect(irdbStore.searchIrdb).toHaveBeenCalledWith('searchterm');
      expect(wrapper.text()).toContain('SearchedDir');
    });

    // Click on search result (directory) to open directory
    await vi.waitFor(() => expect(wrapper.find('.group.items-center').exists()).toBe(true));
    await wrapper.find('.group.items-center').trigger('click');
    await vi.waitFor(() => {
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith('SearchedDir');
      expect(wrapper.text()).toContain('FileInDir.json');
    });

    // Click "Back" button
    await wrapper.find('.mdi-arrow-left').trigger('click');
    await vi.waitFor(() => { 
      expect(irdbStore.browseIrdb).toHaveBeenCalledWith(''); 
      expect(wrapper.text()).not.toContain('FileInDir.json'); 
      expect(wrapper.text()).toContain('RootFolder1'); 
      expect(wrapper.text()).toContain('RootFile1.json'); 
    });
    vi.useRealTimers();
  });
  
  it('updates the path when a file is opened from search results', async () => {
    vi.useFakeTimers();
    const irdbStore = useIrdbStore();
    irdbStore.irdbStatus = { exists: true };
    
    // Mock search to return a file in a subdirectory
    irdbStore.searchIrdb.mockResolvedValueOnce([
      { name: 'MyRemote.ir', path: 'flipper/TVs/MyRemote.ir', type: 'file' },
    ]);

    // Mock file loading
    irdbStore.loadIrdbFile.mockResolvedValueOnce([
        { name: 'Power', code: { protocol: 'NEC' } },
    ]);

    const wrapper = mount(IrDbPicker, { props: { show: true } });
    
    // 1. Initial load (usually to root)
    await vi.waitFor(() => {
        expect(irdbStore.browseIrdb).toHaveBeenCalledWith('');
    });

    // 2. Perform a search
    const searchInput = wrapper.find('input[placeholder="Search devices..."]');
    await searchInput.setValue('myremote');
    vi.advanceTimersByTime(300); // Wait for debounce
    await vi.waitFor(() => {
        expect(irdbStore.searchIrdb).toHaveBeenCalledWith('myremote');
        expect(wrapper.text()).toContain('MyRemote.ir');
    });

    // 3. Click the search result
    await wrapper.find('.group.items-center').trigger('click');
    await vi.waitFor(() => {
        expect(irdbStore.loadIrdbFile).toHaveBeenCalledWith('flipper/TVs/MyRemote.ir');
    });

    // 4. Assertions
    // The search query should be cleared
    expect(wrapper.find('input[placeholder="Search devices..."]').element.value).toBe('');
    
    // The view should now show the file's content
    expect(wrapper.text()).toContain('Power');
    
    // The breadcrumbs should reflect the file's directory path
    const breadcrumbText = wrapper.find('.flex.items-center.gap-2.mb-4').text();
    expect(breadcrumbText).toContain('flipper');
    expect(breadcrumbText).toContain('TVs');
    expect(breadcrumbText).toContain('MyRemote.ir'); // The file name should be the last part
    
    vi.useRealTimers();
  });
});