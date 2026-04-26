<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import TreeView from './TreeView.vue';
import type { Bridge } from '../types';
import { useI18n } from '../i18n';

const props = defineProps({
  modelValue: {
    type: Array as () => string[],
    default: () => []
  },
  bridges: {
    type: Array as () => Bridge[],
    default: () => []
  },
  type: {
    type: String,
    default: 'target' // 'target' or 'source'
  },
  compact: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['update:modelValue']);

const { t } = useI18n();

const title = computed(() => props.type === 'source' ? t('bridgeSelector.sourceTitle') : t('bridgeSelector.targetTitle'));

const description = computed(() => {
  return props.type === 'source' 
    ? t('bridgeSelector.sourceDesc') 
    : t('bridgeSelector.targetDesc');
});

interface TreeNode {
    id: string;
    name: string;
    details?: string;
    textClass?: string;
    icon: string;
    selected: boolean;
    indeterminate?: boolean;
    isOpen: boolean;
    children?: TreeNode[];
}

const localTree = ref<TreeNode[]>([]);

const buildTree = () => {
    localTree.value = props.bridges.map(bridge => {
        const channels = props.type === 'source' ? bridge.receivers : bridge.transmitters;
        const icon = props.type === 'source' ? 'download' : 'upload';
        
        const bridgeSelected = props.modelValue.includes(bridge.id);
        
        const children = (channels || []).map(ch => {
            const chId = `${bridge.id}:${ch.id}`;
            return {
                id: chId,
                name: ch.id,
                icon: icon,
                selected: bridgeSelected || props.modelValue.includes(chId),
                isOpen: false
            };
        });

        const allChildrenSelected = children.length > 0 && children.every(c => c.selected);
        const someChildrenSelected = children.some(c => c.selected);
        const isSelected = bridgeSelected || allChildrenSelected;

        return {
            id: bridge.id,
            name: bridge.name,
            details: `(${bridge.status})`,
            textClass: bridge.status === 'online' ? 'text-green-400' : 'text-gray-500',
            icon: 'lan-connect',
            selected: isSelected,
            indeterminate: !isSelected && someChildrenSelected,
            isOpen: true,
            children: children
        };
    });
};

watch(() => [props.bridges, props.modelValue], buildTree, { immediate: true, deep: true });

const onTreeUpdate = () => {
    const newTargets: string[] = [];
    localTree.value.forEach(bridgeNode => {
        if (bridgeNode.selected) {
            newTargets.push(bridgeNode.id);
        } else if (bridgeNode.children) {
            bridgeNode.children.forEach((chNode: TreeNode) => {
                if (chNode.selected) {
                    newTargets.push(chNode.id);
                }
            });
        }
    });
    
    const currentSorted = [...props.modelValue].sort();
    const newSorted = [...newTargets].sort();
    const changed = currentSorted.length !== newSorted.length || currentSorted.some((v, i) => v !== newSorted[i]);
    
    if (changed) {
        emit('update:modelValue', newTargets);
    }
};
</script>

<template>
  <div :class="compact ? '' : 'border-t border-gray-600 pt-4'">
    <label class="block text-sm font-medium text-gray-300 mb-1">{{ title }}</label>
    <p
      v-if="!compact"
      class="text-xs text-gray-400 pb-2"
    >
      {{ description }}
    </p>

    <div class="bg-gray-800 rounded p-2 border border-gray-600 max-h-60 overflow-y-auto">
      <div
        v-if="bridges.length === 0"
        class="text-gray-500 text-sm p-2"
      >
        {{ t('bridgeSelector.noBridges') }}
      </div>
      <TreeView
        v-else
        :items="localTree"
        @update:model-value="onTreeUpdate"
      />
    </div>
  </div>
</template>