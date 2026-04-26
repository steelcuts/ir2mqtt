import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DeviceModal from '../DeviceModal.vue'
import BridgeSelector from '../BridgeSelector.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useDeviceStore } from '../../stores/devices'
import { useSettingsStore } from '../../stores/settings'
import { api } from '../../services/api'

// Mock API
vi.mock('../../services/api', () => ({
  api: vi.fn((path, options) => {
    if (path === 'devices' && (!options || options.method === 'GET')) {
      return Promise.resolve([])
    }
    return Promise.resolve({ id: '123' })
  })
}))

describe('DeviceModal Component', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const deviceStore = useDeviceStore()
    const settingsStore = useSettingsStore()
    deviceStore.devices = []
    settingsStore.appMode = 'home_assistant'
  })

  it('renders correctly in add mode', async () => {
    const wrapper = mount(DeviceModal, {
      props: { show: false, device: null, bridges: [] }
    })
    await wrapper.setProps({ show: true })
    expect(wrapper.text()).toContain('Add New Device')
    expect(wrapper.find('button.btn-primary').text()).toContain('Add Device')
  })

  it('renders correctly in edit mode', async () => {
    const device = { id: '1', name: 'My TV', icon: 'tv', target_bridges: [] }
    const wrapper = mount(DeviceModal, {
      props: { show: false, device, bridges: [] }
    })
    await wrapper.setProps({ show: true })
    expect(wrapper.text()).toContain('Edit Device')
    expect(wrapper.find('input[placeholder*="Living Room TV"]').element.value).toBe('My TV')
  })

  it('shows tour button in add mode', async () => {
    const wrapper = mount(DeviceModal, {
      props: { show: false, device: null, bridges: [] }
    })
    await wrapper.setProps({ show: true });
    await wrapper.vm.$nextTick()
    const tourButton = wrapper.find('button[title="Start Tour"]')
    expect(tourButton.exists()).toBe(true)
  })

  it('hides tour button in edit mode', async () => {
    const device = { id: '1', name: 'My TV', icon: 'tv', target_bridges: [] }
    const wrapper = mount(DeviceModal, {
      props: { show: false, device, bridges: [] }
    })
    await wrapper.setProps({ show: true });
    await wrapper.vm.$nextTick()
    const tourButton = wrapper.find('button[title="Start Tour"]')
    expect(tourButton.exists()).toBe(false)
  })

  it('validates empty name', async () => {
    const wrapper = mount(DeviceModal, {
      props: { show: false, device: null, bridges: [] }
    })
    await wrapper.setProps({ show: true })
    await wrapper.find('button.btn-primary').trigger('click')
    // Should not call addDevice if invalid, but here we check if error is shown or button disabled
    // The button is disabled if !isValid
    expect(wrapper.find('button.btn-primary').attributes('disabled')).toBeDefined()
  })

  it('renders BridgeSelector component', async () => {
    const wrapper = mount(DeviceModal, {
      props: { show: false, device: null, bridges: [] }
    })
    await wrapper.setProps({ show: true })
    expect(wrapper.findComponent(BridgeSelector).exists()).toBe(true)
  })

  it('applies template correctly', async () => {
    const wrapper = mount(DeviceModal, {
      props: { show: false, device: null, bridges: [] }
    })
    await wrapper.setProps({ show: true })
    
    // Find template selector
    const select = wrapper.find('select')
    await select.setValue('tv') // Assuming 'tv' is a valid template ID from templates.ts
    
    // Check if name and icon updated
    expect(wrapper.vm.localDevice.name).toBe('TV')
    expect(wrapper.vm.localDevice.icon).toBe('television')
  })

  it('saves new device successfully', async () => {
    const wrapper = mount(DeviceModal, {
      props: { show: false, device: null, bridges: [] }
    })
    await wrapper.setProps({ show: true })

    // Fill name
    await wrapper.find('input[placeholder*="Living Room TV"]').setValue('New Device')
    
    // Click Save
    await wrapper.find('button.btn-primary').trigger('click')
    await flushPromises()

    expect(api).toHaveBeenCalledWith('devices', expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('New Device')
    }))
    
    expect(api).toHaveBeenCalledWith('devices')
    expect(wrapper.emitted('device-created')).toBeTruthy()
  })

  it('imports buttons from IRDB', async () => {
    const wrapper = mount(DeviceModal, {
      props: { show: false, device: null, bridges: [] }
    })
    await wrapper.setProps({ show: true })
    
    const mockButtons = [
      { name: 'Power', code: { protocol: 'nec' } },
      { name: 'Vol+', code: { protocol: 'nec' } }
    ]
    
    // Simulate selection from IrDbPicker
    const picker = wrapper.findComponent({ name: 'IrDbPicker' })
    picker.vm.$emit('select', mockButtons)
    
    expect(wrapper.vm.importedButtons).toHaveLength(2)
    
    // Save and check if buttons are included
    await wrapper.find('input[placeholder*="Living Room TV"]').setValue('Imported TV')
    await wrapper.find('button.btn-primary').trigger('click')
    
    const postCall = api.mock.calls.find(c => c[0] === 'devices' && c[1].method === 'POST')
    expect(postCall).toBeDefined()
    const body = JSON.parse(postCall[1].body)
    expect(body.buttons).toHaveLength(2)
    expect(body.buttons[0].name).toBe('Power')
  })
})