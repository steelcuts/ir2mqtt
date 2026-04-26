import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BridgeSelector from '../BridgeSelector.vue'
import TreeView from '../TreeView.vue'

describe('BridgeSelector Component', () => {
  const bridges = [
    { id: 'b1', name: 'Bridge 1', status: 'online' },
    { id: 'b2', name: 'Bridge 2', status: 'offline' }
  ]

  it('renders correctly', () => {
    const wrapper = mount(BridgeSelector, {
      props: { modelValue: [], bridges }
    })
    expect(wrapper.text()).toContain('Target Bridges')
    expect(wrapper.text()).toContain('Bridge 1')
    expect(wrapper.text()).toContain('Bridge 2')
  })

  it('all items unselected when modelValue is empty (broadcast mode)', () => {
    const wrapper = mount(BridgeSelector, {
      props: { modelValue: [], bridges }
    })
    const treeView = wrapper.findComponent(TreeView)
    expect(treeView.props('items').every(i => !i.selected)).toBe(true)
  })

  it('correct bridge item is selected when in modelValue', () => {
    const wrapper = mount(BridgeSelector, {
      props: { modelValue: ['b1'], bridges }
    })
    const items = wrapper.findComponent(TreeView).props('items')
    expect(items[0].selected).toBe(true)
    expect(items[1].selected).toBe(false)
  })

  it('emits update when tree checkbox changed', async () => {
    const wrapper = mount(BridgeSelector, {
      props: { modelValue: [], bridges }
    })
    // First checkbox corresponds to bridge b1
    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[0].setValue(true)
    expect(wrapper.emitted()['update:modelValue']).toBeTruthy()
    expect(wrapper.emitted()['update:modelValue'][0][0]).toContain('b1')
  })
})