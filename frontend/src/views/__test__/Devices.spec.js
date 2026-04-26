import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import Devices from '../Devices.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useDeviceStore } from '../../stores/devices'
import { useLearnStore } from '../../stores/learn'
import { useBridgeStore } from '../../stores/bridges'
import { useCommonStore } from '../../stores/common'

// Mock child components
vi.mock('../../components/DeviceModal.vue', () => ({
    default: { template: '<div class="mock-device-modal"></div>', props: ['show'] }
}))
vi.mock('../../components/LearnModal.vue', () => ({
    default: { template: '<div class="mock-learn-modal"></div>', props: ['show'] }
}))

describe('Devices View', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const deviceStore = useDeviceStore()
    const learnStore = useLearnStore()
    const bridgeStore = useBridgeStore()
    const commonStore = useCommonStore()

    deviceStore.devices = []
    deviceStore.fetchDevices = vi.fn()
    deviceStore.triggerButton = vi.fn()
    deviceStore.deleteDevice = vi.fn()
    deviceStore.deleteButton = vi.fn()
    deviceStore.duplicateDevice = vi.fn()
    deviceStore.duplicateButton = vi.fn()
    deviceStore.reorderDevices = vi.fn()
    deviceStore.reorderButtons = vi.fn()
    deviceStore.assignCode = vi.fn()
    
    learnStore.learn = { active: false, received_codes: [] }
    learnStore.startLearn = vi.fn()
    learnStore.cancelLearn = vi.fn()
    
    bridgeStore.bridges = [{id: 'b1', name: 'Bridge 1', status: 'online'}]
    
    commonStore.addFlashMessage = vi.fn()
  })

  it('renders empty state', () => {
    const wrapper = mount(Devices)
    expect(wrapper.text()).toContain('No devices created yet')
  })

  it('renders devices and buttons', async () => {
    const deviceStore = useDeviceStore()
    deviceStore.devices = [
      { 
        id: 'd1', 
        name: 'TV', 
        icon: 'tv', 
        buttons: [
          { id: 'btn1', name: 'Power', icon: 'power', code: { protocol: 'nec' }, is_output: true }
        ] 
      }
    ]
    deviceStore.expandedDevices.add('d1')

    const wrapper = mount(Devices)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('TV')
    expect(wrapper.text()).toContain('Power')
  })

  it('triggers button on click', async () => {
    const deviceStore = useDeviceStore()
    deviceStore.devices = [
      {
        id: 'd1', name: 'TV', buttons: [
          { id: 'btn1', name: 'Power', code: { protocol: 'nec', payload: { address: '0x1', command: '0x2' } }, is_output: true }
        ],
        target_bridges: ['b1']
      }
    ]
    deviceStore.expandedDevices.add('d1')

    const wrapper = mount(Devices)
    await wrapper.vm.$nextTick()
    
    // Find the button trigger (send)
    const sendBtn = wrapper.find('button[title="Send IR Code"]')
    await sendBtn.trigger('click')
    
    expect(deviceStore.triggerButton).toHaveBeenCalledWith('d1', 'btn1')
  })

  it('opens add device modal', async () => {
    const wrapper = mount(Devices)
    await wrapper.find('button.bg-blue-600').trigger('click') // Add New Device button
    expect(wrapper.findComponent({ name: 'DeviceModal' }).props('show')).toBe(true)
  })

  it('calls delete device', async () => {
    const deviceStore = useDeviceStore()
    deviceStore.devices = [{ id: 'd1', name: 'TV', buttons: [] }]
    const wrapper = mount(Devices)
    
    await wrapper.find('button[title="Delete Device (Hold Shift to bypass confirmation)"]').trigger('click')
    expect(deviceStore.deleteDevice).toHaveBeenCalledWith('d1', expect.anything())
  })

  it('toggles MQTT topics visibility and icon', async () => {
    const deviceStore = useDeviceStore()
    deviceStore.devices = [{ id: 'd1', name: 'TV', buttons: [] }]
    const wrapper = mount(Devices)
    await wrapper.vm.$nextTick()

    const toggleBtn = wrapper.find('button[title="Show MQTT Topics"]')
    expect(toggleBtn.exists()).toBe(true)
    expect(toggleBtn.find('i.mdi-chevron-down').exists()).toBe(true)

    // Topics should be hidden initially
    expect(wrapper.find('.bg-gray-800').exists()).toBe(false)
    
    // Click to show
    await toggleBtn.trigger('click')
    await wrapper.vm.$nextTick()
    
    // Topics should be visible
    expect(wrapper.find('div > h4.text-sm.font-semibold.mb-2').text()).toContain('MQTT Topics')
    
    // Button state should update
    const hideBtn = wrapper.find('button[title="Hide MQTT Topics"]')
    expect(hideBtn.exists()).toBe(true)
    expect(hideBtn.find('i.mdi-chevron-up').exists()).toBe(true)
    expect(hideBtn.classes()).toContain('text-blue-400')

    // Click to hide
    await hideBtn.trigger('click')
    await wrapper.vm.$nextTick()

    // Topics should be hidden again
    expect(wrapper.find('div > h4.text-sm.font-semibold.mb-2').exists()).toBe(false)
    expect(wrapper.find('button[title="Show MQTT Topics"]').find('i.mdi-chevron-down').exists()).toBe(true)
  })

  it('reorders buttons via drag and drop', async () => {
    const deviceStore = useDeviceStore()
    deviceStore.devices = [
      { 
        id: 'd1', 
        name: 'TV', 
        buttons: [
          { id: 'b1', name: 'Btn 1' },
          { id: 'b2', name: 'Btn 2' }
        ] 
      }
    ]
    deviceStore.expandedDevices.add('d1')
    
    const wrapper = mount(Devices)
    await wrapper.vm.$nextTick()

    // Find button cards - using a more specific selector
    const buttons = wrapper.findAll('.grid .group.relative:not([data-tour-id="add-button-to-device"])')
    expect(buttons).toHaveLength(2)

    // Mock dataTransfer
    const dataTransfer = {
      effectAllowed: '',
      dropEffect: '',
      setData: vi.fn(),
      getData: vi.fn().mockReturnValue(JSON.stringify({ type: 'button', devId: 'd1', index: 0 })),
      setDragImage: vi.fn()
    }

    // The drag handle is the element with draggable="true"
    const dragHandle1 = buttons[0].find('[draggable="true"]')
    
    // Start drag on first button
    const dragStartEvent = new Event('dragstart', { bubbles: true, cancelable: true })
    Object.defineProperty(dragStartEvent, 'dataTransfer', { value: dataTransfer })
    dragHandle1.element.dispatchEvent(dragStartEvent)
    
    // Dispatch dragover on second button
    const dragOverEvent = new Event('dragover', { bubbles: true, cancelable: true })
    Object.defineProperty(dragOverEvent, 'dataTransfer', { value: dataTransfer })
    buttons[1].element.dispatchEvent(dragOverEvent)

    // Drop on second button (swap)
    const dropEvent = new Event('drop', { bubbles: true, cancelable: true })
    Object.defineProperty(dropEvent, 'dataTransfer', { value: dataTransfer })
    buttons[1].element.dispatchEvent(dropEvent)
    
    expect(deviceStore.reorderButtons).toHaveBeenCalledWith('d1', ['b2', 'b1'])
  })
})