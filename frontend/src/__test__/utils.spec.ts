import { describe, it, expect } from 'vitest';
import { sanitizeNameForImport, sanitizeTopicParam, isButtonValid, isSameCode } from '../utils';
import type { IRButton } from '../types';

describe('utils.ts', () => {
  describe('sanitizeNameForImport', () => {
    it('sanitizes names correctly', () => {
      expect(sanitizeNameForImport('TV+Living')).toBe('TVPlusLiving');
      expect(sanitizeNameForImport('Channel#1')).toBe('ChannelSharp1');
      expect(sanitizeNameForImport('AC/DC')).toBe('AC_DC');
      expect(sanitizeNameForImport('')).toBe('');
    });
  });

  describe('sanitizeTopicParam', () => {
    it('sanitizes topic params correctly', () => {
      expect(sanitizeTopicParam('Living Room')).toBe('living_room');
      expect(sanitizeTopicParam('TV+')).toBe('tvplus');
      expect(sanitizeTopicParam('Channel#1')).toBe('channelsharp1');
      expect(sanitizeTopicParam('')).toBe('');
    });
  });

  describe('isButtonValid', () => {
    it('returns false for null/undefined', () => {
      expect(isButtonValid(null)).toBe(false);
      expect(isButtonValid(undefined)).toBe(false);
    });

    it('returns false for empty code', () => {
      expect(isButtonValid({ code: {} } as unknown as IRButton)).toBe(false);
      expect(isButtonValid({ code: { protocol: '' } } as unknown as IRButton)).toBe(false);
    });

    it('returns true for valid code', () => {
      expect(isButtonValid({ code: { protocol: 'nec', payload: { address: '0x01' } } } as unknown as IRButton)).toBe(true);
    });
  });

  describe('isSameCode', () => {
    it('returns false if protocols differ', () => {
      const c1 = { protocol: 'nec', payload: { address: '0x1' } };
      const c2 = { protocol: 'sony', payload: { address: '0x1' } };
      expect(isSameCode(c1, c2)).toBe(false);
    });

    it('returns true for identical codes ignoring case', () => {
      const c1 = { protocol: 'nec', payload: { address: '0x1A' } };
      const c2 = { protocol: 'NEC', payload: { address: '0x1a' } };
      expect(isSameCode(c1, c2)).toBe(true);
    });

    it('handles raw data comparison', () => {
      const c1 = { protocol: 'raw', payload: { timings: [100, 200] } };
      const c2 = { protocol: 'raw', payload: { timings: [100, 200] } };
      expect(isSameCode(c1, c2)).toBe(true);
    });
  });
});