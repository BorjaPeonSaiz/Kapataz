<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    variant?: "primary" | "secondary" | "ghost" | "danger";
    type?: "button" | "submit" | "reset";
    /** El botón principal mide 48 px; el resto, 44 px. */
    size?: "md" | "lg";
    loading?: boolean;
    disabled?: boolean;
    block?: boolean;
  }>(),
  { variant: "primary", type: "button", size: "md", loading: false, disabled: false, block: false },
);

const emit = defineEmits<{ click: [event: MouseEvent] }>();

const inactive = computed(() => props.disabled || props.loading);

const variantClasses = {
  primary:
    "bg-primary text-on-primary border-2 border-transparent hover-hover:hover:bg-primary-hover active:bg-primary-hover",
  secondary:
    "bg-transparent text-text border-2 border-border-strong hover-hover:hover:bg-surface-alt active:bg-surface-alt",
  ghost:
    "bg-transparent text-primary border-2 border-transparent hover-hover:hover:bg-surface-alt active:bg-surface-alt",
  danger:
    "bg-danger text-on-danger border-2 border-transparent hover-hover:hover:opacity-90 active:opacity-90",
} as const;

function onClick(event: MouseEvent) {
  // aria-disabled no bloquea el clic por sí solo.
  if (inactive.value) {
    event.preventDefault();
    return;
  }
  emit("click", event);
}
</script>

<template>
  <button
    :type="type"
    :aria-disabled="inactive || undefined"
    :aria-busy="loading || undefined"
    class="focus-ring inline-flex items-center justify-center gap-2 rounded-full px-6 font-sans text-base font-semibold transition-colors duration-150 ease-out"
    :class="[
      variantClasses[variant],
      size === 'lg' ? 'min-h-12' : 'min-h-11',
      block ? 'w-full' : '',
      inactive ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
    ]"
    @click="onClick"
  >
    <svg
      v-if="loading"
      class="h-5 w-5 animate-spin motion-reduce:animate-none"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" opacity="0.25" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        stroke-width="3"
        stroke-linecap="round"
      />
    </svg>
    <slot />
  </button>
</template>
