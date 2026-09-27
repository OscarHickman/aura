export interface Paper {
  arxiv_id: string;
  title: string;
  abstract: string;
  authors: string[];
  categories: string[];
  score?: number;
  model_score?: number;
  freshness_bonus?: number;
  summary_bonus?: number;
  url?: string;
  pdf_url?: string;
  summary?: string;
  deep_summary?: string;
  published?: string;
  updated?: string;
  comments?: string;
  rating?: number | null;
  tags?: string[];
  collections?: { id: number; name: string }[];
  notes?: Note[];
  in_reading_list?: boolean;
  from_followed_author?: boolean;
  from_collaborator?: boolean;
  cites_user_work?: boolean;
  citation_count?: number;
  similar_papers?: Paper[];
}

export interface Note {
  id: number;
  content: string;
  created_at: string;
  updated_at?: string;
}

export interface User {
  id: number;
  email: string;
  is_admin: boolean;
}

export interface AuthState {
  serverUrl: string;
  token: string | null;
  user: User | null;
  isLoading: boolean;
  error: string | null;
}

export interface PapersResponse {
  papers: Paper[];
  page: number;
  per_page: number;
  total: number;
  filter: string;
}
