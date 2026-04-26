<script setup lang="ts">
import type { PropType } from 'vue';

defineOptions({
  name: 'TreeView'
});

interface TreeItem {
    id: string;
    name: string;
    icon?: string;
    selected: boolean;
    isOpen?: boolean;
    children?: TreeItem[];
    details?: string;
    indeterminate?: boolean;
    textClass?: string;
}

defineProps({
    items: {
        type: Array as PropType<TreeItem[]>,
        default: () => [],
    },
    level: {
        type: Number,
        default: 0
    }
});

const emit = defineEmits(['update:modelValue']);

const toggle = (item: TreeItem) => {
    if (item.children) {
        item.isOpen = !item.isOpen;
    }
};

const handleCheckboxChange = (item: TreeItem) => {
    item.indeterminate = false;
    if (item.children) {
        updateChildrenSelection(item, item.selected);
    }
    emit('update:modelValue', item);
};

const onChildChange = (item: TreeItem) => {
    if (item.children) {
        const allSelected = item.children.every((c: TreeItem) => c.selected);
        const someSelected = item.children.some((c: TreeItem) => c.selected || c.indeterminate);
        item.selected = allSelected;
        item.indeterminate = !allSelected && someSelected;
    }
    emit('update:modelValue', item);
};

const updateChildrenSelection = (item: TreeItem, selected: boolean) => {
    if (item.children) {
        item.children.forEach((child: TreeItem) => {
            child.selected = selected;
            child.indeterminate = false;
            updateChildrenSelection(child, selected);
        });
    }
};
</script>

<template>
  <div
    v-for="item in items"
    :key="item.id"
  >
    <div
      class="flex items-center py-1 hover:bg-gray-800 rounded"
      :style="{ 'padding-left': level * 1.5 + 'rem' }"
    >
      <input
        v-model="item.selected"
        type="checkbox"
        :indeterminate.prop="item.indeterminate"
        class="mr-2"
        @change="handleCheckboxChange(item)"
      >
      <div
        class="cursor-pointer flex-grow"
        @click="toggle(item)"
      >
        <i
          v-if="item.children && item.children.length"
          class="mdi w-5 inline-block text-center"
          :class="item.isOpen ? 'mdi-chevron-down' : 'mdi-chevron-right'"
        />
        <span
          v-else
          class="w-5 inline-block"
        />
        <i
          v-if="item.icon"
          class="mdi mr-2"
          :class="`mdi-${item.icon}`"
        />
        <span
          class="font-semibold"
          :class="item.textClass"
        >{{ item.name }}</span>
        <span
          v-if="item.details"
          class="text-sm text-gray-500 ml-2"
        >{{ item.details }}</span>
      </div>
    </div>
    <div v-if="item.children && item.children.length && item.isOpen">
      <TreeView 
        :items="item.children" 
        :level="level + 1"
        @update:model-value="onChildChange(item)"
      />
    </div>
  </div>
</template>