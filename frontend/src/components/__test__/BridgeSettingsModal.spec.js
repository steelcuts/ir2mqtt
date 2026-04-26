import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import BridgeSettingsModal from '../BridgeSettingsModal.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useBridgeStore } from '../../stores/bridges'

// Mock API
vi.mock('../../services/api', () => ({
  api: vi.fn(() => Promise.resolve())
}))

// Mock Switch component to be a simple checkbox for testing
vi.mock('../Switch.vue', () => ({
  default: {
    template: '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
    props: ['modelValue'],
    emits: ['update:modelValue']
  }
}))

describe('BridgeSettingsModal Component', () => {
  const mockBridge = {
    id: 'b1',
    name: 'Test Bridge',
    settings: {
      echo_enabled: true,
      echo_timeout: 200,
      echo_smart: false,
      echo_ignore_self: false,
      echo_ignore_others: true
    }
  }

  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('renders correctly when hidden', () => {
    const wrapper = mount(BridgeSettingsModal, {
      props: { show: false, bridge: mockBridge }
    })
    expect(wrapper.find('.fixed').exists()).toBe(false)
  })

  it('renders correctly when shown and loads settings', async () => {
    const wrapper = mount(BridgeSettingsModal, {
      props: { show: true, bridge: mockBridge }
    })
    
    expect(wrapper.text()).toContain('Bridge Settings: Test Bridge')
    expect(wrapper.text()).toContain('Echo Suppression')
    
    // Check timeout input
    const timeoutInput = wrapper.find('input[type="number"]')
    expect(timeoutInput.element.value).toBe('200')
    
    // Check switches (mocked as checkboxes)
    // The order in template is: Enabled, Smart, Self, Others
    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    
    expect(checkboxes[0].element.checked).toBe(true)  // Enabled
    expect(checkboxes[1].element.checked).toBe(false) // Smart
    expect(checkboxes[2].element.checked).toBe(false) // Self
    expect(checkboxes[3].element.checked).toBe(true)  // Others
  })

  it('uses default settings if bridge has none', async () => {
    const bridgeNoSettings = { id: 'b2', name: 'New Bridge' }
    const wrapper = mount(BridgeSettingsModal, {
      props: { show: true, bridge: bridgeNoSettings }
    })
    
    // Default enabled is false
    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    expect(checkboxes[0].element.checked).toBe(false)

    // Enable to check default timeout
    await checkboxes[0].setValue(true)
    expect(wrapper.find('input[type="number"]').element.value).toBe('500')
  })

  it('saves settings on save button click', async () => {
    const bridgeStore = useBridgeStore()
    // Spy on store actions
    const updateSpy = vi.spyOn(bridgeStore, 'updateBridgeSettings')
    const fetchSpy = vi.spyOn(bridgeStore, 'fetchBridges')

    const wrapper = mount(BridgeSettingsModal, {
      props: { show: true, bridge: mockBridge }
    })
    
    // Change timeout
    await wrapper.find('input[type="number"]').setValue(1000)
    
    // Click Save
    await wrapper.find('button.btn-primary').trigger('click')
    
    await flushPromises()
    expect(updateSpy).toHaveBeenCalledWith('b1', expect.objectContaining({
      echo_timeout: 1000,
      echo_enabled: true
    }))
    expect(fetchSpy).toHaveBeenCalled()
    expect(wrapper.emitted('close')).toBeTruthy()
  })
})