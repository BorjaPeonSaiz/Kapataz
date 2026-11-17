<script setup lang="ts">
import { useI18n } from "vue-i18n";

withDefaults(
  defineProps<{
    role: "user" | "assistant";
    /** Asistente escribiendo: tres puntos con texto accesible. */
    typing?: boolean;
    /** Respuesta que no se ha podido terminar. */
    failed?: boolean;
  }>(),
  { typing: false, failed: false },
);

const { t } = useI18n();
</script>

<template>
  <div class="flex w-full" :class="role === 'user' ? 'justify-end' : 'justify-start'">
    <div
      class="max-w-[85%] whitespace-pre-wrap break-words rounded-md px-4 py-3 text-base text-text"
      :class="[
        role === 'user' ? 'bg-surface-alt' : 'bg-surface shadow-1',
        failed ? 'border-2 border-danger' : role === 'user' ? '' : 'border border-border',
      ]"
      :data-role="role"
    >
      <span v-if="typing" class="flex items-center gap-1 py-1">
        <span class="sr-only">{{ t("chat.typing") }}</span>
        <span
          v-for="n in 3"
          :key="n"
          aria-hidden="true"
          class="h-2 w-2 animate-pulse rounded-full bg-muted motion-reduce:animate-none"
          :style="{ animationDelay: `${(n - 1) * 150}ms` }"
        />
      </span>
      <slot v-else />
    </div>
  </div>
</template>
