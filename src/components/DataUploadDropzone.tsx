import { useEffect, useRef, useState } from 'react';
import { Upload, X, FileSpreadsheet } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore } from '@/store/useAppStore';
import { toast } from './ui/Toast';

const ACCEPT_EXT = ['.csv', '.tsv', '.xlsx', '.xls'];
const MAX_BYTES = 100 * 1024 * 1024;

interface Props {
  open: boolean;
  projectId: string;
  onClose: () => void;
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function hasAllowedExt(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPT_EXT.some((e) => lower.endsWith(e));
}

export default function DataUploadDropzone({
  open,
  projectId,
  onClose,
}: Props) {
  const upload = useAppStore((s) => s.uploadDataset);
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setFile(null);
      setProgress(0);
      setError(null);
      setSubmitting(false);
      setDrag(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !submitting) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, submitting, onClose]);

  if (!open) return null;

  const pickFile = (f: File) => {
    setError(null);
    if (!hasAllowedExt(f.name)) {
      setError(`Unsupported type. Allowed: ${ACCEPT_EXT.join(', ')}`);
      return;
    }
    if (f.size > MAX_BYTES) {
      setError(`File exceeds ${MAX_BYTES / (1024 * 1024)} MB limit`);
      return;
    }
    setFile(f);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) pickFile(f);
  };

  const handleUpload = async () => {
    if (!file) return;
    setSubmitting(true);
    setError(null);
    setProgress(0);
    try {
      await upload(projectId, file, (pct) => setProgress(pct));
      toast(`Uploaded ${file.name}`);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={submitting ? undefined : onClose}
    >
      <div
        className="w-[480px] bg-bg-panel border border-border rounded-xl p-5 shadow-popup"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-base">Upload dataset</h2>
          <button
            onClick={onClose}
            disabled={submitting}
            className="p-1 rounded hover:bg-bg-hover text-fg-muted disabled:opacity-30 transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        {!file ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={cn(
              'border-2 border-dashed rounded-lg py-10 px-6 text-center cursor-pointer transition-colors',
              drag
                ? 'border-accent bg-accent/5'
                : 'border-border hover:border-border-strong bg-bg/40',
            )}
          >
            <Upload
              size={28}
              strokeWidth={1.5}
              className="mx-auto text-fg-subtle mb-3"
            />
            <div className="text-sm text-fg">
              Drop a file here, or click to browse
            </div>
            <div className="text-2xs text-fg-subtle mt-1">
              CSV, TSV, or Excel — up to 100 MB
            </div>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT_EXT.join(',')}
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) pickFile(f);
                e.target.value = '';
              }}
            />
          </div>
        ) : (
          <div className="border border-border rounded-lg p-4 bg-bg/40">
            <div className="flex items-center gap-3">
              <FileSpreadsheet
                size={20}
                strokeWidth={1.75}
                className="text-accent shrink-0"
              />
              <div className="min-w-0 flex-1">
                <div className="text-sm text-fg truncate">{file.name}</div>
                <div className="text-2xs text-fg-subtle">
                  {humanSize(file.size)}
                </div>
              </div>
              {!submitting && (
                <button
                  onClick={() => setFile(null)}
                  className="p-1 rounded text-fg-muted hover:bg-bg-hover hover:text-fg"
                  title="Pick another file"
                >
                  <X size={13} />
                </button>
              )}
            </div>
            {submitting && (
              <div className="mt-3">
                <div className="h-1 bg-bg rounded overflow-hidden">
                  <div
                    className="h-full bg-accent transition-all"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <div className="mt-1.5 text-2xs text-fg-subtle tabular-nums">
                  {progress < 100 ? `Uploading ${progress}%` : 'Parsing…'}
                </div>
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="text-xs text-red-400 mt-3 leading-relaxed">
            {error}
          </div>
        )}

        <div className="flex gap-2 mt-4 justify-end">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-3 py-1.5 rounded border border-border text-fg-muted hover:bg-bg-hover disabled:opacity-40 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleUpload}
            disabled={!file || submitting}
            className="px-3 py-1.5 rounded bg-accent hover:bg-accent-hover text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? 'Uploading…' : 'Upload'}
          </button>
        </div>
      </div>
    </div>
  );
}
