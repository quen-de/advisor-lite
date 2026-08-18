import { parseSseStream, type SseHandler } from './sse';

export interface Source {
  id: number;
  title: string;
  url: string;
}

export interface ChatRow {
  id: string;
  title: string;
  created_at: string;
}

export interface ToolLine {
  id?: string;
  text: string;
  done: boolean;
}

/** One reasoning sequence: the model's thinking plus the tool calls it made. */
export interface Bubble {
  kind: 'bubble';
  thoughts: string;
  tools: ToolLine[];
}

export interface TextSegment {
  kind: 'text';
  text: string;
}

/** An assistant message in display order: bubbles and text segments. */
export type MessagePart = Bubble | TextSegment;

export interface ExchangeRow {
  user_text: string;
  assistant_text: string;
  sources: Source[];
  parts: MessagePart[];
}

export interface Position {
  ticker: string;
  name: string;
  quantity: number;
  cost_basis: number;
  currency: string;
}

export interface Portfolio {
  as_of: string;
  cash: number;
  currency: string;
  positions: Position[];
  summary: string;
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export const getPortfolio = () => fetch('/api/portfolio').then((r) => json<Portfolio>(r));

export interface PositionIn {
  name: string;
  quantity: number;
  cost_basis: number;
  currency: string;
}

async function expectNoContent(response: Response): Promise<void> {
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
}

export const putPosition = (ticker: string, body: PositionIn) =>
  fetch(`/api/positions/${ticker}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }).then(expectNoContent);

export const deletePosition = (ticker: string) =>
  fetch(`/api/positions/${ticker}`, { method: 'DELETE' }).then(expectNoContent);

export const setCash = (cash: number) =>
  fetch('/api/portfolio', {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ cash }),
  }).then(expectNoContent);

export const listChats = () => fetch('/api/chats').then((r) => json<ChatRow[]>(r));

export const createChat = () =>
  fetch('/api/chats', { method: 'POST' }).then((r) => json<ChatRow>(r));

export async function deleteChat(chatId: string): Promise<void> {
  const response = await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
}

export const getExchanges = (chatId: string) =>
  fetch(`/api/chats/${chatId}/exchanges`).then((r) => json<ExchangeRow[]>(r));

export async function sendMessage(
  chatId: string,
  content: string,
  onEvent: SseHandler,
): Promise<void> {
  const response = await fetch(`/api/chats/${chatId}/messages`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  await parseSseStream(response.body, onEvent);
}
