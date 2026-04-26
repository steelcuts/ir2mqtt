import type { IRButton, IRCode, IRCodePayload, ReceivedCode } from './types';

export const sanitizeNameForImport = (name: string): string => {
    if (!name) return '';
    return name.trim()
        .replace(/\+/g, 'Plus')
        .replace(/#/g, 'Sharp')
        .replace(/[/\\]/g, '_');
};

export const sanitizeTopicParam = (name: string): string => {
    if (!name) return '';
    return name.toLowerCase()
        .replace(/\+/g, 'plus')
        .replace(/#/g, 'sharp')
        .replace(new RegExp('[ /\\\\]', 'g'), '_');
};

export const isButtonValid = (btn: IRButton | null | undefined): boolean => {
    if (!btn || !btn.code || Object.keys(btn.code).length === 0) {
        return false;
    }
    const { payload } = btn.code;
    return !!payload && Object.values(payload).some(v => v !== '' && v !== null && v !== undefined);
};

export const isSameCode = (c1: IRCode | null | undefined, c2: IRCode | null | undefined): boolean => {
    if (!c1 || !c2) return false;
    if (c1.protocol.toLowerCase() !== c2.protocol.toLowerCase()) return false;
    if (c1.protocol === 'raw') {
        return JSON.stringify(c1.payload?.timings) === JSON.stringify(c2.payload?.timings);
    }
    const p1 = c1.payload ?? {};
    const p2 = c2.payload ?? {};
    const keys = Object.keys(p2).filter(k => p2[k] !== null && p2[k] !== '' && p2[k] !== undefined);
    return keys.length > 0 && keys.every(k => String(p1[k] ?? '').toLowerCase() === String(p2[k]).toLowerCase());
};

export const PROTOCOL_COLORS: Record<string, string> = {
    // Blue — mainstream consumer electronics
    nec:          'text-blue-500 border-blue-600',
    nec2:         'text-blue-500 border-blue-600',
    samsung:      'text-blue-500 border-blue-600',
    samsung36:    'text-blue-500 border-blue-600',
    lg:           'text-blue-500 border-blue-600',
    panasonic:    'text-blue-500 border-blue-600',
    aeha:         'text-blue-500 border-blue-600',
    symphony:     'text-blue-500 border-blue-600',
    toshiba_ac:   'text-blue-500 border-blue-600',
    mirage:       'text-blue-500 border-blue-600',
    // Red — Sony
    sony:         'text-red-400 border-red-400',
    pioneer:      'text-red-400 border-red-400',
    // Yellow — RC family, JVC
    rc5:          'text-yellow-400 border-yellow-400',
    rc6:          'text-yellow-400 border-yellow-400',
    jvc:          'text-yellow-400 border-yellow-400',
    // Cyan — smart home appliances
    dyson:        'text-cyan-400 border-cyan-400',
    toto:         'text-cyan-400 border-cyan-400',
    roomba:       'text-cyan-400 border-cyan-400',
    // Amber — building/blinds/heating/garage
    dooya:        'text-amber-400 border-amber-400',
    drayton:      'text-amber-400 border-amber-400',
    keeloq:       'text-amber-400 border-amber-400',
    nexa:         'text-amber-400 border-amber-400',
    // Indigo — satellite / door / access
    canalsat:     'text-indigo-400 border-indigo-400',
    canalsat_ld:  'text-indigo-400 border-indigo-400',
    abbwelcome:   'text-indigo-400 border-indigo-400',
    byronsx:      'text-indigo-400 border-indigo-400',
    // Purple — specialty/entertainment
    beo4:         'text-purple-400 border-purple-400',
    magiquest:    'text-purple-400 border-purple-400',
    // Gray — generic / raw
    pronto:       'text-gray-400 border-gray-600',
    raw:          'text-gray-400 border-gray-600',
    rc_switch:    'text-gray-400 border-gray-600',
    gobox:        'text-gray-400 border-gray-600',
    // Green — other
    dish:         'text-green-400 border-green-400',
    coolix:       'text-green-400 border-green-400',
    midea:        'text-green-400 border-green-400',
    haier:        'text-green-400 border-green-400',
};

export const getProtocolColor = (protocol?: string | null): string => {
    if (!protocol) return 'text-green-400 border-green-400';
    return PROTOCOL_COLORS[protocol.toLowerCase()] ?? 'text-green-400 border-green-400';
};

export interface CodeField { label: string; value: string }

const resolvePayload = (code: IRCode | ReceivedCode): IRCodePayload => code.payload ?? {};

export const getCodeFields = (code: IRCode | ReceivedCode | null | undefined): CodeField[] => {
    if (!code) return [];
    const proto = code.protocol?.toLowerCase() ?? '';
    const p = resolvePayload(code);
    const fields: CodeField[] = [];

    const hex = (key: string) => { if (p[key] != null) fields.push({ label: key, value: String(p[key]) }); };

    if (['nec', 'nec2', 'samsung36', 'panasonic', 'rc5', 'rc6', 'dish', 'byronsx',
         'drayton', 'dyson', 'abbwelcome', 'sharp', 'sanyo', 'rca'].includes(proto)) {
        hex('address'); hex('command');
    } else if (['samsung', 'sony', 'lg', 'symphony', 'toshiba', 'whynter'].includes(proto)) {
        hex('data');
        if (p.nbits != null) fields.push({ label: 'bits', value: String(p.nbits) });
    } else if (proto === 'jvc' || proto === 'gobox') {
        hex('data');
    } else if (['midea', 'haier', 'mirage'].includes(proto)) {
        if (p.data != null) {
            const len = Array.isArray(p.data) ? p.data.length : String(p.data).split(',').length;
            fields.push({ label: 'bytes', value: String(len) });
        }
    } else if (proto === 'aeha') {
        hex('address');
        if (p.data != null) {
            const len = Array.isArray(p.data) ? p.data.length : String(p.data).split(',').length;
            fields.push({ label: 'bytes', value: String(len) });
        }
    } else if (['pioneer', 'toshiba_ac'].includes(proto)) {
        hex('rc_code_1'); hex('rc_code_2');
    } else if (proto === 'coolix') {
        hex('first'); hex('second');
    } else if (proto === 'beo4') {
        hex('command'); if (p.source != null) hex('source');
    } else if (proto === 'canalsat' || proto === 'canalsat_ld') {
        hex('device'); hex('command'); if (p.address != null) hex('address');
    } else if (proto === 'dooya') {
        hex('address'); hex('command'); if (p.channel != null) hex('channel');
    } else if (proto === 'keeloq') {
        hex('encrypted'); hex('serial');
    } else if (proto === 'magiquest') {
        hex('id'); hex('magnitude');
    } else if (proto === 'nexa') {
        hex('device'); hex('group'); hex('state'); hex('channel'); hex('level');
    } else if (proto === 'rc_switch') {
        hex('code');
        if (p.protocol != null) fields.push({ label: 'proto', value: String(p.protocol) });
    } else if (proto === 'roomba' || proto === 'toto') {
        hex('command');
    } else if (proto === 'pronto') {
        if (p.data) {
            const d = typeof p.data === 'string' ? p.data : '';
            fields.push({ label: 'words', value: String(d.trim().split(/\s+/).length) });
        }
    } else if (proto === 'raw') {
        const t = p.timings ?? p.data;
        if (t != null) {
            const len = Array.isArray(t) ? t.length : String(t).split(',').length;
            fields.push({ label: 'pulses', value: String(len) });
        }
    } else {
        // Fallback — show whatever is in payload
        hex('address'); hex('command'); hex('data');
        if (p.nbits != null) fields.push({ label: 'bits', value: String(p.nbits) });
        hex('rc_code_1'); hex('rc_code_2'); hex('first'); hex('second');
    }

    return fields;
};

export const formatCodeDetailsString = (code: IRCode | ReceivedCode | null | undefined): string => {
    if (!code) return 'No code';
    const fields = getCodeFields(code);
    const proto = `[${code.protocol ? code.protocol.toUpperCase() : 'UNKNOWN'}]`;
    if (fields.length === 0) return proto;
    return `${proto} ${fields.map(f => `${f.label}: ${f.value}`).join(', ')}`;
};
