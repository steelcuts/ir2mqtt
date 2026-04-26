<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick } from 'vue';
import { storeToRefs } from 'pinia';
import Switch from '../components/Switch.vue';
import ConfigTransferModal from '../components/ConfigTransferModal.vue';
import { useSettingsStore, type TestMessage } from '../stores/settings';
import { useCommonStore } from '../stores/common';
import { useBridgeStore } from '../stores/bridges';
import { useI18n, availableLocales, setLocale, type Locale } from '../i18n';

const settingsStore = useSettingsStore();
const commonStore = useCommonStore();
const bridgeStore = useBridgeStore();
const { t, locale } = useI18n();

const { appMode, appModeLocked, topicStyle, mqttSettings, testState } = storeToRefs(settingsStore);

const logLevels = {
    DEBUG: 'Debug',
    INFO: 'Info',
    WARNING: 'Warning',
    ERROR: 'Error'
};

const { onlineBridges, hasOnlineBridges } = storeToRefs(bridgeStore);

const showConfigTransferModal = ref(false);
const testingMqtt = ref(false);
const savingMqtt = ref(false);
const isLoading = ref(false);

const executeModeChange = async (mode: string, style: string, event: MouseEvent | null = null) => {
    try {
        await settingsStore.updateAppMode(mode, style);
    } catch (e: unknown) {
        const err = e as { status?: number; message: string };
        if (err.status === 409) {
             if (await commonStore.askConfirm(t('confirm.duplicateNamesTitle'), `${t('confirm.duplicateNamesMsg', { details: err.message })}`, 'warning', t('confirm.fixAndSwitch'), event)) {
                 await settingsStore.updateAppMode(mode, style, true);
             } else {
                 settingsStore.fetchAppMode(); // Revert UI
             }
        } else {
            settingsStore.fetchAppMode(); // Revert UI on other errors
        }
    }
};

const handleModeChange = async (mode: string, style: string, event: MouseEvent | null = null) => {
    if (mode === appMode.value && style === topicStyle.value) return;

    let message = t('confirm.confirmChangeDefault');
    if (mode !== appMode.value) {
        message = mode === 'home_assistant' ? t('confirm.switchToHA') : t('confirm.switchToStandalone');
    } else if (style !== topicStyle.value) {
        message = style === 'name' ? t('confirm.switchToNameTopics') : t('confirm.switchToIdTopics');
    }

    if (await commonStore.askConfirm(t('confirm.confirmChangeTitle'), message, 'warning', t('confirm.yesChange'), event)) {
        await executeModeChange(mode, style, event);
    }
};

const handleMqttSave = async () => {
    savingMqtt.value = true;
    try {
        await settingsStore.saveMqttSettings(mqttSettings.value);
        commonStore.addFlashMessage(t('flash.mqttSaved'), 'success');
    } catch {
        // Error handled by api wrapper
    } finally {
        savingMqtt.value = false;
    }
};

const handleMqttTest = async () => {
    testingMqtt.value = true;
    try {
        const res = await settingsStore.testMqttSettings(mqttSettings.value);
        if (res && res.status === 'ok') {
            commonStore.addFlashMessage(res.message, 'success');
        } else {
            commonStore.addFlashMessage(res?.message || t('flash.connectionFailed'), 'error');
        }
    } catch {
        // Error handled by api wrapper
    } finally {
        testingMqtt.value = false;
    }
};

const selectedTxBridge = ref('');
const selectedRxBridge = ref('');
const selectedTxChannel = ref('');
const selectedRxChannel = ref('');
const selectedRepeats = ref(3);
const selectedTimeout = ref(3.0);

const txBridge = computed(() => onlineBridges.value.find(b => b.id === selectedTxBridge.value));
const rxBridge = computed(() => onlineBridges.value.find(b => b.id === selectedRxBridge.value));

const PROTOCOL_INFO: Record<string, { descKey: string; warnKey?: string }> = {
    nec: { descKey: 'std' },
    samsung: { descKey: 'tv' },
    sony: { descKey: 'tv' },
    panasonic: { descKey: 'tv' },
    rc5: { descKey: 'std', warnKey: 'strictTiming' },
    rc6: { descKey: 'std' },
    jvc: { descKey: 'tv' },
    lg: { descKey: 'tv' },
    coolix: { descKey: 'ac', warnKey: 'checksums' },
    pioneer: { descKey: 'av', warnKey: 'clash' },
    samsung36: { descKey: 'tv' },
    dish: { descKey: 'receiver' },
    midea: { descKey: 'ac', warnKey: 'checksums' },
    haier: { descKey: 'ac' },
    raw: { descKey: 'raw' },
    aeha: { descKey: 'ac' },
    abbwelcome: { descKey: 'intercom' },
    beo4: { descKey: 'bno' },
    byronsx: { descKey: 'doorbell' },
    canalsat: { descKey: 'receiver' },
    canalsat_ld: { descKey: 'receiver' },
    dooya: { descKey: 'rfBlinds', warnKey: 'rf' },
    drayton: { descKey: 'thermostat' },
    dyson: { descKey: 'fan' },
    gobox: { descKey: 'receiver' },
    keeloq: { descKey: 'rfSecurity', warnKey: 'rf' },
    magiquest: { descKey: 'wand' },
    mirage: { descKey: 'ac', warnKey: 'checksums' },
    nexa: { descKey: 'rfSwitch', warnKey: 'rf' },
    rc_switch: { descKey: 'rfSwitch', warnKey: 'rf' },
    roomba: { descKey: 'vacuum' },
    symphony: { descKey: 'acCooler' },
    toshiba_ac: { descKey: 'ac', warnKey: 'checksums' },
    toto: { descKey: 'toilet' },
};

const commonProtocols = computed(() => {
    if (!txBridge.value || !rxBridge.value) return [];
    const txCaps = txBridge.value.capabilities || [];
    const rxCaps = rxBridge.value.capabilities || [];
    return txCaps.filter(c => rxCaps.includes(c) && c !== 'pronto');
});

const selectedProtocols = ref<string[]>([]);
const showProtocols = ref(false);

watch(commonProtocols, (newProtos, oldProtos) => {
    const oldStr = (oldProtos || []).join(',');
    const newStr = (newProtos || []).join(',');
    if (oldStr !== newStr) {
        selectedProtocols.value = [...newProtos];
    }
});

watch(selectedTxBridge, () => { selectedTxChannel.value = ''; });
watch(selectedRxBridge, () => { selectedRxChannel.value = ''; });

const canStartTest = computed(() =>
    hasOnlineBridges.value &&
    !!selectedTxBridge.value &&
    !!selectedRxBridge.value &&
    selectedProtocols.value.length > 0 &&
    selectedRepeats.value >= 1 && selectedRepeats.value <= 10 &&
    selectedTimeout.value >= 0.1 && selectedTimeout.value <= 10.0
);

const toggleAllProtocols = () => {
    if (selectedProtocols.value.length === commonProtocols.value.length) {
        selectedProtocols.value = [];
    } else {
        selectedProtocols.value = [...commonProtocols.value];
    }
};

const handleStartTest = () => {
    if (!canStartTest.value) return;
    settingsStore.startLoopbackTest(
        selectedTxBridge.value,
        selectedRxBridge.value,
        selectedTxChannel.value || undefined,
        selectedRxChannel.value || undefined,
        selectedRepeats.value,
        selectedTimeout.value,
        selectedProtocols.value
    ).catch(() => {
        // Error handled by api
    });
};

const handleStopTest = () => {
    settingsStore.stopLoopbackTest();
};

const passedTests = computed(() => testState.value.results.filter((r: TestMessage) => r.status === 'passed').length);
const failedTests = computed(() => testState.value.results.filter((r: TestMessage) => r.status !== 'passed').length);

const resultsContainer = ref<HTMLElement | null>(null);
watch(() => testState.value.results.length, () => {
    nextTick(() => {
        if (resultsContainer.value) {
            resultsContainer.value.scrollTop = resultsContainer.value.scrollHeight;
        }
    });
});

const handleLanguageChange = (lang: string) => {
    setLocale(lang as Locale);
};

onMounted(async () => {
    isLoading.value = true;
    try {
        await settingsStore.fetchMqttSettings();
    } finally {
        isLoading.value = false;
    }
});
</script>

<template>
  <div class="space-y-4">
    <!-- UI SETTINGS -->
    <div
      class="card"
      data-tour-id="settings-ui-card"
    >
      <h2 class="text-lg font-semibold mb-4">
        {{ t('settings.ui.title') }}
      </h2>
      <div class="space-y-4">
        <!-- Language -->
        <div class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-800 transition-colors">
          <div>
            <h3 class="text-sm font-medium">
              {{ t('settings.ui.language') }}
            </h3>
            <p class="text-sm text-gray-400">
              {{ t('settings.ui.languageDesc') }}
            </p>
          </div>
          <select
            :value="locale"
            class="p-2 rounded w-48"
            @change="handleLanguageChange(($event.target as HTMLSelectElement).value)"
          >
            <option
              v-for="lang in availableLocales"
              :key="lang"
              :value="lang"
            >
              {{ t('lang.' + lang) }}
            </option>
          </select>
        </div>

        <!-- UI Indications -->
        <label class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-800 transition-colors cursor-pointer">
          <div>
            <h3 class="text-sm font-medium">{{ t('settings.ui.enableIndications') }}</h3>
            <p class="text-sm text-gray-400">{{ t('settings.ui.enableIndicationsDesc') }}</p>
          </div>
          <Switch v-model="settingsStore.settings.enableUiIndications" />
        </label>

        <label class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-800 transition-colors cursor-pointer">
          <div>
            <h3 class="text-sm font-medium">{{ t('settings.ui.flashIgnoredCodes') }}</h3>
            <p class="text-sm text-gray-400">{{ t('settings.ui.flashIgnoredCodesDesc') }}</p>
          </div>
          <Switch v-model="settingsStore.settings.flashIgnoredCodes" />
        </label>

        <!-- Theme -->
        <div class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-800 transition-colors">
          <div>
            <h3 class="text-sm font-medium">
              {{ t('settings.ui.theme') }}
            </h3>
            <p class="text-sm text-gray-400">
              {{ t('settings.ui.themeDesc') }}
            </p>
          </div>
          <select
            v-model="settingsStore.settings.theme"
            class="p-2 rounded w-48"
            data-tour-id="theme-selector"
          >
            <option value="theme-dark">
              {{ t('settings.ui.themes.dark') }}
            </option>
            <option value="theme-gray">
              {{ t('settings.ui.themes.gray') }}
            </option>
            <option value="theme-light">
              {{ t('settings.ui.themes.light') }}
            </option>
            <option value="theme-ha">
              {{ t('settings.ui.themes.ha') }}
            </option>
          </select>
        </div>

        <!-- Log Level -->
        <div class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-800 transition-colors">
          <div>
            <h3 class="text-sm font-medium">
              {{ t('settings.ui.logLevel') }}
            </h3>
            <p class="text-sm text-gray-400">
              {{ t('settings.ui.logLevelDesc') }}
            </p>
          </div>
          <select
            v-model="settingsStore.settings.logLevel"
            class="p-2 rounded w-48"
            data-tour-id="settings-log-level"
          >
            <option
              v-for="(_, level) in logLevels"
              :key="level"
              :value="level"
            >
              {{ level }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <!-- BACKEND SETTINGS -->
    <div
      class="card"
      data-tour-id="settings-backend-card"
    >
      <h2 class="text-lg font-semibold mb-4">
        {{ t('settings.backend.title') }}
      </h2>
      <div class="space-y-4">
        <div
          class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-800 transition-colors"
          data-tour-id="settings-operating-mode"
        >
          <div>
            <h3 class="text-sm font-medium">
              {{ t('settings.backend.operatingMode') }}
            </h3>
            <p class="text-sm text-gray-400">
              {{ t('settings.backend.operatingModeDesc') }}
            </p>
            <p
              v-if="appModeLocked"
              class="text-xs text-yellow-500 mt-1"
            >
              {{ t('settings.backend.lockedByHA') }}
            </p>
          </div>
          <div
            class="flex bg-gray-900 rounded p-1 border border-gray-600"
            :class="{'opacity-50 cursor-not-allowed': appModeLocked}"
          >
            <button
              class="px-3 py-1 rounded text-xs font-bold transition-colors min-w-[60px]"
              :class="appMode === 'home_assistant' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'"
              :disabled="appModeLocked"
              @click="!appModeLocked && handleModeChange('home_assistant', topicStyle, $event)"
            >
              {{ t('settings.backend.homeAssistant') }}
            </button>
            <button
              class="px-3 py-1 rounded text-xs font-bold transition-colors min-w-[60px]"
              :class="appMode === 'standalone' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'"
              :disabled="appModeLocked"
              @click="!appModeLocked && handleModeChange('standalone', topicStyle, $event)"
            >
              {{ t('settings.backend.standalone') }}
            </button>
          </div>
        </div>
        <div
          v-if="appMode === 'standalone'"
          class="flex items-center justify-between p-2 rounded-lg hover:bg-gray-800 transition-colors"
          data-tour-id="settings-topic-style"
        >
          <div>
            <h3 class="text-sm font-medium">
              {{ t('settings.backend.topicStyle') }}
            </h3>
            <p class="text-sm text-gray-400">
              {{ t('settings.backend.topicStyleDesc') }}
            </p>
          </div>
          <div class="flex bg-gray-900 rounded p-1 border border-gray-600">
            <button
              class="px-3 py-1 rounded text-xs font-bold transition-colors min-w-[60px]"
              :class="topicStyle === 'name' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'"
              @click="handleModeChange(appMode, 'name', $event)"
            >
              {{ t('settings.backend.name') }}
            </button>
            <button
              class="px-3 py-1 rounded text-xs font-bold transition-colors min-w-[60px]"
              :class="topicStyle === 'id' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200'"
              @click="handleModeChange(appMode, 'id', $event)"
            >
              {{ t('settings.backend.id') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- MQTT SETTINGS -->
    <div
      class="card"
      data-tour-id="settings-mqtt-card"
    >
      <div class="mb-4">
        <h2 class="text-lg font-semibold">
          {{ t('settings.mqtt.title') }}
        </h2>
        <p
          v-if="appModeLocked"
          class="text-xs text-yellow-500 mt-1"
        >
          {{ t('settings.mqtt.lockedByHA') }}
        </p>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label class="block text-sm font-medium text-gray-400 mb-1">{{ t('settings.mqtt.brokerHost') }}</label>
          <input
            v-model="mqttSettings.broker"
            type="text"
            :placeholder="t('settings.mqtt.brokerPlaceholder')"
            class="w-full rounded p-2"
            :disabled="isLoading || appModeLocked"
          >
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-400 mb-1">{{ t('settings.mqtt.port') }}</label>
          <input
            v-model.number="mqttSettings.port"
            type="number"
            class="w-full rounded p-2"
            :disabled="isLoading || appModeLocked"
          >
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-400 mb-1">{{ t('settings.mqtt.username') }}</label>
          <input
            v-model="mqttSettings.user"
            type="text"
            class="w-full rounded p-2"
            :disabled="isLoading || appModeLocked"
          >
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-400 mb-1">{{ t('settings.mqtt.password') }}</label>
          <input
            v-model="mqttSettings.password"
            type="password"
            class="w-full rounded p-2"
            :disabled="isLoading || appModeLocked"
          >
        </div>
      </div>
      <div class="flex justify-end gap-2">
        <button
          class="btn btn-secondary"
          :disabled="testingMqtt"
          @click="handleMqttTest"
        >
          <i
            class="mdi mdi-connection"
            :class="{'animate-spin': testingMqtt}"
          /> {{ t('settings.mqtt.testConnection') }}
        </button>
        <button
          class="btn btn-primary"
          :disabled="savingMqtt || appModeLocked"
          data-tour-id="settings-mqtt-save"
          @click="handleMqttSave"
        >
          <i class="mdi mdi-content-save" /> {{ t('settings.mqtt.saveReload') }}
        </button>
      </div>
    </div>

    <!-- LOOPBACK TEST -->
    <div
      class="card"
      data-tour-id="settings-loopback-card"
    >
      <h2 class="text-lg font-semibold mb-4">
        {{ t('settings.loopback.title') }}
      </h2>
      <p class="text-sm text-gray-400 mb-4">
        {{ t('settings.loopback.description') }}
      </p>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <!-- TX column -->
        <div class="space-y-2">
          <div>
            <label
              for="loopback-tx"
              class="block text-sm font-medium text-gray-400 mb-1"
            >{{ t('settings.loopback.senderBridge') }}</label>
            <select
              id="loopback-tx"
              v-model="selectedTxBridge"
              class="w-full rounded p-2"
              :disabled="testState.running"
            >
              <option
                value=""
                disabled
              >
                {{ t('settings.loopback.selectSender') }}
              </option>
              <option
                v-for="b in onlineBridges"
                :key="b.id"
                :value="b.id"
              >
                {{ b.name }}
              </option>
            </select>
          </div>
          <div v-if="txBridge && txBridge.transmitters && txBridge.transmitters.length > 1">
            <label
              for="loopback-tx-channel"
              class="block text-sm font-medium text-gray-400 mb-1"
            >{{ t('settings.loopback.txChannel') }}</label>
            <select
              id="loopback-tx-channel"
              v-model="selectedTxChannel"
              class="w-full rounded p-2"
              :disabled="testState.running"
            >
              <option value="">
                {{ t('settings.loopback.any') }}
              </option>
              <option
                v-for="ch in txBridge.transmitters"
                :key="ch.id"
                :value="ch.id"
              >
                {{ ch.id }}
              </option>
            </select>
          </div>
        </div>

        <!-- RX column -->
        <div class="space-y-2">
          <div>
            <label
              for="loopback-rx"
              class="block text-sm font-medium text-gray-400 mb-1"
            >{{ t('settings.loopback.receiverBridge') }}</label>
            <select
              id="loopback-rx"
              v-model="selectedRxBridge"
              class="w-full rounded p-2"
              :disabled="testState.running"
            >
              <option
                value=""
                disabled
              >
                {{ t('settings.loopback.selectReceiver') }}
              </option>
              <option
                v-for="b in onlineBridges"
                :key="b.id"
                :value="b.id"
              >
                {{ b.name }}
              </option>
            </select>
          </div>
          <div v-if="rxBridge && rxBridge.receivers && rxBridge.receivers.length > 1">
            <label
              for="loopback-rx-channel"
              class="block text-sm font-medium text-gray-400 mb-1"
            >{{ t('settings.loopback.rxChannel') }}</label>
            <select
              id="loopback-rx-channel"
              v-model="selectedRxChannel"
              class="w-full rounded p-2"
              :disabled="testState.running"
            >
              <option value="">
                {{ t('settings.loopback.any') }}
              </option>
              <option
                v-for="ch in rxBridge.receivers"
                :key="ch.id"
                :value="ch.id"
              >
                {{ ch.id }}
              </option>
            </select>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label
            for="loopback-repeats"
            class="block text-sm font-medium text-gray-400 mb-1"
          >{{ t('settings.loopback.repeatsPerProtocol') }}</label>
          <input
            id="loopback-repeats"
            v-model.number="selectedRepeats"
            type="number"
            min="1"
            max="10"
            class="w-full rounded p-2"
            :disabled="testState.running"
          >
        </div>
        <div>
          <label
            for="loopback-timeout"
            class="block text-sm font-medium text-gray-400 mb-1"
          >{{ t('settings.loopback.timeoutSeconds') }}</label>
          <input
            id="loopback-timeout"
            v-model.number="selectedTimeout"
            type="number"
            min="0.1"
            max="10.0"
            step="0.1"
            class="w-full rounded p-2"
            :disabled="testState.running"
          >
        </div>
      </div>

      <div
        v-if="commonProtocols.length > 0"
        class="mb-4 bg-gray-900 border border-gray-700 rounded-lg p-4"
      >
        <div
          class="flex justify-between items-center cursor-pointer"
          @click="showProtocols = !showProtocols"
        >
          <div class="font-semibold flex items-center gap-2">
            <span>{{ t('settings.loopback.protocolsToTest', { selected: selectedProtocols.length, total: commonProtocols.length }) }}</span>
            <span class="text-xs text-gray-400 font-normal ml-2">{{ t('settings.loopback.clickExpandCollapse') }}</span>
          </div>
          <i
            class="mdi text-xl transition-transform"
            :class="showProtocols ? 'mdi-chevron-up' : 'mdi-chevron-down'"
          />
        </div>

        <div
          v-show="showProtocols"
          class="mt-4"
        >
          <div class="flex justify-end mb-2">
            <button
              class="text-xs text-blue-400 hover:text-blue-300"
              @click="toggleAllProtocols"
            >
              {{ t('settings.loopback.selectDeselectAll') }}
            </button>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-60 overflow-y-auto pr-2">
            <label
              v-for="proto in commonProtocols"
              :key="proto"
              class="flex items-start gap-2 p-2 rounded hover:bg-gray-800 cursor-pointer border border-transparent"
              :class="{ 'border-gray-700 bg-gray-800/50': selectedProtocols.includes(proto) }"
            >
              <input
                v-model="selectedProtocols"
                type="checkbox"
                :value="proto"
                class="mt-1 rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500"
              >
              <div class="flex-grow">
                <div class="font-bold text-sm uppercase">{{ proto }}</div>
                <div class="text-xs text-gray-400">{{ PROTOCOL_INFO[proto]?.descKey ? t('loopback.protocols.' + PROTOCOL_INFO[proto].descKey) : 'Protocol' }}</div>
                <div
                  v-if="PROTOCOL_INFO[proto]?.warnKey"
                  class="text-[10px] text-yellow-500 mt-0.5 leading-tight"
                >
                  <i class="mdi mdi-alert-outline" /> {{ t('loopback.warnings.' + PROTOCOL_INFO[proto].warnKey) }}
                </div>
              </div>
            </label>
          </div>
        </div>
      </div>

      <div class="flex justify-end gap-2 mb-4">
        <button
          v-if="!testState.running"
          class="btn btn-primary whitespace-nowrap"
          :disabled="!canStartTest"
          @click="handleStartTest"
        >
          <i class="mdi mdi-test-tube" /> {{ t('settings.loopback.startTest') }}
        </button>
        <button
          v-else
          class="btn btn-danger whitespace-nowrap"
          @click="handleStopTest"
        >
          <i class="mdi mdi-stop" /> {{ t('settings.loopback.stopTest') }}
        </button>
      </div>

      <div
        v-if="testState.running || testState.results.length > 0"
        class="bg-gray-900 rounded-lg p-4 border border-gray-700"
      >
        <div class="flex justify-between items-center mb-2">
          <span class="font-bold text-sm">{{ t('settings.loopback.progressLabel', { current: testState.progress, total: testState.total }) }}</span>
          <div class="flex gap-3 text-xs font-bold">
            <span class="text-green-400">{{ t('settings.loopback.passed', { count: passedTests }) }}</span>
            <span class="text-red-400">{{ t('settings.loopback.failed', { count: failedTests }) }}</span>
          </div>
          <span
            v-if="testState.running"
            class="text-xs text-blue-400 animate-pulse"
          >{{ t('settings.loopback.testing') }}</span>
        </div>
        <div class="w-full bg-gray-700 rounded-full h-2 mb-4 overflow-hidden">
          <div
            class="bg-blue-500 h-2 rounded-full transition-all duration-300"
            :style="{ width: (testState.progress / (testState.total || 1) * 100) + '%' }"
          />
        </div>

        <div
          ref="resultsContainer"
          class="space-y-1 max-h-60 overflow-y-auto pr-2 text-xs font-mono"
        >
          <div
            v-for="(res, idx) in testState.results"
            :key="idx"
            class="flex flex-col p-2 rounded bg-gray-800 border border-gray-700"
          >
            <div class="flex justify-between items-center w-full">
              <span class="uppercase font-bold w-20">{{ res.protocol }}</span>
              <span class="text-gray-400 truncate flex-grow mx-2">{{ JSON.stringify(res.sent) }}</span>
              <span :class="res.status === 'passed' ? 'text-green-400 font-bold' : 'text-red-400 font-bold'">{{ (res.status || 'UNKNOWN').toUpperCase() }}</span>
            </div>
            <div
              v-if="res.status !== 'passed'"
              class="mt-1 text-[10px] text-red-300 pl-2 border-l-2 border-red-500 ml-1"
            >
              <span v-if="res.status === 'error'">{{ t('settings.loopback.errorMsg', { msg: res.error ?? '' }) }}</span>
              <span v-else-if="!res.received">{{ t('settings.loopback.timeoutMsg') }}</span>
              <span v-else>{{ t('settings.loopback.mismatchMsg', { data: JSON.stringify(res.received) }) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- CONFIGURATION MANAGEMENT -->
    <div
      class="card"
      data-tour-id="settings-config-card"
    >
      <h2 class="text-lg font-semibold mb-2">
        {{ t('settings.config.title') }}
      </h2>
      <p class="text-sm text-gray-400 mb-4">
        {{ t('settings.config.description') }}
      </p>

      <button
        class="btn btn-primary"
        @click="showConfigTransferModal = true"
      >
        <i class="mdi mdi-swap-horizontal" /> {{ t('settings.config.openTransfer') }}
      </button>
    </div>

    <!-- DANGER ZONE -->
    <div
      class="card border border-red-900/50"
      data-tour-id="settings-danger-zone"
    >
      <h2 class="text-lg font-semibold mb-2 text-red-500">
        {{ t('settings.danger.title') }}
      </h2>
      <p class="text-sm text-gray-400 mb-4">
        {{ t('settings.danger.description') }}
      </p>

      <div class="flex items-center justify-between p-4 bg-red-900/10 rounded-lg border border-red-900/30">
        <div>
          <h3 class="font-bold text-red-400">
            {{ t('settings.danger.factoryResetTitle') }}
          </h3>
          <p class="text-xs text-red-500">
            {{ t('settings.danger.factoryResetDesc') }}
          </p>
        </div>
        <button
          class="btn btn-danger"
          @click="settingsStore.factoryReset($event)"
        >
          <i class="mdi mdi-nuke" /> {{ t('settings.danger.factoryResetBtn') }}
        </button>
      </div>
    </div>

    <ConfigTransferModal
      :show="showConfigTransferModal"
      @close="showConfigTransferModal = false"
    />
  </div>
</template>
