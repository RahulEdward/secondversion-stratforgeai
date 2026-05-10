import { Monitor, Moon, Sun, Shield, ShieldCheck, ShieldAlert, Zap, Info } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore, type Theme, type PermissionMode } from '@/store/useAppStore';

/**
 * Claude Code-style General settings panel.
 *
 * Sections:
 *   1. Appearance       — theme (system / light / dark)
 *   2. Permission Mode  — ask / accept-edits / plan / bypass
 *   3. Layout           — sidebar + artifacts default widths (reset buttons)
 *   4. About            — app version, backend port
 */
export default function GeneralPanel() {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-2xl mx-auto px-8 py-8 space-y-10">
        <header>
          <h1 className="text-xl font-semibold">General</h1>
          <p className="text-sm text-fg-muted mt-1">
            Tweak appearance, permissions, and layout defaults.
          </p>
        </header>

        <AppearanceSection />
        <PermissionSection />
        <LayoutSection />
        <AboutSection />
      </div>
    </div>
  );
}

// ── Appearance ──────────────────────────────────────────────────────────

function AppearanceSection() {
  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);

  const options: { id: Theme; label: string; icon: typeof Sun; hint: string }[] = [
    { id: 'system', label: 'System', icon: Monitor, hint: 'Follow OS preference' },
    { id: 'dark', label: 'Dark', icon: Moon, hint: 'Always dark' },
    { id: 'light', label: 'Light', icon: Sun, hint: 'Always light' },
  ];

  return (
    <Section title="Appearance" description="Controls the window theme and background.">
      <div className="grid grid-cols-3 gap-2">
        {options.map((opt) => {
          const Icon = opt.icon;
          const active = theme === opt.id;
          return (
            <button
              key={opt.id}
              onClick={() => setTheme(opt.id)}
              className={cn(
                'flex flex-col items-start gap-1.5 p-3 rounded-lg border text-left transition-colors',
                active
                  ? 'border-accent bg-accent-subtle text-fg'
                  : 'border-border-subtle bg-bg-panel text-fg-muted hover:border-border hover:text-fg',
              )}
            >
              <Icon size={16} strokeWidth={1.75} className={active ? 'text-accent' : 'text-fg-subtle'} />
              <div className="text-sm font-medium">{opt.label}</div>
              <div className="text-[11px] text-fg-subtle leading-tight">{opt.hint}</div>
            </button>
          );
        })}
      </div>
    </Section>
  );
}

// ── Permission Mode ─────────────────────────────────────────────────────

function PermissionSection() {
  const permission = useAppStore((s) => s.permissionMode);
  const setPermission = useAppStore((s) => s.setPermissionMode);

  const options: {
    id: PermissionMode;
    label: string;
    icon: typeof Shield;
    hint: string;
    accentClass: string;
  }[] = [
    {
      id: 'ask',
      label: 'Ask',
      icon: ShieldCheck,
      hint: 'Prompt before every edit, command, or agent action.',
      accentClass: 'text-sky-400',
    },
    {
      id: 'accept-edits',
      label: 'Accept Edits',
      icon: Shield,
      hint: 'Auto-accept file edits, still ask for shell commands. (Default)',
      accentClass: 'text-emerald-400',
    },
    {
      id: 'plan',
      label: 'Plan',
      icon: Info,
      hint: 'Read-only mode — the agent explains a plan, no execution.',
      accentClass: 'text-amber-400',
    },
    {
      id: 'bypass',
      label: 'Bypass',
      icon: Zap,
      hint: 'Run everything without confirmation. Only for trusted sessions.',
      accentClass: 'text-red-400',
    },
  ];

  return (
    <Section
      title="Permission Mode"
      description="Controls how the agent asks before running tools. Change mid-session from the right-pane menu."
    >
      <div className="space-y-1.5">
        {options.map((opt) => {
          const Icon = opt.icon;
          const active = permission === opt.id;
          return (
            <button
              key={opt.id}
              onClick={() => setPermission(opt.id)}
              className={cn(
                'w-full flex items-start gap-3 p-3 rounded-lg border text-left transition-colors',
                active
                  ? 'border-accent bg-accent-subtle'
                  : 'border-border-subtle bg-bg-panel hover:border-border',
              )}
            >
              <Icon size={16} strokeWidth={1.75} className={cn('mt-0.5 shrink-0', opt.accentClass)} />
              <div className="flex-1 min-w-0">
                <div className={cn('text-sm font-medium', active ? 'text-fg' : 'text-fg-muted')}>
                  {opt.label}
                </div>
                <div className="text-xs text-fg-subtle mt-0.5 leading-snug">{opt.hint}</div>
              </div>
              {active && (
                <span className="text-[10px] font-medium text-accent uppercase tracking-wider shrink-0 mt-1">
                  active
                </span>
              )}
            </button>
          );
        })}
      </div>
    </Section>
  );
}

// ── Layout ──────────────────────────────────────────────────────────────

function LayoutSection() {
  const sidebarWidth = useAppStore((s) => s.sidebarWidth);
  const setSidebarWidth = useAppStore((s) => s.setSidebarWidth);
  const artifactsWidth = useAppStore((s) => s.artifactsWidth);
  const setArtifactsWidth = useAppStore((s) => s.setArtifactsWidth);

  return (
    <Section
      title="Layout"
      description="Window pane widths are remembered across launches. Reset them to StratForge's defaults here."
    >
      <div className="space-y-3">
        <Row label="Sidebar" value={`${sidebarWidth}px`}>
          <button
            onClick={() => setSidebarWidth(280)}
            disabled={sidebarWidth === 280}
            className="text-xs text-fg-muted hover:text-fg px-2 py-1 rounded hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Reset to 280
          </button>
        </Row>
        <Row label="Artifacts pane" value={`${artifactsWidth}px`}>
          <button
            onClick={() => setArtifactsWidth(440)}
            disabled={artifactsWidth === 440}
            className="text-xs text-fg-muted hover:text-fg px-2 py-1 rounded hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Reset to 440
          </button>
        </Row>
      </div>
    </Section>
  );
}

// ── About ───────────────────────────────────────────────────────────────

function AboutSection() {
  return (
    <Section title="About">
      <div className="space-y-2 text-sm">
        <Row label="App" value="StratForge AI" />
        <Row label="Version" value="0.1.0" />
        <Row label="Backend" value="http://127.0.0.1:8765" />
        <Row label="Engine" value="StratForge" />
      </div>
    </Section>
  );
}

// ── Primitives ──────────────────────────────────────────────────────────

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
        {description && (
          <p className="text-xs text-fg-muted mt-0.5 leading-relaxed">{description}</p>
        )}
      </div>
      {children}
    </section>
  );
}

function Row({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 border-b border-border-subtle/50 last:border-0">
      <span className="text-sm text-fg-muted">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-sm text-fg font-mono">{value}</span>
        {children}
      </div>
    </div>
  );
}
