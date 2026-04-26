<script setup lang="ts">
import { computed } from 'vue';

// A clean interface definition for the props
interface Props {
  modelValue: boolean | (string | number | Record<string, unknown>)[];
  value?: string | number | Record<string, unknown>;
  disabled?: boolean;
}

// `withDefaults` is used to set default values for the props.
// This fixes the warnings and is the recommended approach.
const props = withDefaults(defineProps<Props>(), {
  modelValue: false,
  disabled: false,
  value: undefined
});

const emit = defineEmits(['update:modelValue']);

const isChecked = computed(() => {
  if (Array.isArray(props.modelValue)) {
    if (props.value === undefined) return false;
    return props.modelValue.includes(props.value);
  }
  return !!props.modelValue;
});

function handleChange(event: Event) {
  const checked = (event.target as HTMLInputElement).checked;
  if (Array.isArray(props.modelValue)) {
    if (props.value === undefined) return;
    const newValue = [...props.modelValue];
    if (checked) {
      newValue.push(props.value);
    } else {
      const index = newValue.indexOf(props.value);
      if (index > -1) {
        newValue.splice(index, 1);
      }
    }
    emit('update:modelValue', newValue);
  } else {
    emit('update:modelValue', checked);
  }
}
</script>

<template>
  <div class="relative inline-flex items-center">
    <input
      type="checkbox"
      :value="value"
      :checked="isChecked"
      :disabled="disabled"
      class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10 peer disabled:cursor-not-allowed"
      @change="handleChange"
    >
    <div class="w-11 h-6 bg-gray-600 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-ha-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-500" />
  </div>
</template>