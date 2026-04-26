<script setup lang="ts">
import { storeToRefs } from 'pinia';
import Switch from './Switch.vue';
import BridgeSelector from './BridgeSelector.vue';
import { useLearnStore } from '../stores/learn';
import { useBridgeStore } from '../stores/bridges';
import { useI18n } from '../i18n';

const learnStore = useLearnStore();
const bridgeStore = useBridgeStore();

const { learn } = storeToRefs(learnStore);
const { onlineBridges, hasOnlineBridges } = storeToRefs(bridgeStore);

const { t } = useI18n();

defineProps({
    show: Boolean,
});

const emit = defineEmits(['close']);

const startAndClose = () => {
    if (learn.value.active) return;
    learnStore.startLearn();
    emit('close');
};

</script>
<template>
  <div
    v-if="show"
    class="fixed inset-0 !m-0 bg-gray-900/60 flex items-center justify-center z-40 backdrop-blur-sm"
    @click.self="$emit('close')"
  >
    <div
      class="bg-gray-900 border border-gray-700 rounded-lg p-6 max-w-md w-full shadow-2xl animate-in fade-in scale-95 duration-200"
      style="animation: slideInUp 0.3s ease-out;"
    >
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-lg font-semibold">
          {{ t('learn.title') }}
        </h2>
        <button
          class="text-gray-500 hover:text-gray-300 transition-colors"
          @click="$emit('close')"
        >
          <i class="mdi mdi-close text-2xl" />
        </button>
      </div>

      <div class="space-y-4">
        <div>
          <BridgeSelector
            v-if="hasOnlineBridges"
            v-model="learn.targetBridges"
            :bridges="onlineBridges"
            type="source"
          />
          <select
            v-else
            class="p-2 rounded bg-gray-900 border border-gray-700 w-full"
            disabled
          >
            <option>{{ t('learn.noBridges') }}</option>
          </select>
          <p class="text-xs text-gray-400 mt-1">
            {{ t('learn.selectDesc') }}
          </p>
        </div>

        <div class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-800/50">
          <div
            class="cursor-pointer flex-grow"
            @click="learn.smart = !learn.smart"
          >
            <span class="font-medium text-gray-200">{{ t('learn.smartLearn') }}</span>
            <p class="text-xs text-gray-400">
              {{ t('learn.smartLearnDesc') }}
            </p>
          </div>
          <Switch
            v-model="learn.smart"
            :disabled="learn.active"
          />
        </div>
      </div>

      <div class="flex justify-end gap-4 mt-6">
        <button
          class="btn"
          @click="$emit('close')"
        >
          {{ t('confirm.cancel') }}
        </button>
        <button
          class="btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!hasOnlineBridges || learn.active"
          @click="startAndClose"
        >
          <i class="mdi mdi-radio-tower mr-1" />
          <span>{{ learn.active ? t('learn.listeningBtn') : t('learn.startBtn') }}</span>
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
