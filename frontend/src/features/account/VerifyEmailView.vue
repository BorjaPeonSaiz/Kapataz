<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import { api } from "@/api/client";
import { problemMessageKey } from "@/api/problem";

const { t } = useI18n();
const route = useRoute();

type State = "working" | "success" | "failure" | "missing";
const state = ref<State>("working");
const failureKey = ref("account.verify.failure");

onMounted(async () => {
  const raw = route.query.token;
  const token = Array.isArray(raw) ? raw[0] : raw;
  if (!token) {
    state.value = "missing";
    return;
  }
  try {
    const { error, response } = await api.POST("/api/auth/verify-email", { body: { token } });
    if (!response.ok) failureKey.value = problemMessageKey(error);
    state.value = response.ok ? "success" : "failure";
  } catch {
    state.value = "failure";
  }
});
</script>

<template>
  <h1 class="mb-6 text-xl">{{ t("account.verify.title") }}</h1>
  <p v-if="state === 'working'" role="status" class="text-muted">
    {{ t("account.verify.working") }}
  </p>
  <template v-else-if="state === 'success'">
    <p role="status" class="rounded-md bg-success-bg p-3 text-success">
      {{ t("account.verify.success") }}
    </p>
    <RouterLink :to="{ name: 'login' }" class="mt-4 inline-flex min-h-11 items-center font-medium">
      {{ t("account.verify.goLogin") }}
    </RouterLink>
  </template>
  <p v-else role="alert" class="rounded-md bg-danger-bg p-3 text-danger">
    {{ state === "missing" ? t("account.verify.missingToken") : t(failureKey) }}
  </p>
</template>
