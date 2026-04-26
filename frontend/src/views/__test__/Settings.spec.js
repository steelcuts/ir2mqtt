import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import Settings from '../Settings.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useSettingsStore } from '../../stores/settings'
import { useCommonStore } from '../../stores/common'
import { useBridgeStore } from '../../stores/bridges'

vi.mock('../../components/Switch.vue', () => ({
    default: { template: '<input type="checkbox" />', props: ['modelValue'], emits: ['update:modelValue'] }
}))
vi.mock('../../components/ConfigTransferModal.vue', () => ({
    default: { template: '<div class="mock-transfer-modal" v-if="show"></div>', props: ['show'] }
}))

// Mock API
vi.mock('../../services/api', () => ({
  api: vi.fn(() => Promise.resolve())
}))

describe('Settings View', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const settingsStore = useSettingsStore()
    const commonStore = useCommonStore()
    const bridgeStore = useBridgeStore()

    // Setup initial state
    settingsStore.settings = { enableUiIndications: true, theme: 'theme-dark', logLevel: 'INFO' }
    settingsStore.appMode = 'standalone'
    settingsStore.mqttSettings = { broker: 'test-broker', port: 1883, user: 'user', password: 'pass' }
    settingsStore.testState = { running: false, results: [], progress: 0, total: 0 }
    
    bridgeStore.bridges = [{ id: 'bridge1', name: 'Bridge 1', status: 'online' }, { id: 'bridge2', name: 'Bridge 2', status: 'online' }]
    
    // Mock actions
    settingsStore.fetchMqttSettings = vi.fn()
    settingsStore.saveMqttSettings = vi.fn()
    settingsStore.testMqttSettings = vi.fn().mockResolvedValue({ status: 'ok', message: 'Connected' })
    settingsStore.updateAppMode = vi.fn()
    settingsStore.fetchAppMode = vi.fn()
    settingsStore.factoryReset = vi.fn()
    settingsStore.startLoopbackTest = vi.fn().mockResolvedValue()
    settingsStore.stopLoopbackTest = vi.fn().mockResolvedValue()
    
    commonStore.askConfirm = vi.fn()
  })

  it('fetches mqtt settings on mount', () => {
    const settingsStore = useSettingsStore()
    mount(Settings)
    expect(settingsStore.fetchMqttSettings).toHaveBeenCalled()
  })

  it('renders settings correctly', () => {
    const wrapper = mount(Settings)
    expect(wrapper.text()).toContain('MQTT Connection')
    expect(wrapper.text()).toContain('Operating Mode')
    expect(wrapper.text()).toContain('Theme')
    expect(wrapper.text()).toContain('Danger Zone')
  })

  it('opens config transfer modal', async () => {
    const wrapper = mount(Settings)
    const buttons = wrapper.findAll('button.btn-primary')
    const transferBtn = buttons.find(b => b.text().includes('Configuration Transfer'))
    await transferBtn.trigger('click')
    expect(wrapper.find('.mock-transfer-modal').exists()).toBe(true)
  })

  it('calls factory reset', async () => {
    const settingsStore = useSettingsStore()
    const wrapper = mount(Settings)
    await wrapper.find('button.btn-danger').trigger('click')
    expect(settingsStore.factoryReset).toHaveBeenCalled()
  })

  it('handles mode change with confirmation', async () => {
    const settingsStore = useSettingsStore()
    const commonStore = useCommonStore()
    const wrapper = mount(Settings)
    commonStore.askConfirm.mockResolvedValue(true)
    
    // Find Integration mode button
    const buttons = wrapper.findAll('button')
    const integrationBtn = buttons.find(b => b.text() === 'Home Assistant')
    
    await integrationBtn.trigger('click')
    
    expect(commonStore.askConfirm).toHaveBeenCalled()
    expect(settingsStore.updateAppMode).toHaveBeenCalledWith('home_assistant', 'name')
  })

  it('updates theme setting', async () => {
    const settingsStore = useSettingsStore()
    const wrapper = mount(Settings)
    await wrapper.find('[data-tour-id="theme-selector"]').setValue('theme-gray')
    expect(settingsStore.settings.theme).toBe('theme-gray')
  })

  it('saves mqtt settings', async () => {
    const settingsStore = useSettingsStore()
    const wrapper = mount(Settings)
    const buttons = wrapper.findAll('button')
    const saveMqttBtn = buttons.find(b => b.text().includes('Save & Reload'))
    await saveMqttBtn.trigger('click')
    expect(settingsStore.saveMqttSettings).toHaveBeenCalled()
  })

  it('tests mqtt connection', async () => {
    const settingsStore = useSettingsStore()
    const wrapper = mount(Settings)
    const buttons = wrapper.findAll('button')
    const testMqttBtn = buttons.find(b => b.text().includes('Test Connection'))
    await testMqttBtn.trigger('click')
    expect(settingsStore.testMqttSettings).toHaveBeenCalled()
  })

  it('starts loopback test with selected bridges', async () => {
    const settingsStore = useSettingsStore()
    
    // We need to set the bridge store with capabilities so the computed property works
    const bridgeStore = useBridgeStore()
    bridgeStore.bridges = [
      { id: 'bridge1', name: 'B1', capabilities: ['nec'], status: 'online' },
      { id: 'bridge2', name: 'B2', capabilities: ['nec'], status: 'online' }
    ]

    const wrapper = mount(Settings)
    await wrapper.vm.$nextTick()
    
    // Set the selections
    wrapper.vm.selectedTxBridge = 'bridge1'
    wrapper.vm.selectedRxBridge = 'bridge2'
    // Set protocols directly — the watcher that derives this from commonProtocols is async
    // and unreliable in the test environment; set it explicitly to match bridge capabilities.
    wrapper.vm.selectedProtocols = ['nec']
    await wrapper.vm.$nextTick()

    wrapper.vm.handleStartTest()
    
    expect(settingsStore.startLoopbackTest).toHaveBeenCalledWith('bridge1', 'bridge2', undefined, undefined, 3, 3.0, ['nec'])
  })
})