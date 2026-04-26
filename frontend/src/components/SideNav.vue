<script setup lang="ts">
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useCommonStore } from '../stores/common';
import { useIrdbStore } from '../stores/irdb';
import { startTour } from '../tour';
import { useI18n } from '../i18n';

const navItems = ['Devices', 'Automations', 'Bridges', 'Settings', 'Status', 'IR_DB'];
const navIcons: Record<string, string> = {
  Devices: 'remote-tv',
  Automations: 'robot',
  Bridges: 'bridge',
  Settings: 'cog',
  Status: 'information-outline',
  IR_DB: 'database-search'
};

const commonStore = useCommonStore();
const irdbStore = useIrdbStore();

const { activeView, isNavPinned } = storeToRefs(commonStore);
const { showIrDbBrowser } = storeToRefs(irdbStore);

const { t } = useI18n();

const isExpanded = computed(() => isNavPinned.value);

const handleNavClick = (item: string) => {
    if (item === 'IR_DB') {
        showIrDbBrowser.value = true;
    } else {
        activeView.value = item;
    }
};
</script>

<template>
  <nav
    class="bg-gray-800 flex flex-col transition-all duration-300 ease-in-out relative border-r border-gray-600 overflow-hidden shadow-xl"
    :class="isExpanded ? 'w-[255px]' : 'w-[55px]'"
  >
    <div
      class="h-14 flex items-center border-b border-gray-600 relative group"
      data-tour-id="main-icon"
    >
      <div class="w-[55px] flex items-center justify-center flex-shrink-0 relative">
        <button
          class="absolute inset-0 flex items-center justify-center text-gray-400 hover:text-gray-200 transition-opacity duration-200"
          :title="isNavPinned ? t('nav.collapseSidebar') : t('nav.expandSidebar')"
          @click="commonStore.toggleNavPin"
        >
          <i
            class="mdi text-2xl"
            :class="isNavPinned ? 'mdi-menu-open' : 'mdi-menu'"
          />
        </button>
      </div>
      <span
        class="text-xl font-light whitespace-nowrap transition-all duration-300 ease-in-out overflow-hidden"
        :class="isExpanded ? 'opacity-100 max-w-48' : 'opacity-0 max-w-0'"
      >IR2MQTT</span>
    </div>

    <ul class="flex flex-col py-3 flex-grow gap-2 px-1">
      <li
        v-for="item in navItems"
        :key="item"
      >
        <a
          href="#"
          class="flex items-center h-10 rounded transition-colors"
          :class="{
            'bg-ha-500/15 text-ha-500': activeView === item,
            'text-gray-200 hover:bg-gray-700/50': activeView !== item
          }"
          :data-tour-id="'nav-' + item"
          @click.prevent="handleNavClick(item)"
        >
          <div class="w-[39px] flex items-center justify-center flex-shrink-0 mx-1">
            <i
              class="mdi text-2xl"
              :class="'mdi-' + navIcons[item]"
            />
          </div>
          <span
            class="text-sm font-medium whitespace-nowrap transition-all duration-300 ease-in-out overflow-hidden ml-1"
            :class="isExpanded ? 'opacity-100 max-w-48' : 'opacity-0 max-w-0'"
          >{{ t('nav.' + item.toLowerCase().replace('_', '')) }}</span>
        </a>
      </li>
    </ul>

    <div class="py-3 px-1 border-t border-gray-600 gap-2 flex flex-col">
      <a
        href="#"
        class="flex items-center h-10 rounded transition-colors text-gray-200 hover:bg-gray-700/50"
        :title="t('nav.tour')"
        @click.prevent="startTour"
      >
        <div class="w-[39px] flex items-center justify-center flex-shrink-0 mx-1">
          <i class="mdi mdi-help-circle-outline text-2xl" />
        </div>
        <span
          class="text-sm font-medium whitespace-nowrap transition-all duration-300 ease-in-out overflow-hidden ml-1"
          :class="isExpanded ? 'opacity-100 max-w-48' : 'opacity-0 max-w-0'"
        >{{ t('nav.tour') }}</span>
      </a>
      <a
        href="https://steelcuts.github.io/ir2mqtt/"
        target="_blank"
        rel="noopener noreferrer"
        class="flex items-center h-10 rounded transition-colors text-gray-200 hover:bg-gray-700/50"
        :title="t('nav.docs')"
      >
        <div class="w-[39px] flex items-center justify-center flex-shrink-0 mx-1">
          <i class="mdi mdi-book-open-page-variant-outline text-2xl" />
        </div>
        <span
          class="text-sm font-medium whitespace-nowrap transition-all duration-300 ease-in-out overflow-hidden ml-1"
          :class="isExpanded ? 'opacity-100 max-w-48' : 'opacity-0 max-w-0'"
        >{{ t('nav.docs') }}</span>
      </a>
    </div>
  </nav>
</template>
