import { ref } from "vue";
import { defineStore } from "pinia";
import { api } from "@/api/client";
import type { paths } from "@/api/schema";

type Me = paths["/api/auth/me"]["get"]["responses"][200]["content"]["application/json"];

export const useSessionStore = defineStore("session", () => {
  const user = ref<Me | null>(null);
  const loaded = ref(false);

  async function fetchMe(): Promise<boolean> {
    try {
      const { data } = await api.GET("/api/auth/me");
      user.value = data ?? null;
    } catch {
      user.value = null;
    }
    loaded.value = true;
    return user.value !== null;
  }

  function clear() {
    user.value = null;
    loaded.value = true;
  }

  async function logout() {
    try {
      await api.POST("/api/auth/logout");
    } finally {
      clear();
    }
  }

  return { user, loaded, fetchMe, clear, logout };
});
