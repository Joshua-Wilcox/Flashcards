export interface User {
  authenticated: boolean;
  user_id?: string;
  username?: string;
  is_admin?: boolean;
  is_whitelisted?: boolean;
}

export interface Module {
  id: number;
  name: string;
  year?: number;
}

export interface ModuleGroup {
  year: string;
  modules: Module[];
}

export interface FilterData {
  topics: string[];
  subtopics: string[];
  tags: string[];
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

export interface QuestionResponse {
  question: string;
  answers: string[];
  answer_ids: string[];
  answer_types: string[];
  answer_metadata: (number | null)[];
  module: string;
  topic: string;
  subtopic: string;
  tags: string[];
  pdfs: PDF[];
  question_id: string;
  token: string;
  is_admin: boolean;
  filters_applied: boolean;
  filters_relaxed: boolean;
  total_filtered_questions: number;
  error?: string;
}

export interface CheckAnswerResponse {
  correct: boolean;
  error?: string;
}

export interface UserStats {
  user_id: string;
  username: string;
  correct_answers: number;
  total_answers: number;
  current_streak: number;
  approved_cards: number;
  last_answer_time?: string;
}

export interface ModuleStats {
  module_id: number;
  module_name: string;
  number_answered: number;
  number_correct: number;
  current_streak: number;
  approved_cards: number;
  last_answered_time?: string;
}

export interface LeaderboardEntry {
  user_id: string;
  username: string;
  correct_answers: number;
  total_answers: number;
  current_streak: number;
  max_streak: number;
  approved_cards: number;
  last_answer_time?: string;
}

export interface ActivityEvent {
  user_id: string;
  username: string;
  module_name: string;
  streak: number;
  answered_at: string;
}

export interface LeaderboardUpdate {
  user_id: string;
  username: string;
  module_id?: number;
  correct_answers: number;
  total_answers: number;
  current_streak: number;
  max_streak: number;
  approved_cards: number;
  last_answer_time?: string;
}

export interface WebSocketMessage {
  type: 'activity' | 'leaderboard_update';
  data: ActivityEvent | LeaderboardUpdate;
}

export interface SubmittedFlashcard {
  id: number;
  user_id: string;
  username?: string;
  submitted_question: string;
  submitted_answer: string;
  module: string;
  submitted_topic?: string;
  submitted_subtopic?: string;
  submitted_tags_comma_separated?: string;
  created_at: string;
}

export interface SubmittedDistractor {
  id: number;
  user_id: string;
  username?: string;
  question_id: string;
  distractor_text: string;
  created_at: string;
  question_text?: string;
  question_source?: 'live' | 'pending';
}

export interface ReportedQuestion {
  id: number;
  user_id: string;
  username: string;
  question: string;
  question_id?: string;
  message?: string;
  distractors?: string;
  created_at: string;
}

export interface PDFAccessRequest {
  id: number;
  discord_id: string;
  username: string;
  message?: string;
  created_at: string;
}

export interface AdminSubmissions {
  flashcards: SubmittedFlashcard[];
  distractors: SubmittedDistractor[];
  reports: ReportedQuestion[];
  pdf_requests: PDFAccessRequest[];
}
