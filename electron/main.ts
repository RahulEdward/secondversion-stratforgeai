import { app, BrowserWindow, ipcMain, shell } from 'electron';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const isDev = !app.isPackaged;

let mainWindow: BrowserWindow | null = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    backgroundColor: '#100517',
    title: 'StratForge AI',
    autoHideMenuBar: true,
    icon: path.join(__dirname, '../public/icon.ico'),
    // Hide the default OS titlebar, render native min/max/close buttons as an overlay
    // tinted to match the sidebar color so the top strip is fully dark on Windows 11.
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#100517',
      symbolColor: '#ebe6f0',
      height: 40,
    },
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (isDev && process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  ipcMain.handle('set-titlebar-theme', (_event, theme: 'light' | 'dark') => {
    if (!mainWindow) return;
    if (theme === 'light') {
      mainWindow.setTitleBarOverlay({ color: '#ececf1', symbolColor: '#18181b' });
    } else {
      mainWindow.setTitleBarOverlay({ color: '#100517', symbolColor: '#ebe6f0' });
    }
  });
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
