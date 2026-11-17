import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import BaseField from "./BaseField.vue";

describe("BaseField", () => {
  it("etiqueta siempre visible y asociada al campo req('RNF-10')", () => {
    const w = mount(BaseField, { props: { label: "Correo electrónico" } });
    const label = w.get("label");
    expect(label.classes()).not.toContain("sr-only");
    expect(label.attributes("for")).toBe(w.get("input").attributes("id"));
  });

  it("el error se enlaza con aria-describedby y marca aria-invalid req('RNF-10')", () => {
    const w = mount(BaseField, { props: { label: "Correo", error: "Escribe tu correo." } });
    const input = w.get("input");
    const errorId = input.attributes("aria-describedby");
    expect(input.attributes("aria-invalid")).toBe("true");
    expect(errorId).toBeTruthy();
    expect(w.get(`[id="${errorId}"]`).text()).toContain("Escribe tu correo.");
  });

  it("sin error no hay aria-invalid ni aria-describedby req('RNF-10')", () => {
    const w = mount(BaseField, { props: { label: "Correo" } });
    expect(w.get("input").attributes("aria-invalid")).toBeUndefined();
    expect(w.get("input").attributes("aria-describedby")).toBeUndefined();
  });

  it("ayuda y error se describen los dos req('RNF-10')", () => {
    const w = mount(BaseField, { props: { label: "Correo", hint: "Ayuda", error: "Error" } });
    expect(w.get("input").attributes("aria-describedby")?.split(" ")).toHaveLength(2);
  });

  it("campo con altura mínima de 44 px y foco visible req('RNF-09') req('RNF-10')", () => {
    const input = mount(BaseField, { props: { label: "Correo" } }).get("input");
    expect(input.classes()).toContain("min-h-11");
    expect(input.classes()).toContain("focus-ring");
  });

  it("error: borde danger; reposo: borde fuerte req('RNF-10')", () => {
    const withError = mount(BaseField, { props: { label: "A", error: "x" } });
    const idle = mount(BaseField, { props: { label: "A" } });
    expect(withError.get("input").classes()).toContain("border-danger");
    expect(idle.get("input").classes()).toContain("border-border-strong");
  });

  // Sin req: comportamiento funcional del componente, no accesibilidad (RNF-10).
  it("v-model actualiza el valor", async () => {
    const w = mount(BaseField, {
      props: {
        label: "Correo",
        modelValue: "",
        "onUpdate:modelValue": (v: string | undefined) => w.setProps({ modelValue: v }),
      },
    });
    await w.get("input").setValue("a@b.es");
    expect((w.get("input").element as HTMLInputElement).value).toBe("a@b.es");
  });
});
