import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import SideNav from '../SideNav.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useCommonStore } from '../../stores/common'

describe('SideNav Component', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders nav items', () => {
    const wrapper = mount(SideNav)
    expect(wrapper.text()).toContain('Devices')
    expect(wrapper.text()).toContain('Settings')
  })

  it('highlights active view', async () => {
    const commonStore = useCommonStore()
    commonStore.activeView = 'Settings'
    const wrapper = mount(SideNav)
    await wrapper.vm.$nextTick()
    const activeLink = wrapper.find('[data-tour-id="nav-Settings"]')
    expect(activeLink.classes()).toContain('text-ha-500')
  })
})