import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api } from '../services/api';
import { useBridgeStore } from './bridges';
import { useCommonStore } from './common';
import { isSameCode } from '../utils';
import type { IRCode } from '../types';
import { t } from '../i18n';

export interface LearnState {
    active: boolean;
    last_code: IRCode | null;
    received_codes: IRCode[];
    targetBridges: string[];
    activeOn: string[];
    last_code_bridge: string;
    mode: 'simple' | 'smart';
    progress: number;
    target: number;
    smart: boolean;
}

interface LearningStatusMessage {
    active: boolean;
    bridges?: string[];
    mode?: 'simple' | 'smart';
}

interface SmartLearnProgressMessage {
    current: number;
    target: number;
}

interface LearnedCodeMessage {
    code: IRCode;
    bridge: string;
}

export const useLearnStore = defineStore('learn', () => {
    const bridgeStore = useBridgeStore();
    const commonStore = useCommonStore();

    const learn = ref<LearnState>({ 
        active: false, 
        last_code: null, 
        received_codes: [], 
        targetBridges: [], 
        activeOn: [], 
        last_code_bridge: '', 
        mode: 'simple', 
        progress: 0, 
        target: 5, 
        smart: false 
    });

        let learnTimer: ReturnType<typeof setTimeout> | undefined;

    const hasNewCode = computed(() => learn.value.received_codes.length > 0);

    const startLearn = () => {
        if (!bridgeStore.hasOnlineBridges) {
            commonStore.addFlashMessage(t('store.learnNoBridges'), "error");
            return;
        }
        learn.value.received_codes = [];
        learn.value.last_code = null;
        learn.value.progress = 0;
        const bridgeParams = learn.value.targetBridges.length > 0 
            ? learn.value.targetBridges.map(b => `bridges=${encodeURIComponent(b)}`).join('&') 
            : 'bridges=any';
        api(`learn?${bridgeParams}&smart=${learn.value.smart}`, { method: 'POST' });
    };

    const cancelLearn = () => api('learn/cancel', { method: 'POST' });

    const consumeLearnedCode = (savedCode: IRCode) => {
        if (!savedCode || !learn.value.last_code) return;
        
        const last = learn.value.last_code;
        
        if (isSameCode(savedCode, last)) {
            const codes = learn.value.received_codes;
            const index = codes.findIndex(c => isSameCode(c, last));
            if (index > -1) {
                codes.splice(index, 1);
                if (codes.length > 0) {
                    learn.value.last_code = codes[Math.min(index, codes.length - 1)];
                } else {
                    learn.value.last_code = null;
                    learn.value.last_code_bridge = '';
                }
            }
        }
    };

    const handleLearningStatus = (msg: LearningStatusMessage) => {
        learn.value.active = msg.active;
        learn.value.activeOn = msg.bridges || [];
        learn.value.mode = msg.mode || 'simple';
        if (msg.active && learn.value.mode === 'smart') {
            learn.value.progress = 0;
        }
        if (!msg.active) {
            if (learnTimer) {
                clearTimeout(learnTimer);
                learnTimer = undefined;
            }
            if (learn.value.received_codes.length === 0) {
                learn.value.last_code = null;
                learn.value.last_code_bridge = '';
            }
        }
    };

    const handleSmartLearnProgress = (msg: SmartLearnProgressMessage) => {
        learn.value.progress = msg.current;
        learn.value.target = msg.target;
    };

    const handleLearnedCode = (msg: LearnedCodeMessage) => {
        learn.value.received_codes.push(msg.code);
        if (!learn.value.last_code) {
            learn.value.last_code = msg.code;
        }
        learn.value.last_code_bridge = msg.bridge;
        
        if (learnTimer) {
            clearTimeout(learnTimer);
        }
        
        learnTimer = setTimeout(() => {
            cancelLearn();
            learnTimer = undefined;
        }, 300);
    };

    return { learn, hasNewCode, startLearn, cancelLearn, consumeLearnedCode, handleLearningStatus, handleSmartLearnProgress, handleLearnedCode };
});