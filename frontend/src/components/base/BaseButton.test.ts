import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import BaseButton from "./BaseButton.vue";

describe("BaseButton", () => {
  it("botón con foco visible req('RNF-10')", () => {
    const w = mount(BaseButton, { slots: { default: "Entrar" } });
    expect(w.classes()).toContain("focus-ring");
  });

  it("objetivo táctil de 44 px (48 px el grande) req('RNF-09')", () => {
    expect(mount(BaseButton).classes()).toContain("min-h-11");
    expect(mount(BaseButton, { props: { size: "lg" } }).classes()).toContain("min-h-12");
  });

  it("botón en píldora y variante primaria por defecto req('RNF-10')", () => {
    const w = mount(BaseButton);
    expect(w.classes()).toContain("rounded-full");
    expect(w.classes()).toContain("bg-primary");
  });

  it.each([
    ["secondary", "border-border-strong"],
    ["ghost", "text-primary"],
    ["danger", "bg-danger"],
  ] as const)("variante %s req('RNF-10')", (variant, cls) => {
    expect(mount(BaseButton, { props: { variant } }).classes()).toContain(cls);
  });

  it("deshabilitado usa aria-disabled y no emite clic req('RNF-10')", async () => {
    const w = mount(BaseButton, { props: { disabled: true } });
    expect(w.attributes("aria-disabled")).toBe("true");
    await w.trigger("click");
    expect(w.emitted("click")).toBeUndefined();
  });

  it("cargando muestra spinner, aria-busy y no es clicable req('RNF-10')", async () => {
    const w = mount(BaseButton, { props: { loading: true } });
    expect(w.attributes("aria-busy")).toBe("true");
    expect(w.attributes("aria-disabled")).toBe("true");
    expect(w.find("svg[aria-hidden='true']").exists()).toBe(true);
    await w.trigger("click");
    expect(w.emitted("click")).toBeUndefined();
  });

  // Sin req: comportamiento funcional del componente, no accesibilidad (RNF-10).
  it("activo emite el clic", async () => {
    const w = mount(BaseButton);
    await w.trigger("click");
    expect(w.emitted("click")).toHaveLength(1);
  });
});
