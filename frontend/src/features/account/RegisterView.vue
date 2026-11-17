<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { useI18n } from "vue-i18n";
import BaseButton from "@/components/base/BaseButton.vue";
import BaseField from "@/components/base/BaseField.vue";
import { api } from "@/api/client";
import { PROBLEM, problemMessageKey, problemType } from "@/api/problem";

const { t } = useI18n();

const email = ref("");
const password = ref("");
const emailError = ref("");
const passwordError = ref("");
const formError = ref("");
const closed = ref(false);
const done = ref(false);
const busy = ref(false);

async function submit() {
  emailError.value = email.value.trim() ? "" : t("account.validation.emailRequired");
  passwordError.value = password.value ? "" : t("account.validation.passwordRequired");
  formError.value = "";
  closed.value = false;
  if (emailError.value || passwordError.value) return;

  busy.value = true;
  try {
    const { error, response } = await api.POST("/api/auth/register", {
      body: { email: email.value.trim(), password: password.value },
    });
    if (response.ok) {
      done.value = true;
    } else if (problemType(error) === PROBLEM.registrationClosed) {
      closed.value = true;
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
  <h1 class="mb-6 text-xl">{{ t("account.register.title") }}</h1>
  <p v-if="done" role="status" class="rounded-md bg-success-bg p-3 text-success">
    {{ t("account.register.done") }}
  </p>
  <form v-else class="flex flex-col gap-4" novalidate @submit.prevent="submit">
    <p v-if="closed" role="alert" class="rounded-md bg-warning-bg p-3 text-warning">
      {{ t("errors.problem.registrationClosed") }}
    </p>
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
      autocomplete="new-password"
      required
      :error="passwordError"
    />
    <p v-if="formError" role="alert" class="rounded-md bg-danger-bg p-3 text-sm text-danger">
      {{ formError }}
    </p>
    <BaseButton type="submit" size="lg" block :loading="busy">
      {{ busy ? t("account.register.submitting") : t("account.register.submit") }}
    </BaseButton>
  </form>
  <p class="mt-6 text-sm text-muted">
    {{ t("account.register.haveAccount") }}
    <RouterLink :to="{ name: 'login' }" class="inline-flex min-h-11 items-center font-medium">
      {{ t("account.register.goLogin") }}
    </RouterLink>
  </p>
</template>
