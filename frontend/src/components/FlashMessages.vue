<template>
  <div class="fixed top-5 right-5 !m-0 z-[100] space-y-2 w-80">
    <transition-group name="flash">
      <div 
        v-for="msg in flashMessages" 
        :key="msg.id" 
        class="relative overflow-hidden bg-gray-800 rounded shadow-lg border-l-4"
        :class="getBorderClass(msg.type)"
      >
        <div class="p-4 flex items-start">
          <div class="flex-shrink-0">
            <i
              class="mdi text-2xl"
              :class="[getIcon(msg.type), getTextClass(msg.type)]"
            />
          </div>
          <div class="ml-3 w-0 flex-1 pt-0.5">
            <p class="text-sm font-medium text-gray-200">
              {{ msg.message }}
            </p>
          </div>
          <div class="ml-4 flex-shrink-0 flex">
            <button
              class="inline-flex text-gray-500 hover:text-gray-300 focus:outline-none transition-colors"
              @click="removeMessage(msg.id)"
            >
              <i class="mdi mdi-close" />
            </button>
          </div>
        </div>
        <!-- Progress Bar -->
        <div class="absolute bottom-0 left-0 h-1 w-full bg-gray-700">
          <div
            class="h-full"
            :class="getBgClass(msg.type)"
            :style="{ animation: `flash-progress ${msg.duration}ms linear forwards` }"
          />
        </div>
      </div>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia';
import { useCommonStore, FlashMessage } from '../stores/common';

const commonStore = useCommonStore();
const { flashMessages } = storeToRefs(commonStore);

const removeMessage = (id: number) => {
    commonStore.flashMessages = commonStore.flashMessages.filter(m => m.id !== id);
};

const getIcon = (type: FlashMessage['type']) => {
  if (type === 'success') return 'mdi-check-circle';
  if (type === 'warning') return 'mdi-alert';
  if (type === 'error' || type === 'danger') return 'mdi-alert-circle';
  if (type === 'automation') return 'mdi-robot';
  return 'mdi-information';
};

const getBorderClass = (type: FlashMessage['type']) => {
    if (type === 'success') return 'border-green-500';
    if (type === 'warning') return 'border-yellow-500';
    if (type === 'error' || type === 'danger') return 'border-red-500';
    if (type === 'automation') return 'border-purple-500';
    return 'border-blue-500';
};

const getTextClass = (type: FlashMessage['type']) => {
    if (type === 'success') return 'text-green-500';
    if (type === 'warning') return 'text-yellow-500';
    if (type === 'error' || type === 'danger') return 'text-red-500';
    if (type === 'automation') return 'text-purple-500';
    return 'text-blue-500';
};

const getBgClass = (type: FlashMessage['type']) => {
    if (type === 'success') return 'bg-green-500';
    if (type === 'warning') return 'bg-yellow-500';
    if (type === 'error' || type === 'danger') return 'bg-red-500';
    if (type === 'automation') return 'bg-purple-500';
    return 'bg-blue-500';
};
</script>

<style>
@keyframes flash-progress {
    from { width: 100%; }
    to { width: 0%; }
}
</style>

<style scoped>
.flash-enter-active, .flash-leave-active {
  transition: all 0.4s ease;
}
.flash-enter-from, .flash-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
.flash-move {
    transition: transform 0.4s ease;
}
</style>
