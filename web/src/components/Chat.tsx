import { useEffect, useRef, useState } from 'react';
import type { ExchangeRow, Source } from '../lib/api';
import { sendMessage } from '../lib/api';
import type { Bubble } from './Message';
import { Message } from './Message';

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  text: string;
  sources: Source[];
  bubbles: Bubble[];
}

function fromExchanges(exchanges: ExchangeRow[]): ChatMessage[] {
  return exchanges.flatMap((exchange) => [
    { role: 'user' as const, text: exchange.user_text, sources: [], bubbles: [] },
    {
      role: 'assistant' as const,
      text: exchange.assistant_text,
      sources: exchange.sources,
      bubbles: [],
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
          bubbles: message.bubbles.map((bubble) => ({
            ...bubble,
            tools: bubble.tools.map((tool) => (tool.id === id ? { ...tool, done: true } : tool)),
          })),
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
    setMessages(fromExchanges(exchanges));
  }, [chatId, exchanges]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  async function submit() {
    const content = input.trim();
    if (!content || streaming) return;
    setInput('');
    setStreaming(true);
    lastDeltaAt.current = Date.now();
    setMessages((current) => [
      ...current,
      { role: 'user', text: content, sources: [], bubbles: [] },
      { role: 'assistant', text: '', sources: [], bubbles: [] },
    ]);
    const patchLast = (patch: (message: ChatMessage) => ChatMessage) =>
      setMessages((current) => [...current.slice(0, -1), patch(current[current.length - 1])]);
    try {
      await sendMessage(chatId, content, (event, data) => {
        if (event === 'delta') {
          const { text } = data as { text: string };
          lastDeltaAt.current = Date.now();
          patchLast((message) => ({ ...message, text: message.text + text }));
        } else if (event === 'demote') {
          // The text streamed so far was commentary before a tool round:
          // close it into a fresh bubble and let the answer restart clean.
          patchLast((message) => ({
            ...message,
            text: '',
            bubbles: [...message.bubbles, { thoughts: message.text.trim(), tools: [] }],
          }));
        } else if (event === 'status') {
          const { id, text } = data as { id: string; text: string };
          toolShownAt.current.set(id, Date.now());
          patchLast((message) => {
            // Tool calls stack into the bubble whose thinking preceded them;
            // a round with no commentary still gets a bubble to live in.
            const bubbles = message.bubbles.length
              ? [...message.bubbles]
              : [{ thoughts: '', tools: [] }];
            const last = bubbles[bubbles.length - 1];
            bubbles[bubbles.length - 1] = {
              ...last,
              tools: [...last.tools, { id, text, done: false }],
            };
            return { ...message, bubbles };
          });
        } else if (event === 'status_done') {
          const { id } = data as { id: string };
          markToolDone(id);
        } else if (event === 'title') {
          const { title } = data as { title: string };
          onTitle?.(chatId, title);
        } else if (event === 'sources') {
          const { sources, text } = data as { sources: Source[]; text?: string };
          patchLast((message) => ({ ...message, sources, text: text ?? message.text }));
        } else if (event === 'error') {
          const { message } = data as { message: string };
          patchLast(() => ({ role: 'system', text: message, sources: [], bubbles: [] }));
        }
      });
    } catch {
      patchLast(() => ({
        role: 'system',
        text: 'The connection dropped. Send the message again.',
        sources: [],
        bubbles: [],
      }));
    } finally {
      setStreaming(false);
      toolShownAt.current.clear();
    }
  }

  return (
    <div className="chat">
      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <p className="chat-empty">
            Ask about the portfolio. Try: should I trim my NVDA position?
          </p>
        )}
        {messages.map((message, index) => (
          <Message
            key={index}
            role={message.role}
            text={message.text}
            sources={message.sources}
            bubbles={message.bubbles}
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
