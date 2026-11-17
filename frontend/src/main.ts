import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "@/app/App.vue";
import { createAppRouter } from "@/app/router";
import { createAppI18n } from "@/i18n";
import "@/styles/main.css";

createApp(App).use(createPinia()).use(createAppRouter()).use(createAppI18n()).mount("#app");
