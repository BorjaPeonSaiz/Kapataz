import { createI18n } from "vue-i18n";
import esES from "./es-ES";

export type MessageSchema = typeof esES;

export function createAppI18n() {
  return createI18n<[MessageSchema], "es-ES">({
    legacy: false,
    locale: "es-ES",
    fallbackLocale: "es-ES",
    messages: { "es-ES": esES },
  });
}
