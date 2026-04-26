import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import FlashMessages from '../FlashMessages.vue'
import { createPinia, setActivePinia } from 'pinia'
import { useCommonStore } from '../../stores/common'

describe('FlashMessages Component', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders nothing when empty', () => {
    const wrapper = mount(FlashMessages)
    expect(wrapper.findAll('div.p-4').length).toBe(0)
  })

  it('renders messages', async () => {
    const commonStore = useCommonStore()
    commonStore.flashMessages = [
      { id: 1, message: 'Success Msg', type: 'success', duration: 4000 },
      { id: 2, message: 'Error Msg', type: 'error', duration: 4000 }
    ]
    const wrapper = mount(FlashMessages, { attachTo: document.body })
    // The component teleports to the body, so we check the document body
    expect(document.body.innerHTML).toContain('Success Msg')
    expect(document.body.innerHTML).toContain('Error Msg')
    expect(document.body.querySelector('.border-green-500')).not.toBeNull()
    expect(document.body.querySelector('.border-red-500')).not.toBeNull()
    wrapper.unmount()
  })
})