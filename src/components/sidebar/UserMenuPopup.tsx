import Popup, { PopupItem, PopupSection } from '../ui/Popup';
import { useAppStore, type FontSize } from '@/store/useAppStore';
import { cn } from '@/lib/cn';

interface Props {
  onClose: () => void;
}

const FONT_OPTIONS: { id: FontSize; label: string }[] = [
  { id: 'small', label: 'Small' },
  { id: 'medium', label: 'Medium' },
  { id: 'large', label: 'Large' },
];

export default function UserMenuPopup({ onClose }: Props) {
  const openSettings = useAppStore((s) => s.openSettings);
  const fontSize = useAppStore((s) => s.fontSize);
  const setFontSize = useAppStore((s) => s.setFontSize);

  const handleSettings = () => {
    openSettings('general');
    onClose();
  };

  return (
    <Popup
      open
      onClose={onClose}
      className="bottom-[52px] left-2 right-2 max-w-[260px]"
    >
      <PopupItem onClick={handleSettings}>Settings</PopupItem>

      <div className="border-t border-border-subtle my-1" />

      <div className="px-3 py-1.5 text-[10px] font-medium text-fg-subtle uppercase tracking-wider">
        Font Size
      </div>
      <div className="flex items-center gap-1 px-3 pb-2">
        {FONT_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            onClick={() => setFontSize(opt.id)}
            className={cn(
              'flex-1 text-xs py-1.5 rounded-md text-center transition-colors',
              fontSize === opt.id
                ? 'bg-accent text-white font-medium'
                : 'bg-bg-hover text-fg-muted hover:text-fg hover:bg-bg-active',
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </Popup>
  );
}
