import { useCallback, useEffect, useState } from 'react';
import { Chat } from './components/Chat';
import { PortfolioPanel } from './components/Portfolio';
import { Sidebar } from './components/Sidebar';
import type { ChatRow, ExchangeRow, Portfolio } from './lib/api';
import { createChat, deleteChat, getExchanges, getPortfolio, listChats } from './lib/api';

export default function App() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [chats, setChats] = useState<ChatRow[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [exchanges, setExchanges] = useState<ExchangeRow[]>([]);

  useEffect(() => {
    void getPortfolio().then(setPortfolio).catch(() => setPortfolio(null));
    void listChats().then(setChats).catch(() => setChats([]));
  }, []);

  const refreshPortfolio = useCallback(() => {
    void getPortfolio().then(setPortfolio).catch(() => {});
  }, []);

  const selectChat = useCallback((chatId: string) => {
    setActiveChatId(chatId);
    void getExchanges(chatId).then(setExchanges).catch(() => setExchanges([]));
  }, []);

  const newChat = useCallback(() => {
    void createChat().then((chat) => {
      setChats((current) => [chat, ...current]);
      setActiveChatId(chat.id);
      setExchanges([]);
    });
  }, []);

  const removeChat = useCallback(
    (chatId: string) => {
      void deleteChat(chatId)
        .then(() => {
          setChats((current) => current.filter((chat) => chat.id !== chatId));
          if (chatId === activeChatId) {
            setActiveChatId(null);
            setExchanges([]);
          }
        })
        .catch(() => {});
    },
    [activeChatId],
  );

  const renameChat = useCallback((chatId: string, title: string) => {
    setChats((current) => current.map((chat) => (chat.id === chatId ? { ...chat, title } : chat)));
  }, []);

  return (
    <div className="app">
      <header className="masthead">
        <span className="wordmark">advisor-lite</span>
        <span className="stamp">Demo · Not financial advice</span>
      </header>
      <div className="columns">
        <aside className="pane">
          <h2 className="pane-label">Conversations</h2>
          <Sidebar
            chats={chats}
            activeChatId={activeChatId}
            onSelect={selectChat}
            onNew={newChat}
            onDelete={removeChat}
          />
        </aside>
        <aside className="pane">
          <h2 className="pane-label">Portfolio</h2>
          {portfolio ? (
            <PortfolioPanel portfolio={portfolio} onChanged={refreshPortfolio} />
          ) : (
            <p className="as-of">Portfolio unavailable. Is the API running?</p>
          )}
        </aside>
        <main className="pane">
          {activeChatId ? (
            <Chat
              key={activeChatId}
              chatId={activeChatId}
              exchanges={exchanges}
              onTitle={renameChat}
            />
          ) : (
            <div className="chat">
              <div className="chat-scroll">
                <p className="chat-empty">Start a conversation to get counsel on the portfolio.</p>
              </div>
              <div className="chat-input">
                <button type="button" onClick={newChat}>
                  New conversation
                </button>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
