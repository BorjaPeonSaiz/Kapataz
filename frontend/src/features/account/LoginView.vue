<script setup lang="ts">
import { ref } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import BaseButton from "@/components/base/BaseButton.vue";
import BaseField from "@/components/base/BaseField.vue";
import { api } from "@/api/client";
import { problemMessageKey } from "@/api/problem";
import { useSessionStore } from "@/stores/session";

const { t } = useI18n();
const router = useRouter();
const session = useSessionStore();

const email = ref("");
const password = ref("");
const emailError = ref("");
const passwordError = ref("");
const formError = ref("");
const busy = ref(false);

async function submit() {
  emailError.value = email.value.trim() ? "" : t("account.validation.emailRequired");
  passwordError.value = password.value ? "" : t("account.validation.passwordRequired");
  formError.value = "";
  if (emailError.value || passwordError.value) return;

  busy.value = true;
  try {
    const { error, response } = await api.POST("/api/auth/login", {
      body: { email: email.value.trim(), password: password.value },
    });
    if (response.ok) {
      await session.fetchMe();
      await router.replace({ name: "chat" });
    } else {
      formError.value = t(problemMessageKey(error));
    }
  } catch {
    formError.value = t("errors.network");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <h1 class="mb-6 text-xl">{{ t("account.login.title") }}</h1>
  <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
    <BaseField
      v-model="email"
      :label="t('account.fields.email')"
      type="email"
      autocomplete="email"
      inputmode="email"
      required
      :error="emailError"
    />
    <BaseField
      v-model="password"
      :label="t('account.fields.password')"
      type="password"
      autocomplete="current-password"
      required
      :error="passwordError"
    />
    <p v-if="formError" role="alert" class="rounded-md bg-danger-bg p-3 text-sm text-danger">
      {{ formError }}
    </p>
    <BaseButton type="submit" size="lg" block :loading="busy">
      {{ busy ? t("account.login.submitting") : t("account.login.submit") }}
    </BaseButton>
  </form>
  <p class="mt-6 text-sm text-muted">
    {{ t("account.login.noAccount") }}
    <RouterLink :to="{ name: 'register' }" class="inline-flex min-h-11 items-center font-medium">
      {{ t("account.login.goRegister") }}
    </RouterLink>
  </p>
</template>
