// Lector de Server-Sent Events sobre fetch + ReadableStream (el chat es un POST,
// así que EventSource no sirve). Sigue el formato de la especificación de SSE:
// campos `event:` y `data:`, evento terminado por línea en blanco, saltos \n, \r\n o \r.

export interface SseEvent {
  event: string;
  data: string;
}

export class SseParser {
  private buffer = "";
  private event = "";
  private data: string[] = [];
  private lastWasCR = false;

  /** Recibe un trozo de texto (puede cortar una línea o un evento por la mitad). */
  feed(chunk: string): SseEvent[] {
    // Un \r\n partido entre dos trozos: el \n que abre este trozo ya estaba contado.
    if (this.lastWasCR && chunk.startsWith("\n")) chunk = chunk.slice(1);
    if (chunk.length === 0) return [];
    this.lastWasCR = chunk.endsWith("\r");
    this.buffer += chunk;

    const events: SseEvent[] = [];
    const lines = this.buffer.split(/\r\n|\n|\r/);
    // El último elemento es una línea incompleta (o vacío si el trozo acabó en salto).
    this.buffer = lines.pop() ?? "";
    for (const line of lines) {
      const ev = this.line(line);
      if (ev) events.push(ev);
    }
    return events;
  }

  private line(line: string): SseEvent | null {
    if (line === "") {
      if (this.data.length === 0) {
        this.event = "";
        return null;
      }
      const ev = { event: this.event || "message", data: this.data.join("\n") };
      this.event = "";
      this.data = [];
      return ev;
    }
    if (line.startsWith(":")) return null; // comentario / keep-alive
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    let value = idx === -1 ? "" : line.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    return null;
  }
}

/** Itera los eventos de un cuerpo de respuesta SSE a medida que llegan. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parser = new SseParser();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      yield* parser.feed(decoder.decode(value, { stream: true }));
    }
    yield* parser.feed(decoder.decode());
  } finally {
    reader.releaseLock();
  }
}

// Eventos del chat (ver contrato de POST /api/chat): token {"text"}, done y error {"detail"}.
export type ChatEvent =
  | { kind: "token"; text: string }
  | { kind: "done" }
  | { kind: "error"; detail: string }
  | { kind: "unknown" };

export function toChatEvent(ev: SseEvent): ChatEvent {
  let payload: unknown;
  try {
    payload = ev.data ? JSON.parse(ev.data) : null;
  } catch {
    payload = null;
  }
  const obj = (typeof payload === "object" && payload !== null ? payload : {}) as Record<
    string,
    unknown
  >;
  switch (ev.event) {
    case "token":
      return typeof obj.text === "string" ? { kind: "token", text: obj.text } : { kind: "unknown" };
    case "done":
      return { kind: "done" };
    case "error":
      return { kind: "error", detail: typeof obj.detail === "string" ? obj.detail : "" };
    default:
      return { kind: "unknown" };
  }
}
