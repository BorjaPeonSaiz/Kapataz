<script setup lang="ts">
import { RouterView } from "vue-router";
import { useI18n } from "vue-i18n";

const { t } = useI18n();
</script>

<template>
  <main
    id="contenido"
    class="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-4 py-8 sm:px-6"
  >
    <p class="mb-8 font-display text-2xl font-bold text-primary">{{ t("app.name") }}</p>
    <div class="rounded-md border border-border bg-surface p-4 shadow-1 sm:p-6">
      <RouterView />
    </div>
  </main>
</template>
