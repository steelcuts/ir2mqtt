import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ActionList from '../ActionList.vue'

describe('ActionList Component', () => {
  const devices = [
    { id: 'd1', name: 'Device 1', buttons: [{ id: 'b1', name: 'Button 1' }] },
    { id: 'd2', name: 'Device 2', buttons: [{ id: 'b2', name: 'Button 2' }] },
  ]

  let actions

  beforeEach(() => {
    actions = [
      { type: 'delay', delay_ms: 1000 },
      { type: 'ir_send', device_id: 'd1', button_id: 'b1' },
      { type: 'event', event_name: 'test_event' },
    ]
  })

  it('renders correctly', () => {
    const wrapper = mount(ActionList, {
      props: { actions, devices, appMode: 'standalone' }
    })
    expect(wrapper.text()).toContain('Delay')
    expect(wrapper.text()).toContain('Send IR')
    expect(wrapper.text()).toContain('Button 1')
    expect(wrapper.find('option[value="d1"]').text()).toBe('Device 1')
    expect(wrapper.text()).toContain('Fire Event')
    expect(wrapper.find('input[placeholder="event_name"]').element.value).toBe('test_event')
  })

  it('renders HA event correctly', () => {
    const wrapper = mount(ActionList, {
      props: { actions: [{ type: 'event', event_name: 'ha_event' }], devices, appMode: 'home_assistant' }
    })
    expect(wrapper.text()).toContain('Fire HA Event')
  })

  it('emits remove-action event', async () => {
    const wrapper = mount(ActionList, {
      props: { actions, devices, appMode: 'standalone' }
    })
    const removeBtns = wrapper.findAll('button').filter(b => b.find('.mdi-close').exists())
    await removeBtns[0].trigger('click')
    expect(wrapper.emitted('remove-action')).toBeTruthy()
    expect(wrapper.emitted('remove-action')[0]).toEqual([0])
  })

  it('emits add-action event', async () => {
    const wrapper = mount(ActionList, {
      props: { actions, devices, appMode: 'standalone' }
    })
    const buttons = wrapper.findAll('button.btn-secondary')
    
    await buttons[0].trigger('click')
    expect(wrapper.emitted('add-action')[0]).toEqual(['ir_send'])

    await buttons[1].trigger('click')
    expect(wrapper.emitted('add-action')[1]).toEqual(['delay'])

    await buttons[2].trigger('click')
    expect(wrapper.emitted('add-action')[2]).toEqual(['event'])
  })

  it('emits action-device-change event', async () => {
    const wrapper = mount(ActionList, {
      props: { actions, devices, appMode: 'standalone' }
    })
    const deviceSelect = wrapper.findAll('select')[0]
    
    await deviceSelect.setValue('d2')
    expect(wrapper.emitted('action-device-change')).toBeTruthy()
    expect(wrapper.emitted('action-device-change')[0][0]).toEqual(actions[1])
  })

  it('updates button list when device changes', async () => {
    const wrapper = mount(ActionList, {
      props: { actions, devices, appMode: 'standalone' }
    })
    const deviceSelect = wrapper.findAll('select')[0]
    const buttonSelect = wrapper.findAll('select')[1]
    
    expect(buttonSelect.text()).toContain('Button 1')
    
    await deviceSelect.setValue('d2')
    
    expect(buttonSelect.text()).toContain('Button 2')
  })

  it('emits drag events', async () => {
    const wrapper = mount(ActionList, {
      props: { actions, devices, appMode: 'standalone' }
    })
    const draggableItem = wrapper.find('.cursor-move')
    
    await draggableItem.trigger('dragstart')
    expect(wrapper.emitted('drag-start')).toBeTruthy()
    expect(wrapper.emitted('drag-start')[0]).toEqual([expect.anything(), 0, 'action'])

    await draggableItem.trigger('dragover')
    expect(wrapper.emitted('drag-over')).toBeTruthy()
    expect(wrapper.emitted('drag-over')[0]).toEqual([0, 'action'])

    await draggableItem.trigger('drop')
    expect(wrapper.emitted('drop')).toBeTruthy()
    expect(wrapper.emitted('drop')[0]).toEqual([expect.anything(), 0, 'action'])

    await draggableItem.trigger('dragend')
    expect(wrapper.emitted('drag-end')).toBeTruthy()
  })

  it('applies drag styles', async () => {
    const wrapper = mount(ActionList, {
      props: { 
        actions, 
        devices, 
        appMode: 'standalone',
        draggingItem: { type: 'action', index: 0 },
        dragOverItem: { type: 'action', index: 1 }
      }
    })
    
    const items = wrapper.findAll('.cursor-move')
    expect(items[0].classes()).toContain('opacity-40')
    expect(items[1].classes()).toContain('border-b-4')
    expect(items[1].classes()).toContain('border-b-blue-500')
  })
})