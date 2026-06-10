export async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";

  while (true) {
    if (signal?.aborted) break;
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const raw = line.slice(6);
        try {
          const parsed = JSON.parse(raw);
          yield { event: currentEvent, data: parsed };
        } catch {
          // skip malformed JSON lines
        }
      }
    }
  }
}
