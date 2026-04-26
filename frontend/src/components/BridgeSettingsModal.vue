<script setup lang="ts">
import { ref, watch } from 'vue';
import Switch from './Switch.vue';
import { useBridgeStore } from '../stores/bridges';
import { useCommonStore } from '../stores/common';
import { useI18n } from '../i18n';
import type { Bridge } from '../types';

const bridgeStore = useBridgeStore();
const commonStore = useCommonStore();

const props = defineProps({
  show: Boolean,
  bridge: {
    type: Object as () => Bridge | null,
    default: null,
  },
});

const emit = defineEmits(['close']);

const { t } = useI18n();

const localSettings = ref({
    echo_enabled: false,
    echo_timeout: 500,
    echo_smart: true,
    echo_ignore_self: true,
    echo_ignore_others: false
});

watch(() => props.show, (newVal) => {
  if (newVal && props.bridge) {
    // Merge defaults with existing settings
    const defaults = {
        echo_enabled: false,
        echo_timeout: 500,
        echo_smart: true,
        echo_ignore_self: true,
        echo_ignore_others: false
    };
    localSettings.value = { ...defaults, ...(props.bridge.settings || {}) };
  }
}, { immediate: true });

const save = async () => {
    if (!props.bridge) return;
    await bridgeStore.updateBridgeSettings(props.bridge.id, localSettings.value);
    await bridgeStore.fetchBridges();
    commonStore.addFlashMessage(t('store.bridgeSettingsSaved'), 'success');
    emit('close');
};
</script>

<template>
  <div
    v-if="show"
    class="fixed inset-0 !m-0 bg-gray-900/60 flex items-center justify-center z-50 backdrop-blur-sm"
    @click.self="$emit('close')"
  >
    <div
      class="bg-gray-900 border border-gray-700 rounded-lg max-w-lg w-full flex flex-col shadow-2xl animate-in fade-in scale-95 duration-200"
      data-tour-id="bridge-settings-modal"
      style="animation: slideInUp 0.3s ease-out;"
    >
      <div class="p-6 border-b border-gray-700 shrink-0">
        <h3 class="text-lg font-semibold">
          {{ t('bridges.settings.title') }}: {{ bridge?.name }}
        </h3>
      </div>
      
      <div class="p-6 space-y-6">
        <!-- Echo Suppression -->
        <div
          class="space-y-4"
          data-tour-id="bridge-settings-echo"
        >
          <div class="flex items-center justify-between">
            <div>
              <h4 class="font-bold text-lg">
                {{ t('bridges.settings.echoSuppression') }}
              </h4>
              <p class="text-sm text-gray-400">
                {{ t('bridges.settings.echoDesc') }}
              </p>
            </div>
            <Switch v-model="localSettings.echo_enabled" />
          </div>

          <div
            v-if="localSettings.echo_enabled"
            class="space-y-4 pl-4 border-l-2 border-gray-700"
          >
            <div>
              <label class="block text-sm font-medium text-gray-300 mb-1">{{ t('bridges.settings.timeout') }}</label>
              <input
                v-model.number="localSettings.echo_timeout"
                type="number"
                class="w-full rounded p-2 bg-gray-900 border-gray-600"
                min="50"
                step="50"
              >
              <p class="text-xs text-gray-400 mt-1">
                {{ t('bridges.settings.timeoutDesc') }}
              </p>
            </div>

            <label class="flex items-center justify-between cursor-pointer">
              <div>
                <span class="font-bold text-sm block">{{ t('bridges.settings.smartMode') }}</span>
                <span class="text-xs text-gray-400">{{ t('bridges.settings.smartModeDesc') }}</span>
              </div>
              <Switch v-model="localSettings.echo_smart" />
            </label>

            <label class="flex items-center justify-between cursor-pointer">
              <div>
                <span class="font-bold text-sm block">{{ t('bridges.settings.ignoreSelf') }}</span>
                <span class="text-xs text-gray-400">{{ t('bridges.settings.ignoreSelfDesc') }}</span>
              </div>
              <Switch v-model="localSettings.echo_ignore_self" />
            </label>

            <label class="flex items-center justify-between cursor-pointer">
              <div>
                <span class="font-bold text-sm block">{{ t('bridges.settings.ignoreOthers') }}</span>
                <span class="text-xs text-gray-400">{{ t('bridges.settings.ignoreOthersDesc') }}</span>
              </div>
              <Switch v-model="localSettings.echo_ignore_others" />
            </label>
          </div>
        </div>
      </div>

      <div class="p-6 border-t border-gray-700 flex gap-2 justify-end shrink-0">
        <button
          class="btn btn-secondary"
          @click="$emit('close')"
        >
          {{ t('confirm.cancel') }}
        </button>
        <button
          class="btn btn-primary"
          @click="save"
        >
          {{ t('bridges.settings.save') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes slideInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>