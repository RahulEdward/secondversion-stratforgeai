import { useState } from 'react';
import { Plus, ChevronDown, BookOpen, type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/cn';
import { toast } from '../ui/Toast';
import TemplateLibraryModal from './TemplateLibraryModal';
import DocumentationModal from './DocumentationModal';

interface NavItemProps {
  icon: LucideIcon;
  label: string;
  onClick?: () => void;
  chevron?: boolean;
  open?: boolean;
}

function NavItem({ icon: Icon, label, onClick, chevron, open }: NavItemProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full h-7 flex items-center gap-2 px-2 rounded text-sm text-fg-muted',
        'hover:bg-bg-hover hover:text-fg transition-colors',
      )}
    >
      <Icon size={14} strokeWidth={1.75} />
      <span className="flex-1 text-left">{label}</span>
      {chevron && (
        <ChevronDown
          size={12}
          strokeWidth={1.75}
          className={cn(
            'transition-transform',
            open ? 'rotate-0' : '-rotate-90',
          )}
        />
      )}
    </button>
  );
}

interface Props {
  onNewSession?: () => void;
}

export default function SidebarNav({ onNewSession }: Props) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [docsOpen, setDocsOpen] = useState(false);

  return (
    <div className="px-2 pb-2 space-y-0.5">
      <NavItem
        icon={Plus}
        label="New session"
        onClick={onNewSession ?? (() => toast('Select or create a project first'))}
      />
      <NavItem
        icon={ChevronDown}
        label="More"
        chevron
        open={moreOpen}
        onClick={() => setMoreOpen((v) => !v)}
      />
      {moreOpen && (
        <div className="pl-6 space-y-0.5">
          <NavItem
            icon={BookOpen}
            label="Templates Library"
            onClick={() => setTemplatesOpen(true)}
          />
          <NavItem
            icon={BookOpen}
            label="Documentation"
            onClick={() => setDocsOpen(true)}
          />
          <NavItem
            icon={Plus}
            label="Keyboard shortcuts"
            onClick={() => toast('Shortcuts — coming soon')}
          />
        </div>
      )}

      <TemplateLibraryModal 
        open={templatesOpen} 
        onClose={() => setTemplatesOpen(false)} 
      />
      <DocumentationModal
        open={docsOpen}
        onClose={() => setDocsOpen(false)}
      />
    </div>
  );
}
