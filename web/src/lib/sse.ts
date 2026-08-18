export type SseHandler = (event: string, data: unknown) => void;

/** Read an SSE body, invoking the handler once per complete event. */
export async function parseSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: SseHandler,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      emit(block, onEvent);
      boundary = buffer.indexOf('\n\n');
    }
  }
}

function emit(block: string, onEvent: SseHandler): void {
  let event = 'message';
  let data = '';
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7);
    else if (line.startsWith('data: ')) data = line.slice(6);
  }
  if (data) onEvent(event, JSON.parse(data));
}
