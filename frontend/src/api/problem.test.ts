import { describe, expect, it } from "vitest";
import { createAppI18n } from "@/i18n";
import { PROBLEM, problemMessageKey } from "./problem";

describe("problemMessageKey", () => {
  const i18n = createAppI18n();

  it("cada tipo de error del contrato tiene mensaje en es-ES req('RNF-11')", () => {
    for (const type of Object.values(PROBLEM)) {
      const key = problemMessageKey({ type });
      expect(key).not.toBe("errors.problem.unknown");
      expect(i18n.global.te(key)).toBe(true);
    }
  });

  it("un tipo desconocido o sin tipo usa el mensaje genérico req('RNF-11')", () => {
    expect(problemMessageKey({ type: "/problemas/otro" })).toBe("errors.problem.unknown");
    expect(problemMessageKey(undefined)).toBe("errors.problem.unknown");
    expect(i18n.global.te("errors.problem.unknown")).toBe(true);
  });
});
