<script setup lang="ts">
import { RouterView } from "vue-router";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
</script>

<template>
  <a
    href="#contenido"
    class="sr-only-focusable focus-ring left-2 top-2 z-10 rounded-full bg-surface px-4 py-2 text-text"
  >
    {{ t("app.skipToContent") }}
  </a>
  <RouterView />
</template>
