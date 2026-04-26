<template>
  <div>
    <label
      v-if="label"
      class="block text-sm font-medium text-gray-300 mb-1"
    >{{ label }}</label>
    
    <div class="flex rounded-md shadow-sm">
      <span class="inline-flex items-center px-3 rounded-l-md border border-r-0 border-gray-600 bg-gray-700 text-gray-300">
        <i :class="['mdi', `mdi-${modelValue || 'emoticon-outline'}`, 'text-xl']" />
      </span>
      <input 
        type="text" 
        class="block w-full p-2 border border-gray-600 cursor-pointer rounded-l-none"
        :class="{ 'rounded-r-md': !modelValue, 'border-r-0 rounded-r-none': modelValue }"
        :placeholder="placeholder || t('iconPicker.placeholder')" 
        :value="modelValue"
        readonly
        @click="openModal"
      >
      <button 
        v-if="modelValue" 
        class="inline-flex items-center px-3 rounded-r-md border border-l-0 border-gray-600 bg-gray-700 text-gray-300 hover:bg-gray-600" 
        type="button" 
        :title="t('iconPicker.clearSelection')"
        @click.stop="clearSelection"
      >
        <i class="mdi mdi-close" />
      </button>
    </div>

    <Teleport to="body">
      <div
        v-if="isOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/60 backdrop-blur-sm"
        @click.self="closeModal"
      >
        <div
          class="relative bg-gray-900 rounded-lg shadow-2xl w-[90vw] max-w-6xl h-[80vh] flex flex-col border border-gray-700 animate-in fade-in scale-95 duration-200"
          style="animation: slideInUp 0.3s ease-out;"
        >
          <div class="flex items-center p-4 border-b border-gray-700">
            <div class="flex items-center flex-grow bg-gray-800 rounded-md">
              <span class="pl-3 pr-2 text-gray-400">
                <i class="mdi mdi-magnify text-lg" />
              </span>
              <input 
                ref="searchInput"
                v-model="searchQuery" 
                type="text" 
                class="w-full p-2 bg-transparent focus:outline-none" 
                :placeholder="t('iconPicker.searchPlaceholder')"
              >
            </div>
            <button
              type="button"
              class="ml-4 p-2 rounded-full hover:bg-gray-700 text-gray-400"
              :title="t('iconPicker.close')"
              @click="closeModal"
            >
              <i class="mdi mdi-close" />
            </button>
          </div>

          <div
            ref="scrollContainer"
            class="overflow-y-auto p-4"
            @scroll="handleScroll"
          >
            <!-- Recent Icons -->
            <div v-if="recentIcons.length > 0 && !searchQuery">
              <h3 class="text-sm font-semibold text-gray-400 mb-2">
                {{ t('iconPicker.recentlyUsed') }}
              </h3>
              <div class="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-2">
                <button 
                  v-for="iconName in recentIcons" 
                  :key="`recent-${iconName}`"
                  class="flex flex-col items-center justify-center aspect-square rounded-lg transition-colors duration-150"
                  :class="{ 
                    'bg-ha-500 text-white': modelValue === iconName, 
                    'bg-gray-800 text-gray-300 hover:bg-gray-700': modelValue !== iconName 
                  }"
                  :title="iconName"
                  @click="selectIcon(iconName)"
                >
                  <i :class="['mdi', `mdi-${iconName}`, 'text-3xl']" />
                  <span class="text-xs text-center truncate w-full mt-1 px-1">{{ iconName }}</span>
                </button>
              </div>
              <div class="border-b border-gray-700 my-4" />
            </div>

            <div
              v-if="isLoading"
              class="flex flex-col items-center justify-center h-64 text-gray-400"
            >
              <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-ha-500" />
              <p class="mt-4">
                {{ t('iconPicker.loading') }}
              </p>
            </div>

            <div
              v-else-if="filteredIcons.length === 0"
              class="flex flex-col items-center justify-center h-64 text-gray-400"
            >
              <i class="mdi mdi-emoticon-sad text-6xl" />
              <p class="mt-4">
                {{ t('iconPicker.noIconsFound', { query: searchQuery }) }}
              </p>
            </div>

            <div v-else>
              <h3
                v-if="!searchQuery"
                class="text-sm font-semibold text-gray-400 mb-2"
              >
                {{ t('iconPicker.allIcons') }}
              </h3>
              <div class="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-2">
                <button 
                  v-for="icon in visibleIcons" 
                  :key="icon.name"
                  class="flex flex-col items-center justify-center aspect-square rounded-lg transition-colors duration-150"
                  :class="{ 
                    'bg-ha-500 text-white': modelValue === icon.name, 
                    'bg-gray-800 text-gray-300 hover:bg-gray-700': modelValue !== icon.name 
                  }"
                  :title="icon.name"
                  @click="selectIcon(icon.name)"
                >
                  <i :class="['mdi', `mdi-${icon.name}`, 'text-3xl']" />
                  <span class="text-xs text-center truncate w-full mt-1 px-1">{{ icon.name }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue';
import mdiCss from '@mdi/font/css/materialdesignicons.css?raw';
import { useI18n } from '../i18n';

// Props
defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  label: {
    type: String,
    default: 'Icon'
  },
  placeholder: {
    type: String,
    default: ''
  }
});

// Events
const emit = defineEmits(['update:modelValue']);

// State
const isOpen = ref(false);
const isLoading = ref(false);
const allIcons = ref<{ name: string; tags: string[] }[]>([]);
const searchQuery = ref('');
const searchInput = ref<HTMLInputElement | null>(null);
const renderLimit = ref(150);
const scrollContainer = ref<HTMLElement | null>(null);
const recentIcons = ref<string[]>([]);

const { t } = useI18n();

const RECENT_ICONS_KEY = 'ir2mqtt-recent-icons';

const loadIcons = async () => {
  if (allIcons.value.length > 0) return;
  
  isLoading.value = true;
  try {
    const regex = /\.mdi-([a-z0-9-]+)::?before/g;
    allIcons.value = [...mdiCss.matchAll(regex)].map(m => ({ name: m[1], tags: [] }));
  } catch (e: unknown) {
    console.error("error_parsing_icons", e);
    allIcons.value = [
      { name: 'home', tags: [] }, { name: 'lightbulb', tags: [] }, { name: 'battery', tags: [] }, { name: 'alert', tags: [] }
    ];
  } finally {
    isLoading.value = false;
  }
};

const openModal = async () => {
  isOpen.value = true;
  searchQuery.value = '';
  renderLimit.value = 150; // Reset render limit
  await loadIcons();
  
  nextTick(() => {
    searchInput.value?.focus();
  });
};

const closeModal = () => {
  isOpen.value = false;
};

const addRecentIcon = (iconName: string) => {
    if (!iconName) return;
    const recents = [...recentIcons.value];
    const existingIndex = recents.indexOf(iconName);
    if (existingIndex > -1) {
        recents.splice(existingIndex, 1);
    }
    recents.unshift(iconName);
    if (recents.length > 10) {
        recents.pop();
    }
    recentIcons.value = recents;
    localStorage.setItem(RECENT_ICONS_KEY, JSON.stringify(recents));
};

const selectIcon = (iconName: string) => {
  const cleanName = iconName.replace(/^mdi-/, '');
  addRecentIcon(cleanName);
  emit('update:modelValue', cleanName);
  closeModal();
};

const clearSelection = () => {
  emit('update:modelValue', '');
};

const filteredIcons = computed(() => {
  if (!searchQuery.value) return allIcons.value;
  
  const lowerQuery = searchQuery.value.toLowerCase();
  
  return allIcons.value.filter(icon => {
    if (icon.name.includes(lowerQuery)) return true;
    if (icon.tags.some(tag => tag.includes(lowerQuery))) return true;
    return false;
  });
});

const visibleIcons = computed(() => {
  return filteredIcons.value.slice(0, renderLimit.value);
});

const handleScroll = () => {
    const el = scrollContainer.value;
    if (el) {
        // Load more when scrolling reaches 500px from the bottom
        const isAtBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 500;
        if (isAtBottom && renderLimit.value < filteredIcons.value.length) {
            renderLimit.value += 100;
        }
    }
};

watch(searchQuery, () => {
    renderLimit.value = 150;
    if (scrollContainer.value) {
        scrollContainer.value.scrollTop = 0;
    }
});

watch(isOpen, (val) => {
  const body = document.body;
  if (val) {
    body.style.overflow = 'hidden';
  } else {
    body.style.overflow = '';
  }
});

onMounted(() => {
    loadIcons();
    const savedRecents = localStorage.getItem(RECENT_ICONS_KEY);
    if (savedRecents) {
        try {
            const parsed = JSON.parse(savedRecents);
            if (Array.isArray(parsed)) {
              recentIcons.value = parsed;
            }
        } catch (e) {
            console.error('error_parsing_recent_icons', e);
            localStorage.removeItem(RECENT_ICONS_KEY);
        }
    }
});
</script>

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
