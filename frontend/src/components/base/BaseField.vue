<script setup lang="ts">
import { computed, useId } from "vue";

const props = withDefaults(
  defineProps<{
    label: string;
    type?: string;
    error?: string;
    hint?: string;
    autocomplete?: string;
    inputmode?: "text" | "numeric" | "decimal" | "email" | "tel" | "search" | "url";
    required?: boolean;
    disabled?: boolean;
    readonly?: boolean;
    placeholder?: string;
    /** Id de otro elemento que describe el campo (se suma a la ayuda y al error). */
    describedby?: string;
  }>(),
  { type: "text", required: false, disabled: false, readonly: false },
);

const model = defineModel<string>({ default: "" });

const uid = useId();
const inputId = `field-${uid}`;
const hintId = `${inputId}-hint`;
const errorId = `${inputId}-error`;

const describedBy = computed(() => {
  const ids = [props.describedby, props.hint ? hintId : "", props.error ? errorId : ""].filter(
    Boolean,
  );
  return ids.length ? ids.join(" ") : undefined;
});
</script>

<template>
  <div class="flex flex-col gap-1">
    <label :for="inputId" class="text-sm font-medium text-text">{{ label }}</label>
    <input
      :id="inputId"
      v-model="model"
      :type="type"
      :autocomplete="autocomplete"
      :inputmode="inputmode"
      :required="required || undefined"
      :disabled="disabled"
      :readonly="readonly"
      :placeholder="placeholder"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
      class="focus-ring min-h-11 w-full rounded-md border-2 bg-surface px-4 font-sans text-base text-text placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-60 read-only:bg-surface-alt"
      :class="error ? 'border-danger' : 'border-border-strong'"
    />
    <p v-if="hint" :id="hintId" class="text-sm text-muted">{{ hint }}</p>
    <p v-if="error" :id="errorId" class="flex items-start gap-1 text-sm text-danger">
      <svg
        class="mt-0.5 h-4 w-4 shrink-0"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm-1-11a1 1 0 1 1 2 0v4a1 1 0 1 1-2 0V7Zm1 8a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
          clip-rule="evenodd"
        />
      </svg>
      <span>{{ error }}</span>
    </p>
  </div>
</template>
