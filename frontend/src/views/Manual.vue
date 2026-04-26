<script setup lang="ts">
import { useI18n } from '../i18n';
const { t } = useI18n();
</script>

<template>
  <div class="flex h-full items-center justify-center pb-20">
    <div class="card max-w-lg w-full text-center space-y-6 p-10">
      <i class="mdi mdi-book-open-page-variant-outline text-6xl text-blue-500" />
      <h2 class="text-2xl font-bold text-gray-200">
        {{ t('nav.manual') }}
      </h2>
      <p class="text-gray-400">
        The documentation has been extracted into a modern, searchable format. 
        You can find it in the <code>docs/</code> folder of the repository.
      </p>
      <a
        href="https://github.com/steelcuts/ir2mqtt/tree/main/docs"
        target="_blank"
        class="btn btn-primary w-full flex justify-center items-center gap-2"
      >
        Open Documentation <i class="mdi mdi-open-in-new" />
      </a>
    </div>
  </div>
</template>
