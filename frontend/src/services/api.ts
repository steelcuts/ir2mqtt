import { useCommonStore } from '../stores/common';

const basePath = window.location.pathname.replace(/\/$/, '');

export const api = async <T = unknown>(path: string, options?: RequestInit): Promise<T | null> => {
    const commonStore = useCommonStore();
    
    const response = await fetch(`${basePath}/api/${path}`, options);
    if (!response.ok) {
        let errorDetail = response.statusText;
        try {
            const errJson = await response.json();
            if (errJson.detail) errorDetail = errJson.detail;
        } catch { /* empty */ }
        
        if (response.status === 409) {
                const error = new Error(errorDetail) as Error & { status: number };
                error.status = 409;
                throw error;
        }

        commonStore.addFlashMessage(`API Error: ${errorDetail}`, 'error');
        throw new Error(errorDetail);
    }
    return response.status === 200 ? response.json() : null;
};