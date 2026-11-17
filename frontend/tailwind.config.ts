import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

// Solo referencia los tokens de src/styles/tokens.css: aquí no hay hexadecimales.
const token = (name: string) => `var(--color-${name})`;

export default {
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    colors: {
      transparent: "transparent",
      current: "currentColor",
      bg: token("bg"),
      surface: token("surface"),
      "surface-alt": token("surface-alt"),
      text: token("text"),
      muted: token("text-muted"),
      border: token("border"),
      "border-strong": token("border-strong"),
      brand: token("brand"),
      accent: token("accent"),
      primary: token("primary"),
      "primary-hover": token("primary-hover"),
      "on-primary": token("on-primary"),
      "info-bg": token("info-bg"),
      danger: token("danger"),
      "on-danger": token("on-danger"),
      "danger-bg": token("danger-bg"),
      warning: token("warning"),
      "warning-bg": token("warning-bg"),
      success: token("success"),
      "success-bg": token("success-bg"),
      draft: token("draft"),
      "draft-bg": token("draft-bg"),
      issued: token("issued"),
      "on-issued": token("on-issued"),
      "issued-bg": token("issued-bg"),
      focus: token("focus"),
    },
    fontFamily: {
      sans: [
        "Inter Variable",
        "Inter",
        "system-ui",
        "-apple-system",
        "Segoe UI",
        "Roboto",
        "sans-serif",
      ],
      display: ["Poppins", "Inter Variable", "Inter", "system-ui", "sans-serif"],
    },
    fontSize: {
      xs: ["0.75rem", { lineHeight: "1rem", fontWeight: "500" }],
      sm: ["0.875rem", { lineHeight: "1.25rem" }],
      base: ["1rem", { lineHeight: "1.5rem" }],
      lg: ["1.125rem", { lineHeight: "1.625rem", fontWeight: "600" }],
      xl: ["1.375rem", { lineHeight: "1.75rem", fontWeight: "700" }],
      "2xl": ["1.75rem", { lineHeight: "2.125rem", fontWeight: "700" }],
    },
    borderRadius: {
      none: "0",
      sm: "var(--radius-sm)",
      md: "var(--radius-md)",
      lg: "var(--radius-lg)",
      full: "var(--radius-full)",
    },
    boxShadow: {
      none: "none",
      1: "var(--shadow-1)",
      2: "var(--shadow-2)",
      3: "var(--shadow-3)",
    },
    extend: {
      maxWidth: { column: "1120px", chat: "720px" },
      transitionDuration: { DEFAULT: "150ms" },
    },
  },
  plugins: [
    // Hover solo con puntero: en táctil no se queda pegado.
    plugin(({ addVariant }) => addVariant("hover-hover", "@media (hover: hover)")),
  ],
} satisfies Config;
