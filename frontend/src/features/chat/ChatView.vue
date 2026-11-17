<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import BaseButton from "@/components/base/BaseButton.vue";
import BaseField from "@/components/base/BaseField.vue";
import ChatBubble from "@/components/base/ChatBubble.vue";
import { useChatStore } from "@/stores/chat";
import { useSessionStore } from "@/stores/session";

const { t } = useI18n();
const router = useRouter();
const chat = useChatStore();
const session = useSessionStore();

const draft = ref("");
const scroller = ref<HTMLElement | null>(null);
const loggingOut = ref(false);

// Asistente en pausa: campo y botón deshabilitados, con el motivo asociado.
const unavailable = computed(
  () => chat.problem === "unavailable" || chat.problem === "subscription",
);
const problemText = computed(() => {
  switch (chat.problem) {
    case "unavailable":
      return t("chat.unavailable");
    case "subscription":
      return t("errors.problem.subscriptionInactive");
    case "offline":
      return t("chat.offline");
    case "server":
      return t("errors.server");
    default:
      return "";
  }
});

async function submit() {
  const text = draft.value;
  if (!text.trim() || chat.sending || unavailable.value) return;
  draft.value = "";
  await chat.send(text);
}

async function logout() {
  loggingOut.value = true;
  try {
    await session.logout();
  } finally {
    chat.reset();
    loggingOut.value = false;
    await router.replace({ name: "login" });
  }
}

// Mantiene a la vista lo último que llega, sin animaciones de desplazamiento.
watch(
  () => [chat.messages.length, chat.pending],
  async () => {
    await nextTick();
    scroller.value?.scrollTo({ top: scroller.value.scrollHeight });
  },
);
</script>

<template>
  <div class="mx-auto flex h-dvh w-full max-w-chat flex-col">
    <header class="flex items-center justify-between gap-2 px-4 py-2 sm:px-6">
      <h1 class="text-xl">{{ t("chat.title") }}</h1>
      <BaseButton variant="ghost" :loading="loggingOut" @click="logout">
        {{ loggingOut ? t("chat.logoutWorking") : t("chat.logout") }}
      </BaseButton>
    </header>

    <main id="contenido" ref="scroller" class="flex-1 overflow-y-auto px-4 pb-4 sm:px-6">
      <p
        v-if="chat.messages.length === 0 && chat.pending === null"
        class="py-8 text-center text-muted"
      >
        {{ t("chat.empty") }}
      </p>
      <!-- Región viva: solo se añaden mensajes completos, así que el lector de pantalla
           los lee una vez y no token a token (el texto en curso va fuera, aria-hidden). -->
      <ol
        role="log"
        :aria-label="t('chat.log')"
        aria-live="polite"
        aria-relevant="additions"
        :aria-busy="chat.sending"
        class="flex list-none flex-col gap-3 p-0"
      >
        <li v-for="m in chat.messages" :key="m.id">
          <ChatBubble :role="m.role" :failed="m.failed">
            <span class="sr-only"
              >{{ m.role === "user" ? t("chat.you") : t("chat.assistant") }}:
            </span>
            {{ m.text }}
            <span v-if="m.failed" class="mt-2 block text-sm text-danger">{{
              t("chat.errorBubble")
            }}</span>
          </ChatBubble>
        </li>
      </ol>
      <div v-if="chat.pending !== null" class="mt-3" aria-hidden="true">
        <ChatBubble role="assistant" :typing="chat.pending === ''">{{ chat.pending }}</ChatBubble>
      </div>
      <p v-if="chat.sending" role="status" class="sr-only">{{ t("chat.responding") }}</p>
    </main>

    <p
      v-if="problemText"
      id="chat-problem"
      role="alert"
      class="mx-4 mb-2 rounded-md bg-warning-bg p-3 text-sm text-warning sm:mx-6"
      :class="{ 'bg-danger-bg text-danger': chat.problem === 'server' }"
    >
      {{ problemText }}
    </p>

    <form
      class="flex items-end gap-2 border-t border-border bg-surface px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6"
      @submit.prevent="submit"
    >
      <div class="min-w-0 flex-1">
        <BaseField
          v-model="draft"
          :label="t('chat.input')"
          :placeholder="unavailable ? t('chat.unavailableHint') : t('chat.placeholder')"
          autocomplete="off"
          :disabled="unavailable"
          :describedby="unavailable ? 'chat-problem' : undefined"
        />
      </div>
      <BaseButton type="submit" size="lg" :loading="chat.sending" :disabled="unavailable">
        {{ chat.sending ? t("chat.sending") : t("chat.send") }}
      </BaseButton>
    </form>
  </div>
</template>
