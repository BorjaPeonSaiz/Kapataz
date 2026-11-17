import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import ChatBubble from "./ChatBubble.vue";

describe("ChatBubble", () => {
  it("burbuja del usuario, a la derecha y con fondo surface-alt req('RNF-10')", () => {
    const w = mount(ChatBubble, { props: { role: "user" }, slots: { default: "Hola" } });
    expect(w.classes()).toContain("justify-end");
    expect(w.get("[data-role]").classes()).toContain("bg-surface-alt");
    expect(w.text()).toBe("Hola");
  });

  it("burbuja del asistente, a la izquierda y con borde req('RNF-10')", () => {
    const w = mount(ChatBubble, { props: { role: "assistant" }, slots: { default: "Hola" } });
    expect(w.classes()).toContain("justify-start");
    expect(w.get("[data-role]").classes()).toContain("bg-surface");
    expect(w.get("[data-role]").classes()).toContain("border");
  });

  it("escribiendo: tres puntos decorativos y texto accesible req('RNF-10')", () => {
    const w = mount(ChatBubble, { props: { role: "assistant", typing: true } });
    expect(w.findAll("[aria-hidden='true']")).toHaveLength(3);
    expect(w.get(".sr-only").text()).toBe("El asistente está escribiendo");
  });

  it("respuesta fallida: borde danger req('RNF-10')", () => {
    const w = mount(ChatBubble, {
      props: { role: "assistant", failed: true },
      slots: { default: "x" },
    });
    expect(w.get("[data-role]").classes()).toContain("border-danger");
  });
});
