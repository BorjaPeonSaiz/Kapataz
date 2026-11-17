import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { api } from "@/api/client";
import { PROBLEM, problemType } from "@/api/problem";
import { readSse, toChatEvent } from "@/features/chat/sse";
import { useSessionStore } from "@/stores/session";

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  failed?: boolean;
}

export type ChatProblem = "offline" | "unavailable" | "subscription" | "server" | null;

export const useChatStore = defineStore("chat", () => {
  const messages = ref<ChatMessage[]>([]);
  // Texto del asistente que está llegando. null = no hay respuesta en curso.
  const pending = ref<string | null>(null);
  const problem = ref<ChatProblem>(null);
  const sending = computed(() => pending.value !== null);
  let nextId = 1;

  function finishPending(failed: boolean) {
    const text = pending.value ?? "";
    pending.value = null;
    if (text || failed) {
      messages.value.push({ id: nextId++, role: "assistant", text, failed });
    }
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || sending.value) return;
    problem.value = null;
    messages.value.push({ id: nextId++, role: "user", text: message });
    pending.value = "";

    try {
      const { data, error, response } = await api.POST("/api/chat", {
        body: { message },
        parseAs: "stream",
      });
      if (response.status === 401) {
        pending.value = null;
        useSessionStore().clear();
        return;
      }
      if (!response.ok || !data) {
        pending.value = null;
        if (problemType(error) === PROBLEM.subscriptionInactive) problem.value = "subscription";
        else problem.value = response.status >= 500 ? "unavailable" : "server";
        return;
      }
      for await (const ev of readSse(data)) {
        const chatEvent = toChatEvent(ev);
        if (chatEvent.kind === "token") pending.value = (pending.value ?? "") + chatEvent.text;
        else if (chatEvent.kind === "done") break;
        else if (chatEvent.kind === "error") {
          problem.value = "unavailable";
          finishPending(true);
          return;
        }
      }
      finishPending(false);
    } catch {
      // Sin red o corte a mitad de respuesta.
      problem.value = "offline";
      finishPending((pending.value ?? "") !== "");
    }
  }

  function reset() {
    messages.value = [];
    pending.value = null;
    problem.value = null;
  }

  return { messages, pending, problem, sending, send, reset };
});
