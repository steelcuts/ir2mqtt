import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ConfirmModal from '../ConfirmModal.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useCommonStore } from '../../stores/common'

describe('ConfirmModal Component', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('does not render when show is false', () => {
    const wrapper = mount(ConfirmModal)
    expect(wrapper.find('.fixed').exists()).toBe(false)
  })

  it('renders content when show is true', async () => {
    const commonStore = useCommonStore()
    commonStore.confirmation.show = true
    commonStore.confirmation.title = 'Test Title'
    commonStore.confirmation.message = 'Test Message'
    
    const wrapper = mount(ConfirmModal)
    expect(wrapper.find('.fixed').exists()).toBe(true)
    expect(wrapper.text()).toContain('Test Title')
    expect(wrapper.text()).toContain('Test Message')
  })

  it('calls resolve on button click', async () => {
    const commonStore = useCommonStore()
    const resolveSpy = vi.fn()
    commonStore.confirmation.show = true
    commonStore.confirmation.resolve = resolveSpy

    const wrapper = mount(ConfirmModal)
    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click') // Confirm button
    
    expect(resolveSpy).toHaveBeenCalledWith(true)
    expect(commonStore.confirmation.show).toBe(false)
  })
})