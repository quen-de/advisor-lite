import { useEffect, useRef, useState } from 'react';
import type { ExchangeRow, MessagePart, Source } from '../lib/api';
import { sendMessage } from '../lib/api';
import { Message } from './Message';

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  parts: MessagePart[];
  sources: Source[];
}

function fromExchanges(exchanges: ExchangeRow[]): ChatMessage[] {
  return exchanges.flatMap((exchange) => [
    {
      role: 'user' as const,
      parts: [{ kind: 'text' as const, text: exchange.user_text }],
      sources: [],
    },
    {
      role: 'assistant' as const,
      parts: exchange.parts ?? [{ kind: 'text' as const, text: exchange.assistant_text }],
      sources: exchange.sources,
    },
  ]);
}

export interface ChatProps {
  chatId: string;
  exchanges: ExchangeRow[];
  onTitle?: (chatId: string, title: string) => void;
}

export function Chat({ chatId, exchanges, onTitle }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => fromExchanges(exchanges));
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [idle, setIdle] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const programmaticScroll = useRef(false);
  const lastDeltaAt = useRef(0);
  const toolShownAt = useRef(new Map<string, number>());
  const thinkingShownAt = useRef(0);

  // A tool line keeps its pending mark at least this long before the check
  // appears; a state that flips within a frame reads as a glitch.
  const MIN_TOOL_MS = 2000;

  const markToolDone = (id: string) => {
    const shownAt = toolShownAt.current.get(id);
    toolShownAt.current.delete(id);
    const flip = () =>
      setMessages((current) =>
        current.map((message) => ({
          ...message,
          parts: message.parts.map((part) =>
            part.kind === 'bubble'
              ? {
                  ...part,
                  tools: part.tools.map((tool) =>
                    tool.id === id ? { ...tool, done: true } : tool,
                  ),
                }
              : part,
          ),
        })),
      );
    const wait = (shownAt ?? 0) + MIN_TOOL_MS - Date.now();
    if (wait > 0) setTimeout(flip, wait);
    else flip();
  };

  // With a reasoning model the stream goes quiet between tool rounds while
  // it thinks; surface that instead of an empty gap. Once shown, the line
  // also holds for the minimum display time.
  useEffect(() => {
    if (!streaming) {
      setIdle(false);
      return;
    }
    const timer = setInterval(() => {
      setIdle((shown) => {
        const quiet =
          Date.now() - lastDeltaAt.current > 1500 && toolShownAt.current.size === 0;
        if (!shown && quiet) thinkingShownAt.current = Date.now();
        if (shown && !quiet && Date.now() - thinkingShownAt.current < MIN_TOOL_MS) return true;
        return quiet;
      });
    }, 200);
    return () => clearInterval(timer);
  }, [streaming]);

  useEffect(() => {
    pinned.current = true;
    setMessages(fromExchanges(exchanges));
  }, [chatId, exchanges]);

  // Follow the stream only while the reader stays at the bottom. Scrolling
  // up (wheel, or dragging past the threshold) detaches; coming back near
  // the bottom reattaches. Programmatic scrolls don't count as the reader's.
  useEffect(() => {
    if (!pinned.current || !scrollRef.current) return;
    programmaticScroll.current = true;
    scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function submit() {
    const content = input.trim();
    if (!content || streaming) return;
    setInput('');
    setStreaming(true);
    pinned.current = true; // sending always snaps back to the live end
    lastDeltaAt.current = Date.now();
    setMessages((current) => [
      ...current,
      { role: 'user', parts: [{ kind: 'text', text: content }], sources: [] },
      { role: 'assistant', parts: [], sources: [] },
    ]);
    const patchLast = (patch: (message: ChatMessage) => ChatMessage) =>
      setMessages((current) => [...current.slice(0, -1), patch(current[current.length - 1])]);
    try {
      await sendMessage(chatId, content, (event, data) => {
        if (event === 'delta') {
          // Text belongs to the chat itself, commentary and answer alike.
          const { text } = data as { text: string };
          lastDeltaAt.current = Date.now();
          patchLast((message) => {
            const last = message.parts[message.parts.length - 1];
            const parts =
              last && last.kind === 'text'
                ? [...message.parts.slice(0, -1), { ...last, text: last.text + text }]
                : [...message.parts, { kind: 'text' as const, text }];
            return { ...message, parts };
          });
        } else if (event === 'thought') {
          // Reasoning stream. A bubble stays open until tool calls land in
          // it, so a thought after a tool round starts the next bubble.
          const { text } = data as { text: string };
          lastDeltaAt.current = Date.now();
          patchLast((message) => {
            const last = message.parts[message.parts.length - 1];
            const parts =
              last && last.kind === 'bubble' && last.tools.length === 0
                ? [...message.parts.slice(0, -1), { ...last, thoughts: last.thoughts + text }]
                : [...message.parts, { kind: 'bubble' as const, thoughts: text, tools: [] }];
            return { ...message, parts };
          });
        } else if (event === 'status') {
          const { id, text } = data as { id: string; text: string };
          toolShownAt.current.set(id, Date.now());
          patchLast((message) => {
            // Tool calls stack into the bubble whose thinking preceded them;
            // a round with no thinking still gets a bubble to live in.
            const last = message.parts[message.parts.length - 1];
            const line = { id, text, done: false };
            const parts =
              last && last.kind === 'bubble'
                ? [...message.parts.slice(0, -1), { ...last, tools: [...last.tools, line] }]
                : [...message.parts, { kind: 'bubble' as const, thoughts: '', tools: [line] }];
            return { ...message, parts };
          });
        } else if (event === 'status_done') {
          const { id } = data as { id: string };
          markToolDone(id);
        } else if (event === 'title') {
          const { title } = data as { title: string };
          onTitle?.(chatId, title);
        } else if (event === 'sources') {
          // The processed text replaces the final segment; earlier segments
          // (commentary between tool rounds) stay as they streamed.
          const { sources, text } = data as { sources: Source[]; text?: string };
          patchLast((message) => {
            const parts = [...message.parts];
            const last = parts[parts.length - 1];
            if (text !== undefined) {
              if (last && last.kind === 'text') parts[parts.length - 1] = { ...last, text };
              else parts.push({ kind: 'text', text });
            }
            return { ...message, sources, parts };
          });
        } else if (event === 'error') {
          const { message } = data as { message: string };
          patchLast(() => ({
            role: 'system',
            parts: [{ kind: 'text', text: message }],
            sources: [],
          }));
        }
      });
    } catch {
      patchLast(() => ({
        role: 'system',
        parts: [{ kind: 'text', text: 'The connection dropped. Send the message again.' }],
        sources: [],
      }));
    } finally {
      setStreaming(false);
      toolShownAt.current.clear();
    }
  }

  return (
    <div className="chat">
      <div
        className="chat-scroll"
        ref={scrollRef}
        onWheel={(event) => {
          if (event.deltaY < 0) pinned.current = false;
        }}
        onScroll={() => {
          if (programmaticScroll.current) {
            programmaticScroll.current = false;
            return;
          }
          const el = scrollRef.current;
          if (el) pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
        }}
      >
        {messages.length === 0 && (
          <p className="chat-empty">
            Ask about the portfolio. Try: should I trim my NVDA position?
          </p>
        )}
        {messages.map((message, index) => (
          <Message
            key={index}
            role={message.role}
            parts={message.parts}
            sources={message.sources}
            streaming={streaming && index === messages.length - 1 && message.role === 'assistant'}
          />
        ))}
        {streaming && idle && <p className="status-line">Thinking…</p>}
      </div>
      <form
        className="chat-input"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about your holdings"
          aria-label="Message"
        />
        <button type="submit" disabled={streaming || input.trim() === ''}>
          Send
        </button>
      </form>
    </div>
  );
}
