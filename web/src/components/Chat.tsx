import { useEffect, useRef, useState } from 'react';
import type { ExchangeRow, Source } from '../lib/api';
import { sendMessage } from '../lib/api';
import { Message } from './Message';

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  text: string;
  sources: Source[];
}

function fromExchanges(exchanges: ExchangeRow[]): ChatMessage[] {
  return exchanges.flatMap((exchange) => [
    { role: 'user' as const, text: exchange.user_text, sources: [] },
    { role: 'assistant' as const, text: exchange.assistant_text, sources: exchange.sources },
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
  const [statuses, setStatuses] = useState<{ id: string; text: string }[]>([]);
  const [idle, setIdle] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastDeltaAt = useRef(0);
  const statusShownAt = useRef(new Map<string, number>());
  const thinkingShownAt = useRef(0);

  // Every info line stays visible at least this long; tools often finish in
  // well under a second and a line that flashes is worse than none.
  const MIN_STATUS_MS = 2000;

  const dropStatusAfterMinDisplay = (id: string) => {
    const shownAt = statusShownAt.current.get(id);
    if (shownAt === undefined) return; // drop already scheduled
    statusShownAt.current.delete(id);
    const drop = () => setStatuses((current) => current.filter((s) => s.id !== id));
    const wait = shownAt + MIN_STATUS_MS - Date.now();
    if (wait > 0) setTimeout(drop, wait);
    else drop();
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
        const quiet = Date.now() - lastDeltaAt.current > 1500;
        if (!shown && quiet) thinkingShownAt.current = Date.now();
        if (shown && !quiet && Date.now() - thinkingShownAt.current < MIN_STATUS_MS) return true;
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
  }, [messages, statuses]);

  async function submit() {
    const content = input.trim();
    if (!content || streaming) return;
    setInput('');
    setStreaming(true);
    lastDeltaAt.current = Date.now();
    setMessages((current) => [
      ...current,
      { role: 'user', text: content, sources: [] },
      { role: 'assistant', text: '', sources: [] },
    ]);
    const patchLast = (patch: (message: ChatMessage) => ChatMessage) =>
      setMessages((current) => [...current.slice(0, -1), patch(current[current.length - 1])]);
    try {
      await sendMessage(chatId, content, (event, data) => {
        if (event === 'delta') {
          const { text } = data as { text: string };
          lastDeltaAt.current = Date.now();
          for (const id of statusShownAt.current.keys()) dropStatusAfterMinDisplay(id);
          patchLast((message) => ({ ...message, text: message.text + text }));
        } else if (event === 'status') {
          const { id, text } = data as { id: string; text: string };
          statusShownAt.current.set(id, Date.now());
          setStatuses((current) => [...current.filter((s) => s.id !== id), { id, text }]);
        } else if (event === 'status_done') {
          const { id } = data as { id: string };
          dropStatusAfterMinDisplay(id);
        } else if (event === 'title') {
          const { title } = data as { title: string };
          onTitle?.(chatId, title);
        } else if (event === 'sources') {
          const { sources, text } = data as { sources: Source[]; text?: string };
          setStatuses([]);
          patchLast((message) => ({ ...message, sources, text: text ?? message.text }));
        } else if (event === 'error') {
          const { message } = data as { message: string };
          setStatuses([]);
          patchLast(() => ({ role: 'system', text: message, sources: [] }));
        }
      });
    } catch {
      patchLast(() => ({
        role: 'system',
        text: 'The connection dropped. Send the message again.',
        sources: [],
      }));
    } finally {
      setStreaming(false);
      setStatuses([]);
      statusShownAt.current.clear();
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
            streaming={streaming && index === messages.length - 1 && message.role === 'assistant'}
          />
        ))}
        {statuses.map((s) => (
          <p className="status-line" key={s.id}>
            {s.text}
          </p>
        ))}
        {streaming && statuses.length === 0 && idle && <p className="status-line">Thinking…</p>}
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
