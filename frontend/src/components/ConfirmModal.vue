<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import { storeToRefs } from 'pinia';
import { useCommonStore } from '../stores/common';
import { useI18n } from '../i18n';

const commonStore = useCommonStore();
const { confirmation } = storeToRefs(commonStore);
const { t } = useI18n();

const handleConfirm = (result: boolean) => {
    if (confirmation.value.resolve) {
        confirmation.value.resolve(result);
    }
    confirmation.value.show = false;
    setTimeout(() => { confirmation.value.resolve = null; }, 300);
};

const onEscape = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && confirmation.value.show) {
    handleConfirm(false);
  }
};

onMounted(() => document.addEventListener('keydown', onEscape));
onUnmounted(() => document.removeEventListener('keydown', onEscape));
</script>

<template>
  <transition name="fade">
    <div
      v-if="confirmation.show"
      class="fixed inset-0 !m-0 bg-gray-900/60 flex items-center justify-center z-[60] backdrop-blur-sm"
      @click.self="handleConfirm(false)"
    >
      <div
        class="bg-gray-900 border border-gray-700 rounded-lg p-6 max-w-sm w-full max-h-[90vh] overflow-y-auto shadow-2xl animate-in fade-in scale-95 duration-200"
        style="animation: slideInUp 0.3s ease-out;"
      >
        <h3
          class="text-lg font-semibold mb-2 flex items-center gap-2"
          :class="confirmation.type === 'danger' ? 'text-red-500' : (confirmation.type === 'warning' ? 'text-yellow-400' : 'text-gray-200')"
        >
          <i
            v-if="confirmation.type === 'danger'"
            class="mdi mdi-alert-circle"
          />
          <i
            v-else-if="confirmation.type === 'warning'"
            class="mdi mdi-alert"
          />
          <i
            v-else
            class="mdi mdi-information"
          />
          {{ confirmation.title }}
        </h3>
        <p class="text-gray-300 mb-6 whitespace-pre-wrap">
          {{ confirmation.message }}
        </p>
        <div class="flex flex-col gap-3">
          <div class="flex gap-2 justify-end">
            <button
              class="btn btn-secondary"
              @click="handleConfirm(false)"
            >
              {{ confirmation.cancelText }}
            </button>
            <button
              class="btn"
              :class="confirmation.type === 'danger' ? 'btn-danger' : (confirmation.type === 'warning' ? 'bg-yellow-600 hover:bg-yellow-500 text-white' : 'btn-primary')"
              @click="handleConfirm(true)"
            >
              {{ confirmation.confirmText }}
            </button>
          </div>
          <p class="text-[10px] text-gray-500 text-right italic select-none">
            {{ t('confirm.tipPrefix') }} <span class="bg-gray-800 px-1 rounded border border-gray-700 not-italic font-mono">{{ t('confirm.shift') }}</span> {{ t('confirm.tipSuffix') }}
          </p>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@keyframes slideInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>