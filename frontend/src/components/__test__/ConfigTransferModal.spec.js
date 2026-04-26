import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ConfigTransferModal from '../ConfigTransferModal.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useCommonStore } from '../../stores/common'
import { api } from '../../services/api'

// Mock API
vi.mock('../../services/api', () => ({
  api: vi.fn()
}))

// Mock TreeView to avoid complexity of child component
vi.mock('../TreeView.vue', () => ({
  default: {
    name: 'TreeView',
    props: ['items'],
    template: '<div class="mock-tree-view"></div>',
    emits: ['update:modelValue']
  }
}))

describe('ConfigTransferModal Component', () => {
  const mockConfig = {
    devices: [
      { id: 'd1', name: 'Device 1', icon: 'tv', target_bridges: [], buttons: [
          { id: 'b1', name: 'Power', code: { protocol: 'nec', address: '0x00', command: '0x00' } }
      ]}
    ],
    automations: [
      { id: 'a1', name: 'Auto 1', actions: [] }
    ]
  }

  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    api.mockResolvedValue(JSON.parse(JSON.stringify(mockConfig)))
  })

  it('renders correctly when hidden', () => {
    const wrapper = mount(ConfigTransferModal, {
      props: { show: false }
    })
    expect(wrapper.find('.fixed').exists()).toBe(false)
  })

  it('renders correctly when shown and fetches config', async () => {
    const wrapper = mount(ConfigTransferModal, {
      props: { show: false }
    })
    
    await wrapper.setProps({ show: true })
    await flushPromises()
    
    expect(wrapper.find('.fixed').exists()).toBe(true)
    expect(wrapper.text()).toContain('Configuration Transfer')
    expect(api).toHaveBeenCalledWith('config/export')
    expect(wrapper.findComponent({ name: 'TreeView' }).exists()).toBe(true)
  })

  it('switches between export and import modes', async () => {
    const wrapper = mount(ConfigTransferModal, {
      props: { show: false }
    })
    await wrapper.setProps({ show: true })
    await flushPromises()

    // Default is export
    expect(wrapper.text()).toContain('Export Configuration')
    
    // Switch to import
    const buttons = wrapper.findAll('button')
    const importBtn = buttons.find(b => b.text() === 'Import')
    await importBtn.trigger('click')
    
    expect(wrapper.text()).toContain('Import Configuration')
    expect(wrapper.find('input[type="file"]').exists()).toBe(true)

    // Switch back to export
    const exportBtn = buttons.find(b => b.text() === 'Export')
    await exportBtn.trigger('click')
    expect(wrapper.text()).toContain('Export Configuration')
  })

  it('handles file selection and generates import tree', async () => {
    const wrapper = mount(ConfigTransferModal, {
      props: { show: false }
    })
    await wrapper.setProps({ show: true })
    await flushPromises()
    
    // Switch to import
    await wrapper.findAll('button').find(b => b.text() === 'Import').trigger('click')
    
    const importData = {
      devices: [
        { id: 'd1', name: 'Device 1 Changed', icon: 'tv', target_bridges: [], buttons: [] }, // Changed
        { id: 'd2', name: 'Device 2 New', icon: 'light', target_bridges: [], buttons: [] }   // New
      ],
      automations: []
    }
    
    const file = new File([JSON.stringify(importData)], 'config.json', { type: 'application/json' })
    
    // Mock FileReader
    const originalFileReader = window.FileReader
    window.FileReader = class {
      readAsText() {
        this.onload({ target: { result: JSON.stringify(importData) } })
      }
    }

    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    
    await flushPromises()
    
    // Check if tree view is populated
    const treeView = wrapper.findComponent({ name: 'TreeView' })
    const items = treeView.props('items')
    expect(items).toHaveLength(1) // Only devices changed/new
    expect(items[0].id).toBe('devices')
    expect(items[0].children).toHaveLength(2) // d1 and d2

    // Restore FileReader
    window.FileReader = originalFileReader
  })

  it('applyImport sends data to API', async () => {
    const commonStore = useCommonStore()
    const addFlashMessageSpy = vi.spyOn(commonStore, 'addFlashMessage')

    const wrapper = mount(ConfigTransferModal, {
      props: { show: false }
    })
    await wrapper.setProps({ show: true })
    await flushPromises()
    
    // Switch to import
    await wrapper.findAll('button').find(b => b.text() === 'Import').trigger('click')
    
    // Setup import data manually
    const importData = {
      devices: [{ id: 'd2', name: 'New Device', icon: 'tv', target_bridges: [], buttons: [] }],
      automations: []
    }
    wrapper.vm.importData = importData
    wrapper.vm.generateImportTree()
    await wrapper.vm.$nextTick()

    // Mock API for import
    api.mockResolvedValueOnce({})

    // Click Apply Import
    const applyBtn = wrapper.findAll('button').find(b => b.text().includes('Apply Import'))
    await applyBtn.trigger('click')
    
    expect(api).toHaveBeenCalledWith('config/import', expect.objectContaining({
      method: 'POST',
      body: expect.any(FormData)
    }))
    
    expect(addFlashMessageSpy).toHaveBeenCalledWith('Import successful!', 'success')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('renames duplicates during import', async () => {
    const wrapper = mount(ConfigTransferModal, {
      props: { show: false }
    })
    await wrapper.setProps({ show: true })
    await flushPromises()
    
    // Switch to import
    await wrapper.findAll('button').find(b => b.text() === 'Import').trigger('click')
    
    // Current config has "Device 1" (from beforeEach mock)
    // Import data also has "Device 1" but with different ID (simulating conflict)
    const importData = {
      devices: [{ id: 'd_new', name: 'Device 1', icon: 'tv', target_bridges: [], buttons: [] }],
      automations: []
    }
    
    wrapper.vm.importData = importData
    wrapper.vm.generateImportTree()
    await wrapper.vm.$nextTick()

    // Mock API
    api.mockResolvedValueOnce({})

    // Apply Import
    const applyBtn = wrapper.findAll('button').find(b => b.text().includes('Apply Import'))
    await applyBtn.trigger('click')
    
    // Check the payload sent to API
    const importCall = api.mock.calls.find(call => call[0] === 'config/import')
    expect(importCall).toBeDefined()
    
    // Verify it was a POST request
    expect(importCall[1].method).toBe('POST')
    expect(importCall[1].body).toBeInstanceOf(FormData)
  })

  it('handles API error during import', async () => {
    const wrapper = mount(ConfigTransferModal, {
      props: { show: false }
    })
    await wrapper.setProps({ show: true })
    await flushPromises()

    // Switch to import
    await wrapper.findAll('button').find(b => b.text() === 'Import').trigger('click')

    // Setup import data
    wrapper.vm.importData = { devices: [], automations: [] }
    wrapper.vm.generateImportTree()
    await wrapper.vm.$nextTick()

    // Mock API failure
    api.mockRejectedValueOnce(new Error('Import failed'))

    // Click Apply - should not close modal on error
    await wrapper.findAll('button').find(b => b.text().includes('Apply Import')).trigger('click')
    await flushPromises()

    expect(wrapper.emitted('close')).toBeFalsy()
  })

  // ─── Duplicate ID detection ──────────────────────────────────────────────────

  it('flags duplicate device IDs in the import file as DUPLICATE ID, deselected', async () => {
    const wrapper = mount(ConfigTransferModal, { props: { show: false } })
    await wrapper.setProps({ show: true })
    await flushPromises()

    await wrapper.findAll('button').find(b => b.text() === 'Import').trigger('click')

    wrapper.vm.importData = {
      devices: [
        { id: 'dup', name: 'Device A', icon: 'tv', target_bridges: [], buttons: [] },
        { id: 'dup', name: 'Device B', icon: 'tv', target_bridges: [], buttons: [] },
        { id: 'd-unique', name: 'Device C', icon: 'tv', target_bridges: [], buttons: [] },
      ],
      automations: [],
    }
    wrapper.vm.generateImportTree()
    await wrapper.vm.$nextTick()

    const items = wrapper.findComponent({ name: 'TreeView' }).props('items')
    const devChildren = items.find(n => n.id === 'devices').children

    const dupItems = devChildren.filter(c => c.id === 'dup')
    expect(dupItems).toHaveLength(2)
    dupItems.forEach(item => {
      expect(item.details).toBe('DUPLICATE ID')
      expect(item.textClass).toBe('text-red-400')
      expect(item.selected).toBe(false)
    })

    // Unique device is processed normally (NEW)
    const uniqueItem = devChildren.find(c => c.id === 'd-unique')
    expect(uniqueItem.details).toBe('NEW')
    expect(uniqueItem.selected).toBe(true)
  })

  it('flags duplicate automation IDs in the import file as DUPLICATE ID, deselected', async () => {
    const wrapper = mount(ConfigTransferModal, { props: { show: false } })
    await wrapper.setProps({ show: true })
    await flushPromises()

    await wrapper.findAll('button').find(b => b.text() === 'Import').trigger('click')

    wrapper.vm.importData = {
      devices: [],
      automations: [
        { id: 'dup-auto', name: 'Auto A', actions: [] },
        { id: 'dup-auto', name: 'Auto B', actions: [] },
        { id: 'a-unique', name: 'Auto C', actions: [] },
      ],
    }
    wrapper.vm.generateImportTree()
    await wrapper.vm.$nextTick()

    const items = wrapper.findComponent({ name: 'TreeView' }).props('items')
    const autoChildren = items.find(n => n.id === 'automations').children

    const dupItems = autoChildren.filter(c => c.id === 'dup-auto')
    expect(dupItems).toHaveLength(2)
    dupItems.forEach(item => {
      expect(item.details).toBe('DUPLICATE ID')
      expect(item.textClass).toBe('text-red-400')
      expect(item.selected).toBe(false)
    })

    const uniqueItem = autoChildren.find(c => c.id === 'a-unique')
    expect(uniqueItem.details).toBe('NEW')
    expect(uniqueItem.selected).toBe(true)
  })

  it('flags duplicate button IDs within a device as DUPLICATE ID, deselected', async () => {
    const wrapper = mount(ConfigTransferModal, { props: { show: false } })
    await wrapper.setProps({ show: true })
    await flushPromises()

    await wrapper.findAll('button').find(b => b.text() === 'Import').trigger('click')

    wrapper.vm.importData = {
      devices: [
        {
          id: 'd-new', name: 'Device New', icon: 'tv', target_bridges: [], buttons: [
            { id: 'btn-dup', name: 'Button A', icon: '', code: null },
            { id: 'btn-dup', name: 'Button B', icon: '', code: null },
            { id: 'btn-unique', name: 'Button C', icon: '', code: null },
          ],
        },
      ],
      automations: [],
    }
    wrapper.vm.generateImportTree()
    await wrapper.vm.$nextTick()

    const items = wrapper.findComponent({ name: 'TreeView' }).props('items')
    const devNode = items.find(n => n.id === 'devices').children[0]

    const dupBtns = devNode.children.filter(b => b.id === 'btn-dup')
    expect(dupBtns).toHaveLength(2)
    dupBtns.forEach(btn => {
      expect(btn.details).toBe('DUPLICATE ID')
      expect(btn.textClass).toBe('text-red-400')
      expect(btn.selected).toBe(false)
    })

    const uniqueBtn = devNode.children.find(b => b.id === 'btn-unique')
    expect(uniqueBtn.details).toBe('NEW')
    expect(uniqueBtn.selected).toBe(true)
  })

  it('shows a flash warning when duplicate IDs are found', async () => {
    const commonStore = useCommonStore()
    const addFlashMessageSpy = vi.spyOn(commonStore, 'addFlashMessage')

    const wrapper = mount(ConfigTransferModal, { props: { show: false } })
    await wrapper.setProps({ show: true })
    await flushPromises()

    wrapper.vm.importData = {
      devices: [
        { id: 'dup', name: 'A', icon: 'tv', target_bridges: [], buttons: [] },
        { id: 'dup', name: 'B', icon: 'tv', target_bridges: [], buttons: [] },
      ],
      automations: [],
    }
    wrapper.vm.generateImportTree()
    await wrapper.vm.$nextTick()

    expect(addFlashMessageSpy).toHaveBeenCalledWith(
      expect.stringContaining('dup'),
      'warning',
    )
  })

  it('does not warn when there are no duplicate IDs', async () => {
    const commonStore = useCommonStore()
    const addFlashMessageSpy = vi.spyOn(commonStore, 'addFlashMessage')

    const wrapper = mount(ConfigTransferModal, { props: { show: false } })
    await wrapper.setProps({ show: true })
    await flushPromises()

    wrapper.vm.importData = {
      devices: [
        { id: 'd-new', name: 'Device New', icon: 'tv', target_bridges: [], buttons: [] },
      ],
      automations: [],
    }
    wrapper.vm.generateImportTree()
    await wrapper.vm.$nextTick()

    expect(addFlashMessageSpy).not.toHaveBeenCalledWith(expect.anything(), 'warning')
  })

  // ─── applyImport: automation update vs. duplicate ────────────────────────────

  it('applyImport updates an existing automation without creating a duplicate', async () => {
    const wrapper = mount(ConfigTransferModal, { props: { show: false } })
    await wrapper.setProps({ show: true })
    await flushPromises()

    await wrapper.findAll('button').find(b => b.text() === 'Import').trigger('click')

    // Current config (from beforeEach) has automation { id: 'a1', name: 'Auto 1' }
    // Import the same ID with a changed name
    wrapper.vm.importData = {
      devices: [],
      automations: [{ id: 'a1', name: 'Auto 1 Renamed', actions: [] }],
    }
    wrapper.vm.generateImportTree()
    await wrapper.vm.$nextTick()

    api.mockResolvedValueOnce({})
    await wrapper.findAll('button').find(b => b.text().includes('Apply Import')).trigger('click')
    await flushPromises()

    const importCall = api.mock.calls.find(call => call[0] === 'config/import')
    expect(importCall).toBeDefined()

    const blob = importCall[1].body.get('file')
    const sentText = await new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (e) => resolve(e.target.result)
      reader.readAsText(blob)
    })
    const sentConfig = JSON.parse(sentText)

    // Must have exactly one automation (updated, not duplicated)
    expect(sentConfig.automations).toHaveLength(1)
    expect(sentConfig.automations[0].id).toBe('a1')
    expect(sentConfig.automations[0].name).toBe('Auto 1 Renamed')
  })
})