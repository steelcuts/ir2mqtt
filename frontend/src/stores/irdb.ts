import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api } from '../services/api';
import { useCommonStore } from './common';
import type { IRButton, IRCode } from '../types';
import { t } from '../i18n';

export interface IrdbStatus {
    exists: boolean;
    total_remotes?: number;
    total_codes?: number;
    last_updated?: string;
}

export interface IrdbProgress {
    status: string;
    message?: string;
    percent?: number;
    stats?: {
        total_remotes: number;
        total_codes: number;
        total_skipped: number;
        providers?: Record<string, {
            total_rows: number;
            imported: number;
            skipped: number;
            skip_reasons: Record<string, number>;
        }>;
    };
}

export interface IrDbItem {
    name: string;
    path: string;
    type?: 'file' | 'dir';
}

export const useIrdbStore = defineStore('irdb', () => {
    const commonStore = useCommonStore();
    const irdbStatus = ref<IrdbStatus>({ exists: false });
    const irdbProgress = ref<IrdbProgress | null>(null);
    const showIrDbBrowser = ref(false);

    const fetchIrdbStatus = () => api<IrdbStatus>('irdb/status').then(data => irdbStatus.value = data || { exists: false });
    
    const updateIrdb = async (options = { flipper: true, probono: true }) => {
        try {
            await api('irdb/sync', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options) });
        } catch {
            commonStore.addFlashMessage(t('store.irdbUpdateFailed'), 'error');
        }
    };

    const browseIrdb = (path: string) => api<IrDbItem[]>(`irdb/browse?path=${encodeURIComponent(path)}`);
    const loadIrdbFile = (path: string) => api<IRButton[]>(`irdb/file?path=${encodeURIComponent(path)}`);
    const searchIrdb = (query: string) => api<IrDbItem[]>(`irdb/search?q=${encodeURIComponent(query)}`);

    const sendIrCode = (code: IRCode, targets: string[]) => api('irdb/send_code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, target: targets.length > 0 ? targets : null }),
    });

    const handleIrdbProgress = async (msg: IrdbProgress) => {
        irdbProgress.value = msg;
        if (msg.status === 'done') {
            setTimeout(() => { irdbProgress.value = null; }, 2000);
            await fetchIrdbStatus();
            const s = msg.stats;
            const flashMsg = s
                ? t('store.irdbUpdateSuccessStats', {
                    remotes: s.total_remotes.toLocaleString(),
                    codes: s.total_codes.toLocaleString(),
                    skipped: s.total_skipped.toLocaleString(),
                  })
                : t('store.irdbUpdateSuccess');
            commonStore.addFlashMessage(flashMsg, 'success', 8000);
        }
    };

    return { irdbStatus, irdbProgress, showIrDbBrowser, fetchIrdbStatus, updateIrdb, browseIrdb, loadIrdbFile, searchIrdb, sendIrCode, handleIrdbProgress };
});