import type {
  User,
  Module,
  ModuleGroup,
  FilterData,
  QuestionResponse,
  CheckAnswerResponse,
  UserStats,
  ModuleStats,
  LeaderboardEntry,
  AdminSubmissions,
} from '../types';

const API_BASE = '/api';

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Request failed' }));
    throw new Error(error.error || `HTTP ${response.status}`);
  }

  return response.json();
}

export const api = {
  getMe: () => fetchJSON<User>(`${API_BASE}/me`),

  getRecentActivity: () =>
    fetchJSON<{ activities: { user_id: string; username: string; module_name: string; streak: number; answered_at: string }[] }>(
      `${API_BASE}/recent-activity`
    ),

  getModules: () =>
    fetchJSON<{ modules: Module[]; module_groups: ModuleGroup[] }>(`${API_BASE}/modules`),

  getFilters: (module: string, topics: string[] = []) =>
    fetchJSON<FilterData>(`${API_BASE}/filters`, {
      method: 'POST',
      body: JSON.stringify({ module, topics }),
    }),

  suggestTopics: (module: string, query = '') =>
    fetchJSON<{ suggestions: { name: string; count: number }[] }>(`${API_BASE}/suggest/topics`, {
      method: 'POST',
      body: JSON.stringify({ module, query }),
    }),

  suggestSubtopics: (module: string, topic: string, query = '') =>
    fetchJSON<{ suggestions: { name: string; count: number }[] }>(`${API_BASE}/suggest/subtopics`, {
      method: 'POST',
      body: JSON.stringify({ module, topic, query }),
    }),

  suggestTags: (module: string, query = '') =>
    fetchJSON<{ suggestions: { name: string; count: number }[] }>(`${API_BASE}/suggest/tags`, {
      method: 'POST',
      body: JSON.stringify({ module, query }),
    }),

  getQuestion: (params: {
    module: string;
    topics?: string[];
    subtopics?: string[];
    tags?: string[];
    question_id?: string;
  }) =>
    fetchJSON<QuestionResponse>(`${API_BASE}/question`, {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  checkAnswer: (token: string, answer: string) =>
    fetchJSON<CheckAnswerResponse>(`${API_BASE}/check-answer`, {
      method: 'POST',
      body: JSON.stringify({ token, answer }),
    }),

  getStats: () =>
    fetchJSON<{ user_stats: UserStats; module_stats: ModuleStats[] }>(`${API_BASE}/stats`),

  getUserStats: (userId: string) =>
    fetchJSON<{ user_stats: UserStats; module_stats: ModuleStats[] }>(
      `${API_BASE}/stats/${userId}`
    ),

  getLeaderboard: (sort = 'correct_answers', order = 'desc', module?: string) => {
    const params = new URLSearchParams({ sort, order });
    if (module) params.set('module', module);
    return fetchJSON<{ leaderboard: LeaderboardEntry[] }>(
      `${API_BASE}/leaderboard?${params}`
    );
  },

  checkDuplicates: (question: string, module: string) =>
    fetchJSON<{ matches: { reason: string; id: string; question: string; answer: string; similarity: number }[] }>(
      `${API_BASE}/check-duplicates`,
      {
        method: 'POST',
        body: JSON.stringify({ question, module }),
      }
    ),

  submitFlashcard: (data: {
    question: string;
    answer: string;
    module: string;
    topic: string;
    subtopic: string;
    tags: string;
    distractors?: string[];
  }) =>
    fetchJSON<{ success: boolean; message: string }>(`${API_BASE}/submit-flashcard`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  submitDistractor: (questionId: string, distractors: string[]) =>
    fetchJSON<{ success: boolean; message: string }>(`${API_BASE}/submit-distractor`, {
      method: 'POST',
      body: JSON.stringify({ question_id: questionId, distractors }),
    }),

  reportQuestion: (data: {
    question: string;
    question_id?: string;
    message: string;
    distractors?: string;
  }) =>
    fetchJSON<{ success: boolean; message: string }>(`${API_BASE}/report-question`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  requestPDFAccess: (message?: string) =>
    fetchJSON<{ success: boolean; message: string }>(`${API_BASE}/request-pdf-access`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),

  getAdminSubmissions: () => fetchJSON<AdminSubmissions>(`${API_BASE}/admin/submissions`),

  approveFlashcard: (data: {
    submission_id: number;
    question: string;
    answer: string;
    module: string;
    topic?: string;
    subtopic?: string;
    tags?: string[];
  }) =>
    fetchJSON<{ success: boolean; question_id?: string; pending_distractors_count?: number }>(
      `${API_BASE}/admin/approve-flashcard`,
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    ),

  rejectFlashcard: (submissionId: number) =>
    fetchJSON<{ success: boolean; rejected_distractors_count?: number }>(
      `${API_BASE}/admin/reject-flashcard`,
      {
        method: 'POST',
        body: JSON.stringify({ submission_id: submissionId }),
      }
    ),

  approveDistractor: (submissionId: number) =>
    fetchJSON<{ success: boolean; distractor_id?: number }>(
      `${API_BASE}/admin/approve-distractor`,
      {
        method: 'POST',
        body: JSON.stringify({ submission_id: submissionId }),
      }
    ),

  rejectDistractor: (submissionId: number) =>
    fetchJSON<{ success: boolean }>(`${API_BASE}/admin/reject-distractor`, {
      method: 'POST',
      body: JSON.stringify({ submission_id: submissionId }),
    }),

  discardReport: (reportId: number) =>
    fetchJSON<{ success: boolean }>(`${API_BASE}/admin/discard-report`, {
      method: 'POST',
      body: JSON.stringify({ report_id: reportId }),
    }),

  getQuestionForReport: (questionId: string) =>
    fetchJSON<{
      question: { id: string; question: string; answer: string };
      distractors: { id: number; distractor_text: string }[];
    }>(`${API_BASE}/admin/question/${questionId}`),

  resolveReport: (data: {
    report_id: number;
    question_id?: string;
    new_question_text?: string;
    new_question_answer?: string;
    delete_question?: boolean;
    distractors?: { id: number; type: string; new_text?: string; delete?: boolean }[];
  }) =>
    fetchJSON<{ success: boolean }>(`${API_BASE}/admin/resolve-report`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  approvePDFAccess: (requestId: number) =>
    fetchJSON<{ success: boolean }>(`${API_BASE}/admin/approve-pdf-access`, {
      method: 'POST',
      body: JSON.stringify({ request_id: requestId }),
    }),

  denyPDFAccess: (requestId: number) =>
    fetchJSON<{ success: boolean }>(`${API_BASE}/admin/deny-pdf-access`, {
      method: 'POST',
      body: JSON.stringify({ request_id: requestId }),
    }),

  checkDuplicates: (question: string, module: string) =>
    fetchJSON<{ matches: { reason: string; id: string; question: string; answer: string; similarity: number }[] }>(
      `${API_BASE}/check-duplicates`,
      {
        method: 'POST',
        body: JSON.stringify({ question, module }),
      }
    ),

  editAnswer: (data: {
    question_id?: string;
    manual_distractor_id?: number;
    new_text: string;
    edit_type: string;
  }) =>
    fetchJSON<{ success: boolean }>(`${API_BASE}/admin/edit-answer`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // PDF browsing — all whitelisted users
  listPDFs: (params?: { module_id?: number; is_active?: boolean; topic?: string; subtopic?: string; tag?: string; limit?: number; offset?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.module_id) searchParams.set('module_id', String(params.module_id));
    if (params?.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    if (params?.topic) searchParams.set('topic', params.topic);
    if (params?.subtopic) searchParams.set('subtopic', params.subtopic);
    if (params?.tag) searchParams.set('tag', params.tag);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    return fetchJSON<{ success: boolean; pdfs: PDF[]; total: number; limit: number; offset: number }>(
      `${API_BASE}/pdfs/list?${searchParams}`
    );
  },

  // PDF submission — whitelisted users submit for review
  submitPDF: async (file: File, metadata: PDFMetadata) => {
    const formData = buildPDFFormData(file, metadata);
    const response = await fetch(`${API_BASE}/pdfs/submit`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Upload failed' }));
      throw new Error(error.error || `HTTP ${response.status}`);
    }
    return response.json() as Promise<{ success: boolean; pending: boolean; message: string }>;
  },

  batchSubmitPDFs: async (files: File[], metadata: PDFMetadata) => {
    const formData = new FormData();
    files.forEach(f => formData.append('files', f));
    appendMetadataToForm(formData, metadata);
    const response = await fetch(`${API_BASE}/pdfs/batch-submit`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Upload failed' }));
      throw new Error(error.error || `HTTP ${response.status}`);
    }
    return response.json() as Promise<{ success: boolean; pending: boolean; message: string }>;
  },

  // Admin PDF management
  getPDFInfo: (pdfId: number) =>
    fetchJSON<PDF>(`${API_BASE}/admin/pdfs/${pdfId}`),

  adminListPDFs: (params?: { module_id?: number; is_active?: boolean; topic?: string; subtopic?: string; tag?: string; limit?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.module_id) searchParams.set('module_id', String(params.module_id));
    if (params?.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    if (params?.topic) searchParams.set('topic', params.topic);
    if (params?.subtopic) searchParams.set('subtopic', params.subtopic);
    if (params?.tag) searchParams.set('tag', params.tag);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    return fetchJSON<{ success: boolean; pdfs: PDF[]; total: number; limit: number; offset: number }>(
      `${API_BASE}/admin/pdfs/list?${searchParams}`
    );
  },

  adminUploadPDF: async (file: File, metadata: PDFMetadata) => {
    const formData = buildPDFFormData(file, metadata);
    const response = await fetch(`${API_BASE}/admin/pdfs/upload`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Upload failed' }));
      throw new Error(error.error || `HTTP ${response.status}`);
    }
    return response.json() as Promise<{ success: boolean; pdf: PDF; message: string }>;
  },

  updatePDF: (pdfId: number, data: {
    module_id?: number;
    topic_ids?: number[];
    subtopic_ids?: number[];
    tag_ids?: number[];
    topic_names?: string[];
    subtopic_names?: string[];
    tag_names?: string[];
  }) =>
    fetchJSON<{ success: boolean; pdf: PDF; message: string }>(`${API_BASE}/admin/pdfs/${pdfId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deletePDF: (pdfId: number) =>
    fetchJSON<{ success: boolean; message: string }>(`${API_BASE}/admin/pdfs/${pdfId}`, {
      method: 'DELETE',
    }),

  hardDeletePDF: (pdfId: number) =>
    fetchJSON<{ success: boolean; message: string }>(`${API_BASE}/admin/pdfs/${pdfId}/hard-delete`, {
      method: 'DELETE',
    }),

  restorePDF: (pdfId: number) =>
    fetchJSON<{ success: boolean; message: string }>(`${API_BASE}/admin/pdfs/${pdfId}/restore`, {
      method: 'POST',
    }),

  // Admin PDF approval queue
  listSubmittedPDFs: () =>
    fetchJSON<{ success: boolean; pdfs: SubmittedPDF[] }>(`${API_BASE}/admin/pdfs/submitted`),

  approvePDF: (submittedId: number) =>
    fetchJSON<{ success: boolean; pdf_id: number; message: string }>(`${API_BASE}/admin/pdfs/approve`, {
      method: 'POST',
      body: JSON.stringify({ submitted_id: submittedId }),
    }),

  rejectPDF: (submittedId: number) =>
    fetchJSON<{ success: boolean; message: string }>(`${API_BASE}/admin/pdfs/reject`, {
      method: 'POST',
      body: JSON.stringify({ submitted_id: submittedId }),
    }),
};

interface PDFMetadata {
  module_id?: number;
  module_name?: string;
  topic_names?: string[];
  subtopic_names?: string[];
  tag_names?: string[];
}

function buildPDFFormData(file: File, metadata: PDFMetadata): FormData {
  const formData = new FormData();
  formData.append('file', file);
  appendMetadataToForm(formData, metadata);
  return formData;
}

function appendMetadataToForm(formData: FormData, metadata: PDFMetadata): void {
  if (metadata.module_id) formData.append('module_id', String(metadata.module_id));
  if (metadata.module_name) formData.append('module_name', metadata.module_name);
  metadata.topic_names?.forEach(t => formData.append('topic_names', t));
  metadata.subtopic_names?.forEach(s => formData.append('subtopic_names', s));
  metadata.tag_names?.forEach(t => formData.append('tag_names', t));
}

export interface PDF {
  id: number;
  storage_path: string;
  original_filename: string;
  file_size?: number;
  mime_type: string;
  module_id?: number;
  module_name?: string;
  is_active: boolean;
  match_percent?: number;
  match_reasons?: string[];
  url?: string;
  topic_ids?: number[];
  subtopic_ids?: number[];
  tag_ids?: number[];
  topic_names?: string[];
  subtopic_names?: string[];
  tag_names?: string[];
}

export interface SubmittedPDF {
  id: number;
  storage_path: string;
  original_filename: string;
  file_size?: number;
  mime_type: string;
  module_id?: number;
  module_name?: string;
  uploaded_by: string;
  username?: string;
  submitted_at?: string;
  topic_ids: number[];
  subtopic_ids: number[];
  tag_ids: number[];
  topic_names?: string[];
  subtopic_names?: string[];
  tag_names?: string[];
  url?: string;
}
