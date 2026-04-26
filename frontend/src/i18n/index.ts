import { ref, reactive } from 'vue';
import en from './en';


type LocaleMessages = typeof en;
const locales: Record<string, LocaleMessages> = reactive({ en });

export type Locale = 'en' | 'de' | 'es' | 'fr' | 'it' | 'ru' | 'en_UK' | 'en_AU';
export const availableLocales: Locale[] = ['en', 'de', 'es', 'fr', 'it', 'ru', 'en_UK', 'en_AU'];

// Explicit loader map so Vite can statically analyze and chunk the dynamic imports
// without throwing "cannot import their own directory" warnings.
const localeLoaders: Record<string, () => Promise<{ default: LocaleMessages }>> = {
    de: () => import('./de.ts'),
    es: () => import('./es.ts'),
    fr: () => import('./fr.ts'),
    it: () => import('./it.ts'),
    ru: () => import('./ru.ts'),
    en_UK: () => import('./en_UK.ts'),
    en_AU: () => import('./en_AU.ts'),
};

// Module-level reactive ref — shared across all components and stores.
// Accessing currentLocale.value inside t() registers a reactive dependency,
// so any template or computed that calls t() re-renders on language change.
export const currentLocale = ref<Locale>(
    'en' // Start synchronously with English
);

function resolve(obj: Record<string, unknown>, keys: string[]): unknown {
    let cur: unknown = obj;
    for (const key of keys) {
        if (cur && typeof cur === 'object') {
            cur = (cur as Record<string, unknown>)[key];
        } else {
            return undefined;
        }
    }
    return cur;
}

export function t(key: string, params?: Record<string, string | number>): string {
    const keys = key.split('.');
    // Accessing currentLocale.value here registers a reactive dependency
    const locale = locales[currentLocale.value] ?? locales.en;
    let value = resolve(locale as unknown as Record<string, unknown>, keys);

    if (typeof value !== 'string') {
        value = resolve(locales.en as unknown as Record<string, unknown>, keys);
    }

    if (typeof value !== 'string') {
        console.warn(`[i18n] Translation missing for key: "${key}"`);
        return key;
    }

    if (params) {
        return value.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? `{${k}}`));
    }

    return value;
}

export async function setLocale(locale: Locale): Promise<void> {
    if (!locales[locale] && locale !== 'en') {
        try {
            const loader = localeLoaders[locale];
            if (loader) {
                const module = await loader();
                locales[locale] = module.default;
            }
        } catch (e) {
            console.error(`[i18n] Failed to load locale: ${locale}`, e);
            locale = 'en'; // Fallback on error
        }
    }
    currentLocale.value = locale;
    localStorage.setItem('ir2mqtt_language', locale);
}

// Initialize the saved language on startup if it's not English
const savedLocale = (localStorage.getItem('ir2mqtt_language') as Locale) || 'en';
if (savedLocale !== 'en') {
    setLocale(savedLocale);
}

export function useI18n() {
    return { t, locale: currentLocale, setLocale, availableLocales };
}
