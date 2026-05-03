import { create } from 'zustand';
import { useEffect } from 'react';

interface ToastState {
  message: string | null;
  show: (msg: string) => void;
  clear: () => void;
}

const useToastStore = create<ToastState>((set) => ({
  message: null,
  show: (msg) => set({ message: msg }),
  clear: () => set({ message: null }),
}));

export function toast(msg: string) {
  useToastStore.getState().show(msg);
}

export function ToastHost() {
  const message = useToastStore((s) => s.message);
  const clear = useToastStore((s) => s.clear);

  useEffect(() => {
    if (message == null) return;
    const t = setTimeout(clear, 1800);
    return () => clearTimeout(t);
  }, [message, clear]);

  if (message == null) return null;
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] pointer-events-none">
      <div className="px-3 py-2 rounded-lg bg-bg-panel border border-border shadow-popup text-xs text-fg">
        {message}
      </div>
    </div>
  );
}
