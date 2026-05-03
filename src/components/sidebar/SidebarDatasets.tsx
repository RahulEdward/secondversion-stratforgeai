import { useState } from 'react';
import { Database, Eye, Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/cn';
import { useAppStore } from '@/store/useAppStore';
import type { Dataset } from '@/lib/api';
import DataUploadDropzone from '../DataUploadDropzone';
import DatasetPreviewModal from '../DatasetPreviewModal';

function DatasetRow({
  dataset,
  active,
  onSelect,
  onPreview,
  onDelete,
}: {
  dataset: Dataset;
  active: boolean;
  onSelect: () => void;
  onPreview: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      onClick={onSelect}
      className={cn(
        'group w-full flex items-center gap-2 pl-3 pr-2 py-1 rounded cursor-pointer text-xs transition-colors',
        active
          ? 'bg-bg-active text-fg'
          : 'text-fg-muted hover:bg-bg-hover hover:text-fg',
      )}
      title={dataset.has_ohlcv ? 'OHLCV detected' : 'No OHLCV columns'}
    >
      <Database
        size={10}
        strokeWidth={1.75}
        className={cn(
          'shrink-0',
          dataset.has_ohlcv ? 'text-accent' : 'text-fg-subtle',
        )}
      />
      <span className="truncate flex-1">{dataset.filename}</span>
      <span className="text-fg-faint shrink-0 tabular-nums">
        {dataset.rows}
      </span>
      <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 transition-opacity">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onPreview();
          }}
          className="p-0.5 rounded hover:bg-bg-hover hover:text-fg"
          title="Preview rows"
        >
          <Eye size={10} />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="p-0.5 rounded hover:bg-bg-hover hover:text-red-400"
          title="Delete dataset"
        >
          <Trash2 size={10} />
        </button>
      </div>
    </div>
  );
}

interface Props {
  projectId: string;
}

export default function SidebarDatasets({ projectId }: Props) {
  const datasets = useAppStore((s) => s.datasetsByProject[projectId] ?? []);
  const activeDatasetId = useAppStore((s) => s.activeDatasetId);
  const setActiveDataset = useAppStore((s) => s.setActiveDataset);
  const deleteDataset = useAppStore((s) => s.deleteDataset);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);

  const handleDelete = async (id: string, filename: string) => {
    if (!confirm(`Delete dataset "${filename}"?`)) return;
    await deleteDataset(id);
  };

  return (
    <div className="mb-1">
      <div className="group flex items-center justify-between px-2 py-0.5">
        <span className="text-2xs font-medium text-fg-subtle uppercase tracking-wider">
          Datasets
        </span>
        <button
          onClick={() => setUploadOpen(true)}
          className="p-0.5 rounded text-fg-subtle hover:bg-bg-hover hover:text-fg opacity-0 group-hover:opacity-100 transition-opacity"
          title="Upload dataset"
        >
          <Plus size={11} />
        </button>
      </div>
      <div className="space-y-0.5">
        {datasets.length === 0 ? (
          <button
            onClick={() => setUploadOpen(true)}
            className="pl-3 pr-2 py-1 text-2xs text-fg-faint italic hover:text-fg-muted text-left w-full"
          >
            No datasets — click + to upload
          </button>
        ) : (
          datasets.map((d) => (
            <DatasetRow
              key={d.id}
              dataset={d}
              active={activeDatasetId === d.id}
              onSelect={() => setActiveDataset(d.id)}
              onPreview={() => setPreviewId(d.id)}
              onDelete={() => handleDelete(d.id, d.filename)}
            />
          ))
        )}
      </div>

      <DataUploadDropzone
        open={uploadOpen}
        projectId={projectId}
        onClose={() => setUploadOpen(false)}
      />
      {previewId && (
        <DatasetPreviewModal
          datasetId={previewId}
          onClose={() => setPreviewId(null)}
        />
      )}
    </div>
  );
}
