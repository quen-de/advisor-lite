import { describe, expect, it } from 'vitest';
import { parseSseStream } from './sse';

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(new TextEncoder().encode(chunk));
      }
      controller.close();
    },
  });
}

describe('parseSseStream', () => {
  it('parses events from a stream', async () => {
    const events: Array<[string, unknown]> = [];
    await parseSseStream(
      streamOf(['event: delta\ndata: {"text":"a"}\n\nevent: done\ndata: {"chat_id":"1"}\n\n']),
      (event, data) => events.push([event, data]),
    );
    expect(events).toEqual([
      ['delta', { text: 'a' }],
      ['done', { chat_id: '1' }],
    ]);
  });

  it('handles an event split across chunks', async () => {
    const events: Array<[string, unknown]> = [];
    await parseSseStream(
      streamOf(['event: delta\nda', 'ta: {"text":"ab"}\n\n']),
      (event, data) => events.push([event, data]),
    );
    expect(events).toEqual([['delta', { text: 'ab' }]]);
  });
});
