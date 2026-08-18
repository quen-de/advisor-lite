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
  const [status, setStatus] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages(fromExchanges(exchanges));
  }, [chatId, exchanges]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, status]);

  async function submit() {
    const content = input.trim();
    if (!content || streaming) return;
    setInput('');
    setStreaming(true);
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
          setStatus(null);
          patchLast((message) => ({ ...message, text: message.text + text }));
        } else if (event === 'status') {
          const { text } = data as { text: string };
          setStatus(text);
        } else if (event === 'title') {
          const { title } = data as { title: string };
          onTitle?.(chatId, title);
        } else if (event === 'sources') {
          const { sources, text } = data as { sources: Source[]; text?: string };
          setStatus(null);
          patchLast((message) => ({ ...message, sources, text: text ?? message.text }));
        } else if (event === 'error') {
          const { message } = data as { message: string };
          setStatus(null);
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
      setStatus(null);
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
        {status && <p className="status-line">{status}</p>}
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
