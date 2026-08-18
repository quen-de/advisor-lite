import type { ChatRow } from '../lib/api';

export interface SidebarProps {
  chats: ChatRow[];
  activeChatId: string | null;
  onSelect: (chatId: string) => void;
  onNew: () => void;
  onDelete: (chatId: string) => void;
}

export function Sidebar({ chats, activeChatId, onSelect, onNew, onDelete }: SidebarProps) {
  return (
    <nav>
      <button type="button" className="new-chat" onClick={onNew}>
        New conversation
      </button>
      <ul className="chat-list">
        {chats.map((chat) => (
          <li key={chat.id} className={chat.id === activeChatId ? 'chat-row active' : 'chat-row'}>
            <button type="button" className="chat-link" onClick={() => onSelect(chat.id)}>
              {chat.title}
              <span className="chat-date">{chat.created_at.slice(0, 10)}</span>
            </button>
            <button
              type="button"
              className="chat-delete"
              aria-label={`Delete ${chat.title}`}
              title="Delete conversation"
              onClick={() => onDelete(chat.id)}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
