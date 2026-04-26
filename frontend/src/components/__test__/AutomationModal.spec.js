import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AutomationModal from '../AutomationModal.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useDeviceStore } from '../../stores/devices'
import { useAutomationsStore } from '../../stores/automations'
import { useSettingsStore } from '../../stores/settings'
import { api } from '../../services/api'

// Mock API
vi.mock('../../services/api', () => ({
  api: vi.fn(() => Promise.resolve())
}))

describe('AutomationModal Component', () => {
  const mockDevices = [
    { id: 'd1', name: 'Device 1', buttons: [{ id: 'b1', name: 'Button 1' }] }
  ]

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const deviceStore = useDeviceStore()
    const automationsStore = useAutomationsStore()
    const settingsStore = useSettingsStore()

    deviceStore.devices = mockDevices
    automationsStore.automations = []
    settingsStore.appMode = 'standalone'
  })

  it('renders correctly when shown', async () => {
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation: { name: '', actions: [] } }
    })
    expect(wrapper.text()).toContain('Create Automation')
    expect(wrapper.find('input[placeholder="E.g., Movie Night"]').exists()).toBe(true)
  })

  it('validates required fields', async () => {
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation: { name: '', actions: [] } }
    })
    
    // Initially invalid because name and actions are empty
    expect(wrapper.find('button.btn-primary').attributes('disabled')).toBeDefined()
    
    // Set name
    await wrapper.find('input[placeholder="E.g., Movie Night"]').setValue('My Auto')
    
    // Still invalid (no actions, no trigger)
    expect(wrapper.find('button.btn-primary').attributes('disabled')).toBeDefined()
  })

  it('populates fields when editing', async () => {
    const automation = {
      id: 'a1',
      name: 'Test Auto',
      triggers: [{ type: 'single', device_id: 'd1', button_id: 'b1' }],
      actions: [{ type: 'delay', delay_ms: 500 }]
    }
    
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation }
    })

    expect(wrapper.text()).toContain('Edit Automation')
    expect(wrapper.find('input[placeholder="E.g., Movie Night"]').element.value).toBe('Test Auto')
  })

  it('shows tour button in create mode', async () => {
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation: { name: '', actions: [] } }
    })
    await wrapper.vm.$nextTick()
    const tourButton = wrapper.find('button[title="Start Tour"]')
    expect(tourButton.exists()).toBe(true)
  })

  it('hides tour button in edit mode', async () => {
    const automation = {
      id: 'a1',
      name: 'Test Auto',
      triggers: [{ type: 'single', device_id: 'd1', button_id: 'b1' }],
      actions: [{ type: 'delay', delay_ms: 500 }]
    }
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation }
    })
    await wrapper.vm.$nextTick()
    const tourButton = wrapper.find('button[title="Start Tour"]')
    expect(tourButton.exists()).toBe(false)
  })

  it('adds and removes actions', async () => {
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation: { name: 'Test', actions: [] } }
    })
    
    // Add Delay Action
    const addDelayBtn = wrapper.findAll('button').find(b => b.text().includes('Add Delay'))
    await addDelayBtn.trigger('click')
    
    expect(wrapper.text()).toContain('Delay')
    expect(wrapper.vm.localAuto.actions).toHaveLength(1)
    expect(wrapper.vm.localAuto.actions[0].type).toBe('delay')

    // Remove Action
    const removeBtn = wrapper.find('button .mdi-close').element.parentElement
    await removeBtn.click()
    
    expect(wrapper.vm.localAuto.actions).toHaveLength(0)
  })

  it('saves automation successfully', async () => {
    const automationsStore = useAutomationsStore()
    const fetchSpy = vi.spyOn(automationsStore, 'fetchAutomations')
    
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation: { name: '', actions: [] } }
    })

    // Fill valid data
    await wrapper.find('input[placeholder="E.g., Movie Night"]').setValue('New Auto')
    
    // Add trigger (default is single)
    const addTriggerBtn = wrapper.findAll('button').find(b => b.text().includes('Add Trigger'))
    await addTriggerBtn.trigger('click')
    
    // Select device/button for trigger
    const triggerSelects = wrapper.findAll('select')
    await triggerSelects[1].setValue('d1') // Device
    await triggerSelects[2].setValue('b1') // Button

    // Add action
    const addDelayBtn = wrapper.findAll('button').find(b => b.text().includes('Add Delay'))
    await addDelayBtn.trigger('click')

    // Click Save
    const saveBtn = wrapper.find('button[data-tour-id="automation-save-button"]')
    expect(saveBtn.attributes('disabled')).toBeUndefined()
    
    await saveBtn.trigger('click')
    await flushPromises()

    expect(api).toHaveBeenCalledWith('automations', expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('New Auto')
    }))
    expect(fetchSpy).toHaveBeenCalled()
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('manages triggers and sequences', async () => {
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation: { name: 'Test', actions: [], triggers: [] } }
    })

    // Add Trigger
    const addTriggerBtn = wrapper.findAll('button').find(b => b.text().includes('Add Trigger'))
    await addTriggerBtn.trigger('click')
    expect(wrapper.vm.localAuto.triggers).toHaveLength(1)

    // Change to Sequence
    const triggerSelect = wrapper.find('select')
    await triggerSelect.setValue('sequence')
    expect(wrapper.vm.localAuto.triggers[0].type).toBe('sequence')

    // Add Sequence Step
    const addStepBtn = wrapper.findAll('button').find(b => b.text().includes('Add Step'))
    await addStepBtn.trigger('click')
    expect(wrapper.vm.localAuto.triggers[0].sequence).toHaveLength(1)

    // Remove Trigger
    const removeTriggerBtn = wrapper.find('.bg-gray-800\\/50 > button')
    await removeTriggerBtn.trigger('click')
    expect(wrapper.vm.localAuto.triggers).toHaveLength(0)
  })

  // --- device_inactivity trigger ---

  it('switches trigger type to device_inactivity and fills defaults', async () => {
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation: { name: 'Test', actions: [], triggers: [] } }
    })

    // Add a trigger (defaults to 'single')
    const addTriggerBtn = wrapper.findAll('button').find(b => b.text().includes('Add Trigger'))
    await addTriggerBtn.trigger('click')
    expect(wrapper.vm.localAuto.triggers[0].type).toBe('single')

    // Change type to device_inactivity
    const typeSelect = wrapper.find('select')
    await typeSelect.setValue('device_inactivity')

    const trigger = wrapper.vm.localAuto.triggers[0]
    expect(trigger.type).toBe('device_inactivity')
    expect(trigger.timeout_s).toBe(30)
    expect(trigger.watch_mode).toBe('received')
    expect(trigger.rearm_mode).toBe('always')
  })

  it('device_inactivity: validation fails without device_id', async () => {
    const wrapper = mount(AutomationModal, {
      props: {
        show: true,
        automation: {
          name: 'Test',
          actions: [{ type: 'delay', delay_ms: 100 }],
          triggers: [{
            type: 'device_inactivity',
            device_id: '',
            timeout_s: 30,
            watch_mode: 'received',
            rearm_mode: 'always'
          }]
        }
      }
    })

    // Save button must be disabled when device_id is missing
    const saveBtn = wrapper.find('button[data-tour-id="automation-save-button"]')
    expect(saveBtn.attributes('disabled')).toBeDefined()
  })

  it('device_inactivity: validation fails when timeout_s is zero', async () => {
    const wrapper = mount(AutomationModal, {
      props: {
        show: true,
        automation: {
          name: 'Test',
          actions: [{ type: 'delay', delay_ms: 100 }],
          triggers: [{
            type: 'device_inactivity',
            device_id: 'd1',
            timeout_s: 0,
            watch_mode: 'received',
            rearm_mode: 'always'
          }]
        }
      }
    })

    const saveBtn = wrapper.find('button[data-tour-id="automation-save-button"]')
    expect(saveBtn.attributes('disabled')).toBeDefined()
  })

  it('device_inactivity: save button enabled with valid trigger', async () => {
    const wrapper = mount(AutomationModal, {
      props: {
        show: true,
        automation: {
          name: 'Test',
          actions: [{ type: 'delay', delay_ms: 100 }],
          triggers: [{
            type: 'device_inactivity',
            device_id: 'd1',
            timeout_s: 30,
            watch_mode: 'received',
            rearm_mode: 'always'
          }]
        }
      }
    })

    const saveBtn = wrapper.find('button[data-tour-id="automation-save-button"]')
    expect(saveBtn.attributes('disabled')).toBeUndefined()
  })

  it('handles drag and drop reordering', async () => {
    const automation = {
      id: 'a1',
      name: 'Test',
      triggers: [],
      actions: [
        { type: 'delay', delay_ms: 100 },
        { type: 'delay', delay_ms: 200 }
      ]
    }
    const wrapper = mount(AutomationModal, {
      props: { show: true, automation }
    })

    // Mock dataTransfer
    const dataTransfer = {
      effectAllowed: '',
      dropEffect: '',
      setData: vi.fn(),
      getData: vi.fn().mockReturnValue(JSON.stringify({ index: 0, type: 'action' }))
    }

    // Simulate drag start via ActionList event
    const actionList = wrapper.findComponent({ name: 'ActionList' })
    
    // Start drag on first item
    actionList.vm.$emit('drag-start', { dataTransfer }, 0, 'action')
    expect(wrapper.vm.draggingItem).toEqual({ index: 0, type: 'action' })
    
    // Drop on second item (swap)
    actionList.vm.$emit('drop', { dataTransfer }, 1, 'action')
    
    // Verify swap
    expect(wrapper.vm.localAuto.actions[0].delay_ms).toBe(200)
    expect(wrapper.vm.localAuto.actions[1].delay_ms).toBe(100)
  })
})