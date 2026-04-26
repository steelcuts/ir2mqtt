import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Switch from '../Switch.vue'

describe('Switch Component', () => {
  it('renders properly in unchecked state', () => {
    const wrapper = mount(Switch, { props: { modelValue: false } })
    expect(wrapper.find('input').element.checked).toBe(false)
  })

  it('renders properly in checked state', () => {
    const wrapper = mount(Switch, { props: { modelValue: true } })
    expect(wrapper.find('input').element.checked).toBe(true)
  })

  it('emits update:modelValue event when clicked', async () => {
    const wrapper = mount(Switch, { props: { modelValue: false } })
    await wrapper.find('input').setValue(true)
    expect(wrapper.emitted()['update:modelValue'][0]).toEqual([true])
  })
})