import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import IconPicker from '../IconPicker.vue'

// Mock CSS import
vi.mock('@mdi/font/css/materialdesignicons.css?raw', () => ({
  default: `
    .mdi-home::before { content: "\\F02DC"; }
    .mdi-account::before { content: "\\F0004"; }
    .mdi-cog::before { content: "\\F0141"; }
    .mdi-alert::before { content: "\\F0026"; }
  `
}))

describe('IconPicker Component', () => {
  it('renders input with modelValue', () => {
    const wrapper = mount(IconPicker, {
      props: { modelValue: 'home' }
    })
    expect(wrapper.find('input').element.value).toBe('home')
    expect(wrapper.find('.mdi-home').exists()).toBe(true)
  })

  it('opens modal on click', async () => {
    const wrapper = mount(IconPicker, {
      props: { modelValue: '' },
      global: { stubs: { Teleport: true } }
    })
    await wrapper.find('input').trigger('click')
    expect(wrapper.find('.fixed.inset-0').exists()).toBe(true)
  })

  it('emits update when icon selected', async () => {
    const wrapper = mount(IconPicker)
    await wrapper.vm.selectIcon('home')
    expect(wrapper.emitted()['update:modelValue'][0]).toEqual(['home'])
  })

  it('filters icons based on search query', async () => {
    const wrapper = mount(IconPicker, {
      props: { modelValue: '' },
      global: { stubs: { Teleport: true } }
    })
    await wrapper.find('input').trigger('click') // Open modal
    await flushPromises() // Wait for loadIcons

    const searchInput = wrapper.find('input[placeholder*="Search"]')
    await searchInput.setValue('account')
    
    // Wait for watcher/computed update
    await wrapper.vm.$nextTick()
    
    const icons = wrapper.findAll('.grid button[title]')
    expect(icons.length).toBe(1)
    expect(icons[0].attributes('title')).toBe('account')
  })
})