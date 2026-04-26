import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import Automations from '../Automations.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useAutomationsStore } from '../../stores/automations'
import { useDeviceStore } from '../../stores/devices'
import { useSettingsStore } from '../../stores/settings'

describe('Automations View', () => {
  const mockDevices = [
    { id: 'd1', name: 'Device 1', buttons: [{ id: 'b1', name: 'Button 1', icon: 'power' }] }
  ]

  beforeEach(() => {
    setActivePinia(createPinia())
    const deviceStore = useDeviceStore()
    const automationsStore = useAutomationsStore()
    const settingsStore = useSettingsStore()

    deviceStore.devices = mockDevices
    automationsStore.automations = []
    settingsStore.appMode = 'standalone'
    
    // Mock actions
    automationsStore.triggerAutomation = vi.fn()
    automationsStore.deleteAutomation = vi.fn()
    automationsStore.duplicateAutomation = vi.fn()
    automationsStore.reorderAutomations = vi.fn()
  })

  it('renders empty state correctly', () => {
    const wrapper = mount(Automations)
    expect(wrapper.text()).toContain('No automations defined yet')
  })

  it('renders list of automations', () => {
    const automationsStore = useAutomationsStore()
    automationsStore.automations = [
      { 
        id: 'a1', 
        name: 'Test Auto', 
        enabled: true, 
        triggers: [{ type: 'single', device_id: 'd1', button_id: 'b1' }], 
        actions: [] 
      }
    ]
    const wrapper = mount(Automations)
    expect(wrapper.text()).toContain('Test Auto')
    expect(wrapper.text()).toContain('Button 1')
  })

  it('opens add modal when create button clicked', async () => {
    const automationsStore = useAutomationsStore()
    const wrapper = mount(Automations)
    const createBtn = wrapper.find('button.bg-blue-600') // Create New Automation button
    await createBtn.trigger('click')
    
    expect(automationsStore.editingAutomation).toBeTruthy()
    expect(automationsStore.editingAutomation.id).toBe('')
  })

  it('triggers automation on play click', async () => {
    const automationsStore = useAutomationsStore()
    automationsStore.automations = [
      { 
        id: 'a1', 
        name: 'Test Auto', 
        enabled: true, 
        triggers: [{ type: 'single', device_id: 'd1', button_id: 'b1' }], 
        actions: [] 
      }
    ]
    const wrapper = mount(Automations)
    const playBtn = wrapper.find('button[title="Trigger Automation"]')
    await playBtn.trigger('click')
    
    expect(automationsStore.triggerAutomation).toHaveBeenCalledWith('a1')
  })

  it('calls delete and duplicate functions', async () => {
    const automationsStore = useAutomationsStore()
    automationsStore.automations = [
      { 
        id: 'a1', 
        name: 'Test Auto', 
        enabled: true, 
        triggers: [{ type: 'single', device_id: 'd1', button_id: 'b1' }], 
        actions: [] 
      }
    ]
    const wrapper = mount(Automations)
    
    await wrapper.find('button[title="Duplicate Automation"]').trigger('click')
    expect(automationsStore.duplicateAutomation).toHaveBeenCalledWith('a1')

    await wrapper.find('button[title="Delete Automation (Hold Shift to bypass confirmation)"]').trigger('click')
    expect(automationsStore.deleteAutomation).toHaveBeenCalledWith('a1', expect.anything())
  })

  // --- device_inactivity display ---

  it('renders device_inactivity trigger with timeout', () => {
    const automationsStore = useAutomationsStore()
    automationsStore.automations = [{
      id: 'a1',
      name: 'Inactivity Auto',
      enabled: true,
      triggers: [{ type: 'device_inactivity', device_id: 'd1', timeout_s: 45 }],
      actions: []
    }]
    const wrapper = mount(Automations)
    expect(wrapper.text()).toContain('45s inactivity')
  })

  it('shows countdown bar when inactivity trigger is armed', async () => {
    const automationsStore = useAutomationsStore()
    const settingsStore = useSettingsStore()
    settingsStore.settings = { ...settingsStore.settings, enableUiIndications: true }

    automationsStore.automations = [{
      id: 'a1',
      name: 'Inactivity Auto',
      enabled: true,
      triggers: [{ type: 'device_inactivity', device_id: 'd1', timeout_s: 30 }],
      actions: []
    }]

    // Arm the trigger state (deadline 20s from now)
    const now = Date.now() / 1000
    automationsStore.inactivityStates.set('a1_0', {
      state: 'armed',
      timeout_s: 30,
      armed_at: now - 10  // 10 seconds elapsed → 20s remaining
    })

    const wrapper = mount(Automations)
    await wrapper.vm.$nextTick()

    // Countdown text should be visible
    expect(wrapper.text()).toMatch(/\d+s/)
    // Progress bar should exist
    expect(wrapper.find('.bg-orange-500').exists()).toBe(true)
  })

  it('does not show countdown bar when UI indications are disabled', async () => {
    const automationsStore = useAutomationsStore()
    const settingsStore = useSettingsStore()
    settingsStore.settings = { ...settingsStore.settings, enableUiIndications: false }

    automationsStore.automations = [{
      id: 'a1',
      name: 'Inactivity Auto',
      enabled: true,
      triggers: [{ type: 'device_inactivity', device_id: 'd1', timeout_s: 30 }],
      actions: []
    }]

    const now = Date.now() / 1000
    automationsStore.inactivityStates.set('a1_0', {
      state: 'armed', timeout_s: 30, armed_at: now - 5
    })

    const wrapper = mount(Automations)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.bg-orange-500').exists()).toBe(false)
  })

  it('renders multiple triggers (OR logic)', () => {
    const automationsStore = useAutomationsStore()
    automationsStore.automations = [
      { 
        id: 'a1', 
        name: 'Multi Trigger Auto', 
        enabled: true, 
        triggers: [
            { type: 'single', device_id: 'd1', button_id: 'b1' },
            { type: 'single', device_id: 'd1', button_id: 'b1' }
        ],
        actions: [] 
      }
    ]
    const wrapper = mount(Automations)
    expect(wrapper.text()).toContain('OR')
    // Check if we have multiple trigger blocks (identified by the lightning bolt icon)
    const triggerBlocks = wrapper.findAll('.mdi-lightning-bolt')
    expect(triggerBlocks.length).toBeGreaterThanOrEqual(2)
  })
})