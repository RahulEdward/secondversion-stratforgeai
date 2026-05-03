import Popup, { PopupItem } from '../ui/Popup';
import { useAppStore } from '@/store/useAppStore';

interface Props {
  onClose: () => void;
}

export default function UserMenuPopup({ onClose }: Props) {
  const openSettings = useAppStore((s) => s.openSettings);

  const handleSettings = () => {
    openSettings('providers');
    onClose();
  };

  return (
    <Popup
      open
      onClose={onClose}
      className="bottom-[52px] left-2 right-2 max-w-[260px]"
    >
      <PopupItem onClick={handleSettings}>Settings</PopupItem>
    </Popup>
  );
}
