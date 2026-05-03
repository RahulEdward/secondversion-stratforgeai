import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('stratforge', {
  version: '0.1.0',
  platform: process.platform,
  setTitleBarTheme: (theme: 'light' | 'dark') =>
    ipcRenderer.invoke('set-titlebar-theme', theme),
});

export type StratForgeBridge = {
  version: string;
  platform: NodeJS.Platform;
  setTitleBarTheme: (theme: 'light' | 'dark') => Promise<void>;
};
