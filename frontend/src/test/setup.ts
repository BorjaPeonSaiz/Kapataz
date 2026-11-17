import { config } from "@vue/test-utils";
import { createAppI18n } from "@/i18n";

config.global.plugins = [createAppI18n()];
