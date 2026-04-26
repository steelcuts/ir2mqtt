import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TreeView from '../TreeView.vue'

describe('TreeView Component', () => {
  const items = [
    { id: '1', name: 'Parent', selected: false, isOpen: true, children: [
        { id: '1-1', name: 'Child', selected: false }
    ]},
    { id: '2', name: 'Single', selected: true }
  ]

  it('renders items correctly', () => {
    const wrapper = mount(TreeView, { props: { items } })
    expect(wrapper.text()).toContain('Parent')
    expect(wrapper.text()).toContain('Child')
    expect(wrapper.text()).toContain('Single')
  })

  it('toggles selection recursively', async () => {
    const wrapper = mount(TreeView, { props: { items } })
    const parentCheckbox = wrapper.find('input[type="checkbox"]')
    
    await parentCheckbox.setValue(true)
    
    // Check if event emitted with updated item
    expect(wrapper.emitted()['update:modelValue']).toBeTruthy()
    const emittedItem = wrapper.emitted()['update:modelValue'][0][0]
    expect(emittedItem.selected).toBe(true)
    expect(emittedItem.children[0].selected).toBe(true)
  })

  it('toggles expansion', async () => {
    const wrapper = mount(TreeView, { props: { items } })
    await wrapper.find('.cursor-pointer').trigger('click')
    expect(items[0].isOpen).toBe(false)
  })
})