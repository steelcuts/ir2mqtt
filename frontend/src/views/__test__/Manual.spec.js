import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import Manual from '../Manual.vue';

describe('Manual.vue', () => {
    it('renders the external documentation link', () => {
        const wrapper = mount(Manual);
        expect(wrapper.find('a').attributes('href')).toBe('https://github.com/steelcuts/ir2mqtt/tree/main/docs');
    });
});
