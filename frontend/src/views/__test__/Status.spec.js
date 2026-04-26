import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import Status from '../Status.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useCommonStore } from '../../stores/common'
import { useDeviceStore } from '../../stores/devices'
import { useIrdbStore } from '../../stores/irdb'

describe('Status View', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const commonStore = useCommonStore()
    const deviceStore = useDeviceStore()
    const irdbStore = useIrdbStore()

    commonStore.logs = []
    commonStore.mqttConnected = true
    commonStore.clearLogs = vi.fn()
    deviceStore.devices = []
    irdbStore.irdbStatus = { exists: true, total_remotes: 10, total_codes: 100, last_updated: new Date().toISOString() }
    irdbStore.fetchIrdbStatus = vi.fn()
  })

  it('fetches IRDB status on mount', () => {
    const irdbStore = useIrdbStore()
    mount(Status)
    expect(irdbStore.fetchIrdbStatus).toHaveBeenCalled()
  })

  it('renders status cards', () => {
    const wrapper = mount(Status)
    expect(wrapper.text()).toContain('MQTT')
    expect(wrapper.text()).toContain('Connected')
    expect(wrapper.text()).toContain('IRDB')
    expect(wrapper.text()).toContain('Loaded')
  })

  it('renders logs', () => {
    const commonStore = useCommonStore()
    commonStore.logs = [
      { level: 'INFO', message: 'Log 1', timestamp: new Date() },
      { level: 'WARNING', message: 'Log 2', timestamp: new Date() }
    ]
    const wrapper = mount(Status)
    expect(wrapper.text()).toContain('Log 1')
    expect(wrapper.text()).toContain('Log 2')
  })

  it('clears logs', async () => {
    const commonStore = useCommonStore()
    commonStore.logs = ['Log 1']
    const wrapper = mount(Status)
    
    const clearBtn = wrapper.findAll('button').find(b => b.text().includes('Clear'))
    await clearBtn.trigger('click')
    expect(commonStore.clearLogs).toHaveBeenCalled()
  })
})