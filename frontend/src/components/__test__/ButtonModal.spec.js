import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ButtonModal from '../ButtonModal.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useDeviceStore } from '../../stores/devices'
import { useSettingsStore } from '../../stores/settings'

// Mock API
vi.mock('../../services/api', () => ({
  api: vi.fn(() => Promise.resolve())
}))

// Mock child components to simplify testing
vi.mock('../IconPicker.vue', () => ({
  default: { template: '<div class="mock-icon-picker"></div>' }
}))
vi.mock('../IrDbPicker.vue', () => ({
  default: { template: '<div class="mock-irdb-picker"></div>' }
}))

describe('ButtonModal Component', () => {
  const protocols = ['nec', 'raw']
  const mockButton = {
    id: 'b1',
    deviceId: 'd1',
    name: 'Power',
    code: { protocol: 'nec', address: '0x00', command: '0x00' }
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    const deviceStore = useDeviceStore()
    const settingsStore = useSettingsStore()
    deviceStore.devices = [{ id: 'd1', name: 'TV', buttons: [] }]
    settingsStore.appMode = 'standalone'
  })

  it('renders correctly in add mode', async () => {
    const wrapper = mount(ButtonModal, {
      props: { show: true, button: { deviceId: 'd1' }, protocols }
    })
    expect(wrapper.text()).toContain('Add Button')
    expect(wrapper.find('input[placeholder="E.g., Power, Volume Up"]').exists()).toBe(true)
  })

  it('renders correctly in edit mode', async () => {
    const wrapper = mount(ButtonModal, {
      props: { show: true, button: mockButton, protocols }
    })
    expect(wrapper.text()).toContain('Edit Button')
    expect(wrapper.find('input[placeholder="E.g., Power, Volume Up"]').element.value).toBe('Power')
  })

  it('shows tour button in add mode', async () => {
    const wrapper = mount(ButtonModal, {
      props: { show: true, button: { deviceId: 'd1' }, protocols }
    })
    await wrapper.vm.$nextTick()
    const tourButton = wrapper.find('button[title="Start Tour"]')
    expect(tourButton.exists()).toBe(true)
  })

  it('hides tour button in edit mode', async () => {
    const wrapper = mount(ButtonModal, {
      props: { show: true, button: mockButton, protocols }
    })
    await wrapper.vm.$nextTick()
    const tourButton = wrapper.find('button[title="Start Tour"]')
    expect(tourButton.exists()).toBe(false)
  })

  it('validates protocol fields', async () => {
    const wrapper = mount(ButtonModal, {
      props: { show: true, button: { deviceId: 'd1', code: { protocol: '' } }, protocols }
    })
    
    const protocolSelect = wrapper.findAll('select').find(s => s.findAll('option').some(o => o.text() === 'NEC'))
    await protocolSelect.setValue('nec')
    
    expect(wrapper.find('input[placeholder="Address (e.g., 0x04)"]').exists()).toBe(true)
    expect(wrapper.find('button.btn-primary').attributes('disabled')).toBeDefined()
  })
})