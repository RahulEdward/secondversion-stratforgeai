import MainHeader from './chat/MainHeader';
import MessageList from './chat/MessageList';
import ChatInput from './chat/ChatInput';
import ChatFooter from './chat/ChatFooter';

export default function ChatPane() {
  return (
    <main className="flex-1 flex flex-col min-w-0 bg-bg">
      <MainHeader />
      <MessageList />
      <div className="shrink-0 px-4 pb-4">
        <div className="max-w-3xl mx-auto">
          <ChatInput />
          <ChatFooter />
          <div className="text-[10px] text-fg-faint text-center mt-2">
            StratForge AI can make mistakes. Validate strategies before live trading.
          </div>
        </div>
      </div>
    </main>
  );
}
