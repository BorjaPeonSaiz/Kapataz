import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const tokens = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");

const components = import.meta.glob("../**/*.vue", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("tokens de diseño", () => {
  it("la paleta lleva los hexadecimales exactos de la tabla, en claro y oscuro req('RNF-10')", () => {
    for (const hex of [
      "#FFF7ED",
      "#B04E24",
      "#D66C3A",
      "#3A2E28",
      "#1A1512",
      "#F0956A",
      "#8C7A6E",
    ]) {
      expect(tokens).toContain(hex);
    }
    expect(tokens).toContain(':root[data-theme="dark"]');
    expect(tokens).toContain("prefers-color-scheme: dark");
  });

  // Los contrastes de RNF-10 se calculan sobre los tokens: un hexadecimal suelto se los salta.
  it("los componentes no llevan hexadecimales sueltos req('RNF-10')", () => {
    const hex = /#[0-9a-fA-F]{3,8}\b/;
    const offenders = Object.entries(components)
      .filter(([, src]) => hex.test(src.replace(/href="#[\w-]+"/g, "")))
      .map(([file]) => file);
    expect(offenders).toEqual([]);
  });
});
