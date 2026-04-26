<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useBridgeStore } from '../stores/bridges';
import { useCommonStore } from '../stores/common';
import { useI18n } from '../i18n';
import type { ReceiverConfig, TransmitterConfig } from '../types';

const bridgeStore = useBridgeStore();
const commonStore = useCommonStore();

const { t } = useI18n();

const props = defineProps({
  show: Boolean
});

const emit = defineEmits(['close']);

const { bridges, availableSerialPorts, loadingSerialPorts, testingSerialConnection, creatingSerialBridge } = storeToRefs(bridgeStore);

const selectedPort = ref('');
const baudrate = ref(115200);
const testResult = ref<{ status: string; message: string; config?: { id?: string; name?: string; version?: string; receivers?: ReceiverConfig[]; transmitters?: TransmitterConfig[]; capabilities?: string[]; } } | null>(null);
const testError = ref('');
const hasTestedSuccess = ref(false);

const baudRateOptions = [1200, 2400, 4800, 9600, 14400, 19200, 38400, 57600, 115200, 230400];

const isValid = computed(() => {
  return selectedPort.value && baudrate.value > 0;
});

const canCreate = computed(() => {
  return isValid.value && hasTestedSuccess.value;
});

const isPortUsed = (portName: string) => {
  return bridges.value.some(b => b.connection_type === 'serial' && b.serial_port === portName);
};

const onEscape = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    handleClose();
  }
};

watch(() => props.show, (newVal) => {
  if (newVal) {
    bridgeStore.listSerialPorts();
    selectedPort.value = '';
    baudrate.value = 115200;
    testResult.value = null;
    testError.value = '';
    hasTestedSuccess.value = false;
    document.addEventListener('keydown', onEscape);
  } else {
    document.removeEventListener('keydown', onEscape);
  }
});

const handleTest = async () => {
  testError.value = '';
  testResult.value = null;
  hasTestedSuccess.value = false;

  try {
    const result = await bridgeStore.testSerialConnection(selectedPort.value, baudrate.value);
    if (result) {
      testResult.value = result;
      hasTestedSuccess.value = result.status === 'success';
      if (hasTestedSuccess.value) {
        commonStore.addFlashMessage(t('store.serialTestSuccess'), 'success');
      } else {
        testError.value = result.message || t('bridges.modal.testFailed');
      }
    }
  } catch (error) {
    testError.value = error instanceof Error ? error.message : t('bridges.modal.testFailed');
    hasTestedSuccess.value = false;
  }
};

const handleCreate = async () => {
  if (!canCreate.value) return;

  try {
    const bridgeId = testResult.value?.config?.id;
    const result = await bridgeStore.createSerialBridge(selectedPort.value, baudrate.value, bridgeId);
    if (result && result.status === 'ok') {
      emit('close');
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : 'Failed to create serial bridge';
    commonStore.addFlashMessage(t('store.serialBridgeFailed', { msg: errorMsg }), 'error');
  }
};

const handleClose = () => {
  emit('close');
};
</script>

<template>
  <div
    v-if="show"
    class="fixed inset-0 !m-0 bg-gray-900/60 flex items-center justify-center z-50 backdrop-blur-sm"
    @click.self="handleClose"
  >
    <div
      class="bg-gray-900 rounded-lg shadow-2xl p-6 w-full max-w-md border border-gray-700 animate-in fade-in scale-95 duration-200"
      style="animation: slideInUp 0.3s ease-out;"
      data-tour-id="add-serial-bridge-modal"
    >
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-lg font-semibold flex items-center gap-3 ">
          {{ t('bridges.addSerialBridge') }}
        </h2>
        <button
          class="text-gray-500 hover:text-gray-300 hover:bg-gray-800 p-1 rounded transition-colors"
          @click="handleClose"
        >
          <i class="mdi mdi-close text-xl" />
        </button>
      </div>

      <!-- Port Selection -->
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-semibold mb-2 text-gray-300">{{ t('bridges.modal.port') }}</label>
          <div
            v-if="loadingSerialPorts"
            class="text-gray-400 text-sm flex items-center gap-2 py-2"
          >
            <i class="mdi mdi-loading mdi-spin" />
            {{ t('bridges.modal.loadingPorts') }}
          </div>
          <select
            v-else
            v-model="selectedPort"
            :disabled="creatingSerialBridge"
            class="w-full rounded px-3 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 transition-colors"
          >
            <option value="">
              {{ t('bridges.modal.selectPort') }}
            </option>
            <option
              v-for="port in availableSerialPorts"
              :key="port.port"
              :value="port.port"
              :disabled="isPortUsed(port.port)"
            >
              {{ port.port }} - {{ port.description }} {{ isPortUsed(port.port) ? t('bridges.modal.inUse') : '' }}
            </option>
          </select>
        </div>

        <!-- Baudrate Selection -->
        <div>
          <label class="block text-sm font-semibold mb-2 text-gray-300">{{ t('bridges.modal.baudrate') }}</label>
          <select
            v-model.number="baudrate"
            :disabled="creatingSerialBridge"
            class="w-full rounded px-3 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 transition-colors"
          >
            <option
              v-for="rate in baudRateOptions"
              :key="rate"
              :value="rate"
            >
              {{ rate }} bps
            </option>
          </select>
        </div>

        <!-- Test Section -->
        <div class="border-t border-gray-700 pt-4">
          <button
            :disabled="!isValid || testingSerialConnection || creatingSerialBridge"
            class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed rounded text-white font-medium transition-colors"
            @click="handleTest"
          >
            <i
              v-if="testingSerialConnection"
              class="mdi mdi-loading mdi-spin"
            />
            <i
              v-else
              class="mdi mdi-check-circle-outline"
            />
            {{ testingSerialConnection ? t('bridges.modal.testing') : t('bridges.modal.testConnection') }}
          </button>

          <!-- Test Result -->
          <transition
            enter-active-class="transition-all duration-300"
            leave-active-class="transition-all duration-200"
            enter-from-class="opacity-0 -translate-y-2"
            leave-to-class="opacity-0 -translate-y-2"
          >
            <div
              v-if="testError || (testResult && hasTestedSuccess)"
              class="mt-3"
            >
              <div
                v-if="testError"
                class="p-3 bg-red-900/30 border border-red-700 rounded text-red-200 text-sm flex items-start gap-2"
              >
                <i class="mdi mdi-alert-circle mt-0.5 flex-shrink-0" />
                <span>{{ testError }}</span>
              </div>
              <div
                v-if="testResult && hasTestedSuccess"
                class="p-3 bg-green-900/30 border border-green-700 rounded text-green-200 text-sm"
              >
                <div class="flex items-start gap-2">
                  <i class="mdi mdi-check-circle mt-0.5 flex-shrink-0" />
                  <div>
                    <div class="font-medium">
                      {{ testResult.message }}
                    </div>
                    <div
                      v-if="testResult.config"
                      class="mt-2 text-xs text-gray-300 space-y-1"
                    >
                      <div><strong>{{ t('bridges.modal.id') }}</strong> <span class="text-gray-400">{{ testResult.config.id }}</span></div>
                      <div v-if="testResult.config.name">
                        <strong>{{ t('bridges.modal.name') }}</strong> <span class="text-gray-400">{{ testResult.config.name }}</span>
                      </div>
                      <div v-if="testResult.config.version">
                        <strong>{{ t('bridges.modal.version') }}</strong> <span class="text-gray-400">{{ testResult.config.version }}</span>
                      </div>
                      <div v-if="testResult.config?.receivers && testResult.config.receivers.length > 0">
                        <strong>{{ t('bridges.modal.receivers') }}</strong> <span class="text-gray-400">{{ testResult.config?.receivers?.length }}</span>
                      </div>
                      <div v-if="testResult.config?.transmitters && testResult.config.transmitters.length > 0">
                        <strong>{{ t('bridges.modal.senders') }}</strong> <span class="text-gray-400">{{ testResult.config?.transmitters?.length }}</span>
                      </div>

                      <div v-if="testResult.config?.capabilities && testResult.config.capabilities.length > 0">
                        <strong>{{ t('bridges.modal.protocols') }}</strong> <span class="text-gray-400">{{ testResult.config?.capabilities?.join(', ') }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </transition>
        </div>

        <!-- Action Buttons -->
        <div class="flex gap-2 pt-4 border-t border-gray-700">
          <button
            class="flex-1 btn btn-secondary disabled:opacity-50"
            :disabled="creatingSerialBridge"
            @click="handleClose"
          >
            {{ t('confirm.cancel') }}
          </button>
          <button
            :disabled="!canCreate || creatingSerialBridge"
            class="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed rounded text-white font-medium transition-colors"
            @click="handleCreate"
          >
            <i
              v-if="creatingSerialBridge"
              class="mdi mdi-loading mdi-spin"
            />
            <i
              v-else
              class="mdi mdi-plus-circle"
            />
            {{ creatingSerialBridge ? t('bridges.modal.creating') : t('bridges.modal.create') }}
          </button>
        </div>

        <!-- Help text -->
        <div class="text-xs text-gray-400 text-center pt-2">
          <i class="mdi mdi-information-outline" />
          {{ t('bridges.modal.helpText') }}
        </div>
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
