import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import Bridges from '../Bridges.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useBridgeStore } from '../../stores/bridges'

describe('Bridges View', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const bridgeStore = useBridgeStore()
    bridgeStore.bridges = []
    bridgeStore.ignoredBridgeIds = []
    bridgeStore.fetchIgnoredBridges = vi.fn().mockResolvedValue(undefined)
    bridgeStore.deleteBridge = vi.fn()
    bridgeStore.updateBridgeProtocols = vi.fn()
  })

  it('renders empty state', () => {
    const wrapper = mount(Bridges)
    expect(wrapper.text()).toContain('No bridges detected')
  })

  it('renders list of bridges', () => {
    const bridgeStore = useBridgeStore()
    bridgeStore.bridges = [
      { id: 'b1', name: 'Living Room', status: 'online', ip: '192.168.1.10', capabilities: ['nec'], receivers: [{id: 'ir_rx_main'}], transmitters: [{id: 'ir_tx_main'}] }
    ]
    const wrapper = mount(Bridges)
    expect(wrapper.text()).toContain('Living Room')
    expect(wrapper.text()).toContain('192.168.1.10')
    expect(wrapper.find('.text-green-400 .mdi-circle').exists()).toBe(true)
    expect(wrapper.text()).toContain('protocols')
  })

  it('handles delete action', async () => {
    const bridgeStore = useBridgeStore()
    bridgeStore.bridges = [{ id: 'b1', name: 'Bridge 1', status: 'online' }]
    const wrapper = mount(Bridges)
    
    await wrapper.find('button[title="Delete Bridge (Hold Shift to bypass confirmation)"]').trigger('click')
    expect(bridgeStore.deleteBridge).toHaveBeenCalledWith('b1', expect.anything())
  })

  it('toggles protocol on click', async () => {
    const bridgeStore = useBridgeStore()
    bridgeStore.bridges = [{ 
        id: 'b1', 
        name: 'Bridge 1', 
        status: 'online', 
        capabilities: ['nec', 'raw'], receivers: [{id: 'ir_rx_main'}], transmitters: [{id: 'ir_tx_main'}], 
        enabled_protocols: ['nec'] 
    }]
    const wrapper = mount(Bridges)
    
    // Expand the protocol panel first
    await wrapper.find('button[title="Protocols"]').trigger('click')

    const chips = wrapper.findAll('span.uppercase.select-none')
    // First chip is NEC (enabled), Second is RAW (disabled)
    
    // Click NEC (disable)
    await chips[0].trigger('click')
    expect(bridgeStore.updateBridgeProtocols).toHaveBeenCalledWith('b1', [])
  })

  it('opens settings modal on edit click', async () => {
    const bridgeStore = useBridgeStore()
    bridgeStore.bridges = [{ id: 'b1', name: 'Bridge 1', status: 'online', settings: { echo_enabled: false } }]
    const wrapper = mount(Bridges)
    
    const editBtn = wrapper.find('button[title="Echo Suppression Settings"]')
    await editBtn.trigger('click')
    
    expect(wrapper.text()).toContain('Echo Suppression')
    expect(wrapper.find('button.btn-primary').text()).toBe('Save')
  })
})