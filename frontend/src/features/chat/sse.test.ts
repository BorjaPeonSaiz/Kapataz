import { describe, expect, it } from "vitest";
import { readSse, SseParser, toChatEvent } from "./sse";

function streamOf(chunks: Array<string | Uint8Array>): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(typeof c === "string" ? enc.encode(c) : c);
      controller.close();
    },
  });
}

async function collect(chunks: Array<string | Uint8Array>) {
  const out = [];
  for await (const ev of readSse(streamOf(chunks))) out.push(toChatEvent(ev));
  return out;
}

describe("SseParser", () => {
  it("evento completo en un solo trozo req('RF-CO-01')", () => {
    const p = new SseParser();
    expect(p.feed('event: token\ndata: {"text":"Hola"}\n\n')).toEqual([
      { event: "token", data: '{"text":"Hola"}' },
    ]);
  });

  it("evento partido entre lecturas, también por la mitad de una palabra req('RF-CO-01')", () => {
    const p = new SseParser();
    expect(p.feed("event: tok")).toEqual([]);
    expect(p.feed('en\ndata: {"te')).toEqual([]);
    expect(p.feed('xt":"Ho')).toEqual([]);
    expect(p.feed('la"}\n')).toEqual([]);
    expect(p.feed("\n")).toEqual([{ event: "token", data: '{"text":"Hola"}' }]);
  });

  it("varios eventos en un mismo trozo req('RF-CO-01')", () => {
    const p = new SseParser();
    const evs = p.feed(
      'event: token\ndata: {"text":"a"}\n\nevent: token\ndata: {"text":"b"}\n\nevent: done\ndata: {}\n\n',
    );
    expect(evs.map((e) => e.event)).toEqual(["token", "token", "done"]);
  });

  it("saltos CRLF, incluso con el CR y el LF en trozos distintos req('RF-CO-01')", () => {
    const p = new SseParser();
    expect(p.feed("event: done\r")).toEqual([]);
    expect(p.feed("\ndata: {}\r\n\r")).toEqual([{ event: "done", data: "{}" }]);
    expect(p.feed("\n")).toEqual([]);
  });

  it("ignora comentarios y une varias líneas data req('RF-CO-01')", () => {
    const p = new SseParser();
    expect(p.feed(": keep-alive\n\ndata: uno\ndata: dos\n\n")).toEqual([
      { event: "message", data: "uno\ndos" },
    ]);
  });

  it("un evento sin terminar no se emite req('RF-CO-01')", () => {
    expect(new SseParser().feed('event: token\ndata: {"text":"x"}\n')).toEqual([]);
  });
});

describe("readSse", () => {
  it("lee eventos de un ReadableStream con trozos cortados req('RF-CO-01')", async () => {
    const out = await collect([
      "event: token\nda",
      'ta: {"text":"Ho"}\n\nevent: token\ndata: {"text":"la"}\n',
      "\n",
    ]);
    expect(out).toEqual([
      { kind: "token", text: "Ho" },
      { kind: "token", text: "la" },
    ]);
  });

  it("no rompe un carácter multibyte partido entre lecturas req('RF-CO-01')", async () => {
    const bytes = new TextEncoder().encode('event: token\ndata: {"text":"€ñ"}\n\n');
    const cut = bytes.indexOf(0xe2) + 1; // en mitad del euro
    const out = await collect([bytes.slice(0, cut), bytes.slice(cut)]);
    expect(out).toEqual([{ kind: "token", text: "€ñ" }]);
  });

  it("evento error con detalle y evento done req('RF-CO-01')", async () => {
    const out = await collect([
      'event: error\ndata: {"detail":"sin servicio"}\n\n',
      "event: done\ndata: {}\n\n",
    ]);
    expect(out).toEqual([{ kind: "error", detail: "sin servicio" }, { kind: "done" }]);
  });
});

describe("toChatEvent", () => {
  it("datos mal formados o evento desconocido no rompen req('RF-CO-01')", () => {
    expect(toChatEvent({ event: "token", data: "no es json" })).toEqual({ kind: "unknown" });
    expect(toChatEvent({ event: "otro", data: "{}" })).toEqual({ kind: "unknown" });
    expect(toChatEvent({ event: "error", data: "" })).toEqual({ kind: "error", detail: "" });
  });
});
