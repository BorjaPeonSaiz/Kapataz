import js from "@eslint/js";
import globals from "globals";
import pluginVue from "eslint-plugin-vue";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/api/schema.d.ts", "scripts"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["**/*.vue"],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      "vue/multi-word-component-names": "off",
      "vue/require-default-prop": "off",
      // T-01: nunca v-html; la salida del LLM y de documentos importados es dato.
      "vue/no-v-html": "error",
    },
  },
  prettier,
);
