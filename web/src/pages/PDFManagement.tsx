import { useState, useCallback, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, Trash2, RotateCcw, Eye, Edit2, X, Check, AlertCircle } from 'lucide-react';
import { api } from '../api/client';
import ModuleSelector from '../components/ModuleSelector';
import MultiSelectField from '../components/MultiSelectField';
import TagInput from '../components/TagInput';

interface PDFItem {
  id: number;
  storage_path: string;
  original_filename: string;
  file_size?: number;
  mime_type: string;
  module_id?: number;
  module_name?: string;
  is_active: boolean;
}

export default function PDFManagement() {
  const queryClient = useQueryClient();
  const [selectedModule, setSelectedModule] = useState<string>('');
  const [selectedModuleId, setSelectedModuleId] = useState<number | undefined>();
  const [showInactive, setShowInactive] = useState(false);
  const [uploadTopics, setUploadTopics] = useState<string[]>([]);
  const [uploadSubtopics, setUploadSubtopics] = useState<string[]>([]);
  const [uploadTags, setUploadTags] = useState<string[]>([]);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState<string>('');
  const [editingPDF, setEditingPDF] = useState<number | null>(null);

  const { data: modulesData } = useQuery({
    queryKey: ['modules'],
    queryFn: api.getModules,
  });

  const { data: pdfsData, isLoading } = useQuery({
    queryKey: ['admin-pdfs', selectedModuleId, showInactive],
    queryFn: () => api.listPDFs({
      module_id: selectedModuleId,
      is_active: !showInactive,
      limit: 100,
    }),
    enabled: true,
  });

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!selectedModuleId || pendingFiles.length === 0) {
        throw new Error('Please select a module and add files');
      }

      const topicNames = uploadTopics.filter(Boolean);
      const subtopicNames = uploadSubtopics.filter(Boolean);
      const tagNames = uploadTags.filter(Boolean);

      if (pendingFiles.length === 1) {
        return api.adminUploadPDF(pendingFiles[0], {
          module_id: selectedModuleId,
          topic_names: topicNames,
          subtopic_names: subtopicNames,
          tag_names: tagNames,
        });
      } else {
        return api.batchSubmitPDFs(pendingFiles, {
          module_id: selectedModuleId,
          topic_names: topicNames,
          subtopic_names: subtopicNames,
          tag_names: tagNames,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-pdfs'] });
      setPendingFiles([]);
      setUploadTopics([]);
      setUploadSubtopics([]);
      setUploadTags([]);
      setUploadError('');
    },
    onError: (error: Error) => {
      setUploadError(error.message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (pdfId: number) => api.deletePDF(pdfId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-pdfs'] });
    },
  });

  const hardDeleteMutation = useMutation({
    mutationFn: (pdfId: number) => api.hardDeletePDF(pdfId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-pdfs'] });
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (pdfId: number) => api.restorePDF(pdfId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-pdfs'] });
    },
  });

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const pdfFiles = acceptedFiles.filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'));
    setPendingFiles(prev => [...prev, ...pdfFiles]);
    setUploadError('');
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
  });

  const handleModuleSelect = (moduleName: string) => {
    setSelectedModule(moduleName);
    const module = modulesData?.modules.find(m => m.name === moduleName);
    setSelectedModuleId(module?.id);
    setUploadTopics([]);
    setUploadSubtopics([]);
  };

  const fetchTopicSuggestions = useCallback(
    async (query: string) => {
      if (!selectedModule) return [];
      const result = await api.suggestTopics(selectedModule, query);
      return result.suggestions || [];
    },
    [selectedModule]
  );

  const fetchSubtopicSuggestions = useCallback(
    async (query: string) => {
      if (!selectedModule) return [];
      // If topics are selected, get subtopics for the first topic (for suggestions)
      // The API only supports one topic at a time for subtopic suggestions
      const topic = uploadTopics.length > 0 ? uploadTopics[0] : '';
      const result = await api.suggestSubtopics(selectedModule, topic, query);
      return result.suggestions || [];
    },
    [selectedModule, uploadTopics]
  );

  const fetchTagSuggestions = useCallback(
    async (query: string) => {
      if (!selectedModule) return [];
      const result = await api.suggestTags(selectedModule, query);
      return result.suggestions || [];
    },
    [selectedModule]
  );

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const removePendingFile = (index: number) => {
    setPendingFiles(prev => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
        <FileText className="h-7 w-7" />
        PDF Management
      </h1>

      {/* Upload Section */}
      <div className="card p-6 mb-6">
        <h2 className="text-lg font-semibold text-white mb-4">Upload PDFs</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Module (required)</label>
            <ModuleSelector
              modules={modulesData?.modules || []}
              moduleGroups={modulesData?.module_groups || []}
              selectedModule={selectedModule}
              onSelect={handleModuleSelect}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Topics</label>
            <MultiSelectField
              values={uploadTopics}
              onChange={setUploadTopics}
              onFetch={fetchTopicSuggestions}
              placeholder="Select or add topics..."
              disabled={!selectedModule}
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Subtopics</label>
            <MultiSelectField
              values={uploadSubtopics}
              onChange={setUploadSubtopics}
              onFetch={fetchSubtopicSuggestions}
              placeholder="Select or add subtopics..."
              disabled={!selectedModule}
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Tags</label>
            <TagInput
              tags={uploadTags}
              onChange={setUploadTags}
              onFetch={fetchTagSuggestions}
              minCount={0}
              disabled={!selectedModule}
            />
          </div>
        </div>

        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
            isDragActive
              ? 'border-blue-500 bg-blue-500/10'
              : 'border-slate-600 hover:border-slate-500'
          }`}
        >
          <input {...getInputProps()} />
          <Upload className="h-10 w-10 mx-auto mb-3 text-slate-400" />
          {isDragActive ? (
            <p className="text-blue-400">Drop the PDFs here...</p>
          ) : (
            <p className="text-slate-400">
              Drag & drop PDF files here, or click to select
            </p>
          )}
        </div>

        {pendingFiles.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-medium text-slate-300 mb-2">
              Files to upload ({pendingFiles.length})
            </h3>
            <div className="space-y-2">
              {pendingFiles.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-2 bg-slate-800 rounded"
                >
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-slate-400" />
                    <span className="text-sm text-white">{file.name}</span>
                    <span className="text-xs text-slate-500">
                      ({formatFileSize(file.size)})
                    </span>
                  </div>
                  <button
                    onClick={() => removePendingFile(index)}
                    className="p-1 text-slate-400 hover:text-red-400"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>

            {uploadError && (
              <div className="mt-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center gap-2 text-red-400">
                <AlertCircle className="h-4 w-4" />
                {uploadError}
              </div>
            )}

            <button
              onClick={() => uploadMutation.mutate()}
              disabled={!selectedModuleId || uploadMutation.isPending}
              className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:cursor-not-allowed text-white rounded-lg flex items-center gap-2"
            >
              {uploadMutation.isPending ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-white" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4" />
                  Upload {pendingFiles.length} file{pendingFiles.length > 1 ? 's' : ''}
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* PDF List Section */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">
            PDFs {pdfsData?.total ? `(${pdfsData.total})` : ''}
          </h2>
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
              className="rounded border-slate-600 bg-slate-800"
            />
            Show deleted
          </label>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500" />
          </div>
        ) : pdfsData?.pdfs.length === 0 ? (
          <p className="text-center text-slate-400 py-8">
            No PDFs found. Upload some PDFs to get started.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-slate-400 border-b border-slate-700">
                  <th className="pb-3 font-medium">Filename</th>
                  <th className="pb-3 font-medium">Module</th>
                  <th className="pb-3 font-medium">Size</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {pdfsData?.pdfs.map((pdf: PDFItem) => (
                  <tr key={pdf.id} className={!pdf.is_active ? 'opacity-50' : ''}>
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-slate-400" />
                        <span className="text-white">{pdf.original_filename}</span>
                      </div>
                    </td>
                    <td className="py-3 text-slate-300">{pdf.module_name || '-'}</td>
                    <td className="py-3 text-slate-400">{formatFileSize(pdf.file_size)}</td>
                    <td className="py-3">
                      {pdf.is_active ? (
                        <span className="px-2 py-1 text-xs bg-green-500/20 text-green-400 rounded">
                          Active
                        </span>
                      ) : (
                        <span className="px-2 py-1 text-xs bg-red-500/20 text-red-400 rounded">
                          Deleted
                        </span>
                      )}
                    </td>
                    <td className="py-3">
                      <div className="flex items-center justify-end gap-2">
                        <a
                          href={`/api/pdf/${pdf.id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded"
                          title="View"
                        >
                          <Eye className="h-4 w-4" />
                        </a>
                        {pdf.is_active ? (
                          <>
                            <button
                              onClick={() => setEditingPDF(pdf.id)}
                              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded"
                              title="Edit"
                            >
                              <Edit2 className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm('Mark this PDF as deleted?')) {
                                  deleteMutation.mutate(pdf.id);
                                }
                              }}
                              className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded"
                              title="Delete"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              onClick={() => restoreMutation.mutate(pdf.id)}
                              className="p-1.5 text-slate-400 hover:text-green-400 hover:bg-slate-700 rounded"
                              title="Restore"
                            >
                              <RotateCcw className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => {
                                if (confirm('Permanently delete this PDF? This cannot be undone.')) {
                                  hardDeleteMutation.mutate(pdf.id);
                                }
                              }}
                              className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-slate-700 rounded"
                              title="Permanently Delete"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Edit Modal */}
      {editingPDF && (
        <EditPDFModal
          pdfId={editingPDF}
          modules={modulesData?.modules || []}
          moduleGroups={modulesData?.module_groups || []}
          onClose={() => setEditingPDF(null)}
          onSave={() => {
            setEditingPDF(null);
            queryClient.invalidateQueries({ queryKey: ['admin-pdfs'] });
          }}
        />
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

  const fetchTopicSuggestions = useCallback(
    async (query: string) => {
      if (!editModule) return [];
      const result = await api.suggestTopics(editModule, query);
      return result.suggestions || [];
    },
    [editModule]
  );

  const fetchSubtopicSuggestions = useCallback(
    async (query: string) => {
      if (!editModule) return [];
      const topic = topics.length > 0 ? topics[0] : '';
      const result = await api.suggestSubtopics(editModule, topic, query);
      return result.suggestions || [];
    },
    [editModule, topics]
  );

  const fetchTagSuggestions = useCallback(
    async (query: string) => {
      if (!editModule) return [];
      const result = await api.suggestTags(editModule, query);
      return result.suggestions || [];
    },
    [editModule]
  );

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
    } catch (error) {
      console.error('Failed to update PDF:', error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-slate-800 rounded-lg p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
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
            <MultiSelectField
              values={topics}
              onChange={setTopics}
              onFetch={fetchTopicSuggestions}
              placeholder="Select or add topics..."
              disabled={!editModule}
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Subtopics</label>
            <MultiSelectField
              values={subtopics}
              onChange={setSubtopics}
              onFetch={fetchSubtopicSuggestions}
              placeholder="Select or add subtopics..."
              disabled={!editModule}
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Tags</label>
            <TagInput
              tags={tags}
              onChange={setTags}
              onFetch={fetchTagSuggestions}
              minCount={0}
              disabled={!editModule}
            />
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-slate-400 hover:text-white"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 text-white rounded-lg flex items-center gap-2"
          >
            {saving ? (
              <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-white" />
            ) : (
              <Check className="h-4 w-4" />
            )}
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
