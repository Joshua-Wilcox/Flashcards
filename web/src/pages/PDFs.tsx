import { useState, useCallback, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useDropzone } from 'react-dropzone';
import {
  Upload, FileText, Trash2, RotateCcw, Eye, Edit2,
  X, Check, AlertCircle, ChevronDown, Filter,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '../api/client';
import type { PDF, User } from '../types';
import ModuleSelector from '../components/ModuleSelector';
import MultiSelectField from '../components/MultiSelectField';
import TagInput from '../components/TagInput';

interface PDFsProps {
  user?: User;
}

export default function PDFs({ user }: PDFsProps) {
  const isAdmin = user?.is_admin;
  const queryClient = useQueryClient();

  // Filter state — multi-select like the home page
  const [filterModule, setFilterModule] = useState('');
  const [filterModuleId, setFilterModuleId] = useState<number | undefined>();
  const [filterTopics, setFilterTopics] = useState<string[]>([]);
  const [filterSubtopics, setFilterSubtopics] = useState<string[]>([]);
  const [filterTags, setFilterTags] = useState<string[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  // Upload/submit state
  const [uploadModule, setUploadModule] = useState('');
  const [uploadModuleId, setUploadModuleId] = useState<number | undefined>();
  const [uploadTopics, setUploadTopics] = useState<string[]>([]);
  const [uploadSubtopics, setUploadSubtopics] = useState<string[]>([]);
  const [uploadTags, setUploadTags] = useState<string[]>([]);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState('');
  const [editingPDF, setEditingPDF] = useState<number | null>(null);

  const { data: modulesData } = useQuery({
    queryKey: ['modules'],
    queryFn: api.getModules,
  });

  // Fetch filter options for the selected module (same as home page)
  const { data: filterData } = useQuery({
    queryKey: ['filters', filterModule, filterTopics],
    queryFn: () => api.getFilters(filterModule, filterTopics),
    enabled: !!filterModule,
  });

  const { data: pdfsData, isLoading } = useQuery({
    queryKey: ['pdfs', filterModuleId, filterTopics, filterSubtopics, filterTags, showInactive],
    queryFn: () => api.listPDFs({
      module_id: filterModuleId,
      is_active: !showInactive,
      topic: filterTopics[0] || undefined,
      subtopic: filterSubtopics[0] || undefined,
      tag: filterTags[0] || undefined,
      limit: 100,
    }),
  });

  const handleFilterModuleSelect = (name: string) => {
    setFilterModule(name);
    const mod = modulesData?.modules.find(m => m.name === name);
    setFilterModuleId(mod?.id);
    setFilterTopics([]);
    setFilterSubtopics([]);
    setFilterTags([]);
  };

  const handleUploadModuleSelect = (name: string) => {
    setUploadModule(name);
    const mod = modulesData?.modules.find(m => m.name === name);
    setUploadModuleId(mod?.id);
    setUploadTopics([]);
    setUploadSubtopics([]);
    setUploadTags([]);
  };

  // Fetch filter options for the upload module
  const { data: uploadFilterData } = useQuery({
    queryKey: ['filters', uploadModule, uploadTopics],
    queryFn: () => api.getFilters(uploadModule, uploadTopics),
    enabled: !!uploadModule,
  });

  const [uploadDropdown, setUploadDropdown] = useState<string | null>(null);

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!uploadModuleId || pendingFiles.length === 0) {
        throw new Error('Please select a module and add files');
      }
      const metadata = {
        module_id: uploadModuleId,
        topic_names: uploadTopics,
        subtopic_names: uploadSubtopics,
        tag_names: uploadTags,
      };
      if (pendingFiles.length === 1) {
        return api.submitPDF(pendingFiles[0], metadata);
      } else {
        return api.batchSubmitPDFs(pendingFiles, metadata);
      }
    },
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['pdfs'] });
      setPendingFiles([]);
      setUploadTopics([]);
      setUploadSubtopics([]);
      setUploadTags([]);
      setUploadError('');
      if (data?.pending) {
        toast.success('Submitted for review — an admin will approve your PDF shortly.');
      } else {
        toast.success('PDF uploaded successfully.');
      }
    },
    onError: (err: Error) => {
      setUploadError(err.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deletePDF(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pdfs'] });
      toast.success('PDF deleted');
    },
  });

  const hardDeleteMutation = useMutation({
    mutationFn: (id: number) => api.hardDeletePDF(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pdfs'] });
      toast.success('PDF permanently deleted');
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (id: number) => api.restorePDF(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pdfs'] });
      toast.success('PDF restored');
    },
  });

  const onDrop = useCallback((accepted: File[]) => {
    const pdfs = accepted.filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'));
    setPendingFiles(prev => [...prev, ...pdfs]);
    setUploadError('');
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
  });

  const formatSize = (bytes?: number) => {
    if (!bytes) return '';
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const pdfs = pdfsData?.pdfs || [];
  const hasActiveFilters = filterModule || filterTopics.length > 0 || filterSubtopics.length > 0 || filterTags.length > 0;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <FileText className="h-7 w-7 text-blue-400" />
        Resource Library
      </h1>

      {/* ── PDF Browse ── */}
      <section>
        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <Filter className="h-4 w-4 text-slate-400" />

          <div className="w-52">
            <ModuleSelector
              modules={modulesData?.modules || []}
              moduleGroups={modulesData?.module_groups || []}
              selectedModule={filterModule}
              onSelect={handleFilterModuleSelect}
            />
          </div>

          <PDFFilterDropdown
            label="Topics"
            items={filterData?.topics || []}
            selected={filterTopics}
            onChange={setFilterTopics}
            isOpen={openDropdown === 'topics'}
            onToggle={() => setOpenDropdown(openDropdown === 'topics' ? null : 'topics')}
            onClose={() => setOpenDropdown(null)}
            disabled={!filterModule}
          />
          <PDFFilterDropdown
            label="Subtopics"
            items={filterData?.subtopics || []}
            selected={filterSubtopics}
            onChange={setFilterSubtopics}
            isOpen={openDropdown === 'subtopics'}
            onToggle={() => setOpenDropdown(openDropdown === 'subtopics' ? null : 'subtopics')}
            onClose={() => setOpenDropdown(null)}
            disabled={!filterModule}
          />
          <PDFFilterDropdown
            label="Tags"
            items={filterData?.tags || []}
            selected={filterTags}
            onChange={setFilterTags}
            isOpen={openDropdown === 'tags'}
            onToggle={() => setOpenDropdown(openDropdown === 'tags' ? null : 'tags')}
            onClose={() => setOpenDropdown(null)}
            disabled={!filterModule}
          />

          {hasActiveFilters && (
            <button
              onClick={() => {
                setFilterModule('');
                setFilterModuleId(undefined);
                setFilterTopics([]);
                setFilterSubtopics([]);
                setFilterTags([]);
              }}
              className="flex items-center gap-1 px-3 py-2 text-sm text-slate-400 hover:text-white transition-colors"
            >
              <X className="h-4 w-4" /> Clear
            </button>
          )}

          {isAdmin && (
            <label className="ml-auto flex items-center gap-2 text-sm text-slate-400">
              <input
                type="checkbox"
                checked={showInactive}
                onChange={e => setShowInactive(e.target.checked)}
                className="rounded border-slate-600 bg-slate-800"
              />
              Show deleted
            </label>
          )}
        </div>

        {/* PDF grid */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500" />
          </div>
        ) : pdfs.length === 0 ? (
          <div className="card p-12 text-center text-slate-400">
            <FileText className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p>No PDFs found{hasActiveFilters ? ' matching your filters' : ''}.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {pdfs.map((pdf: PDF) => (
              <PDFCard
                key={pdf.id}
                pdf={pdf}
                isAdmin={!!isAdmin}
                onEdit={() => setEditingPDF(pdf.id)}
                onDelete={() => {
                  if (confirm('Mark this PDF as deleted?')) deleteMutation.mutate(pdf.id);
                }}
                onHardDelete={() => {
                  if (confirm('Permanently delete this PDF? This cannot be undone.')) hardDeleteMutation.mutate(pdf.id);
                }}
                onRestore={() => restoreMutation.mutate(pdf.id)}
              />
            ))}
          </div>
        )}

        <p className="text-xs text-slate-500 mt-3">
          {pdfsData?.total ?? 0} PDF{pdfsData?.total !== 1 ? 's' : ''}
        </p>
      </section>

      {/* ── Upload / Submit ── */}
      <section className="card p-6">
        <h2 className="text-lg font-semibold text-white mb-1">Submit a PDF</h2>
        <p className="text-sm text-slate-400 mb-4">
          Submissions are reviewed by an admin before appearing in the library.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Module (required)</label>
            <ModuleSelector
              modules={modulesData?.modules || []}
              moduleGroups={modulesData?.module_groups || []}
              selectedModule={uploadModule}
              onSelect={handleUploadModuleSelect}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 mb-4">
          <PDFFilterDropdown
            label="Topics"
            items={uploadFilterData?.topics || []}
            selected={uploadTopics}
            onChange={setUploadTopics}
            isOpen={uploadDropdown === 'topics'}
            onToggle={() => setUploadDropdown(uploadDropdown === 'topics' ? null : 'topics')}
            onClose={() => setUploadDropdown(null)}
            disabled={!uploadModule}
          />
          <PDFFilterDropdown
            label="Subtopics"
            items={uploadFilterData?.subtopics || []}
            selected={uploadSubtopics}
            onChange={setUploadSubtopics}
            isOpen={uploadDropdown === 'subtopics'}
            onToggle={() => setUploadDropdown(uploadDropdown === 'subtopics' ? null : 'subtopics')}
            onClose={() => setUploadDropdown(null)}
            disabled={!uploadModule}
          />
          <PDFFilterDropdown
            label="Tags"
            items={uploadFilterData?.tags || []}
            selected={uploadTags}
            onChange={setUploadTags}
            isOpen={uploadDropdown === 'tags'}
            onToggle={() => setUploadDropdown(uploadDropdown === 'tags' ? null : 'tags')}
            onClose={() => setUploadDropdown(null)}
            disabled={!uploadModule}
          />
        </div>

        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
            isDragActive ? 'border-blue-500 bg-blue-500/10' : 'border-slate-600 hover:border-slate-500'
          }`}
        >
          <input {...getInputProps()} />
          <Upload className="h-10 w-10 mx-auto mb-3 text-slate-400" />
          {isDragActive ? (
            <p className="text-blue-400">Drop the PDFs here...</p>
          ) : (
            <p className="text-slate-400">Drag & drop PDF files here, or click to select</p>
          )}
        </div>

        {pendingFiles.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="text-sm font-medium text-slate-300">
              {pendingFiles.length} file{pendingFiles.length > 1 ? 's' : ''} selected
            </p>
            {pendingFiles.map((file, i) => (
              <div key={i} className="flex items-center justify-between p-2 bg-slate-800 rounded">
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="h-4 w-4 text-slate-400 flex-shrink-0" />
                  <span className="text-sm text-white truncate">{file.name}</span>
                  <span className="text-xs text-slate-500 flex-shrink-0">{formatSize(file.size)}</span>
                </div>
                <button onClick={() => setPendingFiles(p => p.filter((_, j) => j !== i))} className="p-1 text-slate-400 hover:text-red-400">
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}

            {uploadError && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400 text-sm">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                {uploadError}
              </div>
            )}

            <button
              onClick={() => submitMutation.mutate()}
              disabled={!uploadModuleId || submitMutation.isPending}
              className="mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:cursor-not-allowed text-white rounded-lg flex items-center gap-2 text-sm"
            >
              {submitMutation.isPending ? (
                <><div className="animate-spin rounded-full h-4 w-4 border-t-2 border-white" /> Processing...</>
              ) : (
                <><Upload className="h-4 w-4" /> Submit for Review ({pendingFiles.length} file{pendingFiles.length > 1 ? 's' : ''})</>
              )}
            </button>
          </div>
        )}
      </section>

      {editingPDF && (
        <EditPDFModal
          pdfId={editingPDF}
          modules={modulesData?.modules || []}
          moduleGroups={modulesData?.module_groups || []}
          onClose={() => setEditingPDF(null)}
          onSave={() => {
            setEditingPDF(null);
            queryClient.invalidateQueries({ queryKey: ['pdfs'] });
          }}
        />
      )}
    </div>
  );
}

function ChipList({
  items,
  max,
  chipClass,
}: {
  items: string[];
  max: number;
  chipClass: string;
}) {
  if (items.length === 0) return null;
  const visible = items.slice(0, max);
  const hidden = items.length - max;
  return (
    <div className="flex flex-wrap gap-1">
      {visible.map(item => (
        <span key={item} className={`px-2 py-0.5 text-xs rounded-full ${chipClass}`}>{item}</span>
      ))}
      {hidden > 0 && (
        <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700 text-slate-400" title={items.slice(max).join(', ')}>
          +{hidden}
        </span>
      )}
    </div>
  );
}

function PDFCard({
  pdf,
  isAdmin,
  onEdit,
  onDelete,
  onHardDelete,
  onRestore,
}: {
  pdf: PDF;
  isAdmin: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onHardDelete: () => void;
  onRestore: () => void;
}) {
  const formatSize = (bytes?: number) => {
    if (!bytes) return '';
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={`card p-4 flex flex-col gap-2.5 ${!pdf.is_active ? 'opacity-50' : ''}`}>
      {/* Header */}
      <div className="flex items-start gap-2">
        <FileText className="h-5 w-5 text-blue-400 flex-shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-white truncate" title={pdf.original_filename}>
            {pdf.original_filename}
          </p>
          {pdf.module_name && (
            <p className="text-xs text-slate-400">{pdf.module_name}</p>
          )}
        </div>
        {!pdf.is_active && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 flex-shrink-0">Deleted</span>
        )}
      </div>

      {/* Topics — max 3 */}
      <ChipList
        items={pdf.topic_names ?? []}
        max={3}
        chipClass="bg-violet-900/40 text-violet-300"
      />

      {/* Subtopics — max 2 */}
      <ChipList
        items={pdf.subtopic_names ?? []}
        max={2}
        chipClass="bg-blue-900/30 text-blue-300"
      />

      {/* Tags — max 5, rounded squares */}
      {(pdf.tag_names?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-1">
          {pdf.tag_names!.slice(0, 5).map(t => (
            <span key={t} className="px-1.5 py-0.5 text-xs rounded bg-slate-700 text-slate-400">{t}</span>
          ))}
          {pdf.tag_names!.length > 5 && (
            <span
              className="px-1.5 py-0.5 text-xs rounded bg-slate-700/60 text-slate-500"
              title={pdf.tag_names!.slice(5).join(', ')}
            >
              +{pdf.tag_names!.length - 5}
            </span>
          )}
        </div>
      )}

      {/* Footer: size + actions */}
      <div className="flex items-center justify-between pt-2 mt-auto border-t border-slate-700/50">
        <span className="text-xs text-slate-500">{formatSize(pdf.file_size)}</span>
        <div className="flex items-center gap-1">
          <a
            href={pdf.url || `/api/pdf/${pdf.id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded"
            title="View PDF"
          >
            <Eye className="h-4 w-4" />
          </a>
          {isAdmin && pdf.is_active && (
            <>
              <button onClick={onEdit} className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded" title="Edit">
                <Edit2 className="h-4 w-4" />
              </button>
              <button onClick={onDelete} className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded" title="Delete">
                <Trash2 className="h-4 w-4" />
              </button>
            </>
          )}
          {isAdmin && !pdf.is_active && (
            <>
              <button onClick={onRestore} className="p-1.5 text-slate-400 hover:text-green-400 hover:bg-slate-700 rounded" title="Restore">
                <RotateCcw className="h-4 w-4" />
              </button>
              <button onClick={onHardDelete} className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded" title="Permanently Delete">
                <Trash2 className="h-4 w-4" />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function PDFFilterDropdown({
  label,
  items,
  selected,
  onChange,
  isOpen,
  onToggle,
  onClose,
  disabled,
}: {
  label: string;
  items: string[];
  selected: string[];
  onChange: (items: string[]) => void;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isOpen, onClose]);

  const toggleItem = (item: string) => {
    if (selected.includes(item)) {
      onChange(selected.filter(i => i !== item));
    } else {
      onChange([...selected, item]);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={onToggle}
        disabled={disabled || items.length === 0}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg border transition-colors text-sm ${
          selected.length > 0
            ? 'bg-blue-600/20 border-blue-500 text-blue-400'
            : 'bg-slate-800 border-slate-600 text-slate-300 hover:border-slate-500'
        } ${disabled || items.length === 0 ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <span>
          {label}
          {selected.length > 0 && (
            <span className="ml-1 px-1.5 py-0.5 bg-blue-600 text-white text-xs rounded-full">
              {selected.length}
            </span>
          )}
        </span>
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && items.length > 0 && (
        <div className="absolute z-50 mt-2 w-64 max-h-64 overflow-y-auto rounded-lg bg-slate-800 border border-slate-700 shadow-xl">
          {items.map(item => (
            <button
              key={item}
              onClick={() => toggleItem(item)}
              className={`w-full flex items-center gap-2 px-4 py-2 text-left text-sm hover:bg-slate-700 transition-colors ${
                selected.includes(item) ? 'bg-blue-600/20 text-blue-400' : 'text-slate-300'
              }`}
            >
              <div
                className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                  selected.includes(item) ? 'bg-blue-600 border-blue-600' : 'border-slate-500'
                }`}
              >
                {selected.includes(item) && (
                  <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>
              <span className="truncate">{item}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function EditPDFModal({
  pdfId,
  modules,
  moduleGroups,
  onClose,
  onSave,
}: {
  pdfId: number;
  modules: Array<{ id: number; name: string; year?: number }>;
  moduleGroups: Array<{ year: string; modules: Array<{ id: number; name: string }> }>;
  onClose: () => void;
  onSave: () => void;
}) {
  const [editModule, setEditModule] = useState<string>('');
  const [editModuleId, setEditModuleId] = useState<number | undefined>();
  const [topics, setTopics] = useState<string[]>([]);
  const [subtopics, setSubtopics] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const { data: pdf } = useQuery({
    queryKey: ['pdf-info', pdfId],
    queryFn: () => api.getPDFInfo(pdfId),
  });

  // Prepopulate fields once PDF data loads
  const [initialized, setInitialized] = useState(false);
  useEffect(() => {
    if (pdf && !initialized) {
      setEditModule(pdf.module_name || '');
      setEditModuleId(pdf.module_id || undefined);
      setTopics(pdf.topic_names || []);
      setSubtopics(pdf.subtopic_names || []);
      setTags(pdf.tag_names || []);
      setInitialized(true);
    }
  }, [pdf, initialized]);

  const handleModuleChange = (moduleName: string) => {
    setEditModule(moduleName);
    const mod = modules.find(m => m.name === moduleName);
    setEditModuleId(mod?.id);
    setTopics([]);
    setSubtopics([]);
  };

  const fetchTopics = useCallback(async (q: string) => {
    if (!editModule) return [];
    const res = await api.suggestTopics(editModule, q);
    return res.suggestions || [];
  }, [editModule]);

  const fetchSubtopics = useCallback(async (q: string) => {
    if (!editModule) return [];
    const topic = topics[0] || '';
    const res = await api.suggestSubtopics(editModule, topic, q);
    return res.suggestions || [];
  }, [editModule, topics]);

  const fetchTags = useCallback(async (q: string) => {
    if (!editModule) return [];
    const res = await api.suggestTags(editModule, q);
    return res.suggestions || [];
  }, [editModule]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updatePDF(pdfId, {
        module_id: editModuleId,
        topic_names: topics.filter(Boolean),
        subtopic_names: subtopics.filter(Boolean),
        tag_names: tags.filter(Boolean),
      });
      onSave();
    } catch {
      toast.error('Failed to update PDF');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">Edit PDF Metadata</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </div>

        {pdf && (
          <p className="text-sm text-slate-400 mb-4 truncate" title={pdf.original_filename}>
            {pdf.original_filename}
          </p>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Module</label>
            <ModuleSelector
              modules={modules}
              moduleGroups={moduleGroups}
              selectedModule={editModule}
              onSelect={handleModuleChange}
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Topics</label>
            <MultiSelectField values={topics} onChange={setTopics} onFetch={fetchTopics} placeholder="Add topics..." disabled={!editModule} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Subtopics</label>
            <MultiSelectField values={subtopics} onChange={setSubtopics} onFetch={fetchSubtopics} placeholder="Add subtopics..." disabled={!editModule} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Tags</label>
            <TagInput tags={tags} onChange={setTags} onFetch={fetchTags} minCount={0} disabled={!editModule} />
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button onClick={onClose} className="px-4 py-2 text-slate-400 hover:text-white">Cancel</button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 text-white rounded-lg flex items-center gap-2"
          >
            {saving ? <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-white" /> : <Check className="h-4 w-4" />}
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
