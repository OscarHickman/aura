import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  CitationEvent,
  Collection,
  MyPaper,
  Note,
  Paper,
  PapersResponse,
  User,
} from '../types';
import {
  enqueueMutation,
  flushOfflineQueue,
  FlushResult,
  getOfflineQueue,
} from './offlineQueue';

function isNetworkError(error: any): boolean {
  if (!error) return false;
  const msg = (error.message || '').toLowerCase();
  return (
    msg.includes('network request failed') ||
    msg.includes('aborted') ||
    msg.includes('failed to fetch') ||
    msg.includes('networkerror') ||
    msg.includes('timeout')
  );
}

const STORAGE_KEYS = {
  SERVER_URL: '@aura_server_url',
  AUTH_TOKEN: '@aura_auth_token',
  SAVED_PAPERS: '@aura_cached_papers',
};

// Default to user's Tailscale host or local fallback
export const DEFAULT_SERVER_URL = 'http://100.88.127.35/aura';

class AuraApiClient {
  private serverUrl: string = DEFAULT_SERVER_URL;
  private token: string | null = null;

  async init(): Promise<{ serverUrl: string; token: string | null }> {
    try {
      const [storedUrl, storedToken] = await Promise.all([
        AsyncStorage.getItem(STORAGE_KEYS.SERVER_URL),
        AsyncStorage.getItem(STORAGE_KEYS.AUTH_TOKEN),
      ]);
      if (storedUrl) this.serverUrl = storedUrl.replace(/\/+$/, '');
      if (storedToken) this.token = storedToken;
    } catch (e) {
      console.warn('Failed to restore auth from storage:', e);
    }
    return { serverUrl: this.serverUrl, token: this.token };
  }

  getServerUrl(): string {
    return this.serverUrl;
  }

  async setServerUrl(url: string): Promise<void> {
    const cleanUrl = url.trim().replace(/\/+$/, '');
    this.serverUrl = cleanUrl;
    await AsyncStorage.setItem(STORAGE_KEYS.SERVER_URL, cleanUrl);
  }

  getToken(): string | null {
    return this.token;
  }

  async setToken(token: string | null): Promise<void> {
    this.token = token;
    if (token) {
      await AsyncStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, token);
    } else {
      await AsyncStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
    }
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.serverUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
    const headers: Record<string, string> = {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });

      if (!response.ok) {
        let errorMsg = `Server error (${response.status})`;
        try {
          const errData = await response.json();
          errorMsg = errData.error || errorMsg;
        } catch {
          // ignore non-json error responses
        }
        throw new Error(errorMsg);
      }

      return await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  async testConnection(customUrl?: string): Promise<{ ok: boolean; status?: string; error?: string }> {
    const targetUrl = customUrl ? customUrl.trim().replace(/\/+$/, '') : this.serverUrl;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 6000);
      const res = await fetch(`${targetUrl}/health`, { signal: controller.signal });
      clearTimeout(timeout);
      if (res.ok) {
        return { ok: true, status: 'Connected successfully' };
      }
      return { ok: false, error: `HTTP ${res.status}` };
    } catch (e: any) {
      return { ok: false, error: e.message || 'Connection failed' };
    }
  }

  async login(email: string, password: string): Promise<{ token: string; user: User }> {
    const data = await this.request<{ status: string; token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, token_name: 'AURA Android Phone' }),
    });
    await this.setToken(data.token);
    return { token: data.token, user: data.user };
  }

  async logout(): Promise<void> {
    if (this.token) {
      try {
        await this.request('/api/auth/logout', { method: 'POST' });
      } catch {
        // Server unreachable or token already revoked: still clear it locally.
      }
    }
    await this.setToken(null);
  }

  async getMe(): Promise<User> {
    return await this.request<User>('/api/auth/me');
  }

  async getPapers(params: {
    filter?: string;
    page?: number;
    per_page?: number;
    q?: string;
    tag?: string;
  } = {}): Promise<PapersResponse> {
    const query = new URLSearchParams();
    if (params.filter) query.set('filter', params.filter);
    if (params.page) query.set('page', String(params.page));
    if (params.per_page) query.set('per_page', String(params.per_page));
    if (params.q) query.set('q', params.q);
    if (params.tag) query.set('tag', params.tag);

    const queryString = query.toString();
    const endpoint = `/api/papers${queryString ? `?${queryString}` : ''}`;
    return await this.request<PapersResponse>(endpoint);
  }

  async getPaper(arxivId: string): Promise<Paper> {
    return await this.request<Paper>(`/api/papers/${arxivId}`);
  }

  async ratePaper(arxivId: string, rating: number): Promise<{ status: string; score?: number }> {
    try {
      return await this.request<{ status: string; score?: number }>('/api/rate', {
        method: 'POST',
        body: JSON.stringify({ arxiv_id: arxivId, rating }),
      });
    } catch (e: any) {
      if (isNetworkError(e)) {
        await enqueueMutation({ type: 'rate', paperId: arxivId, rating });
        return { status: 'queued_offline', score: rating };
      }
      throw e;
    }
  }

  async addToReadingList(arxivId: string): Promise<{ status: string }> {
    try {
      return await this.request<{ status: string }>('/api/reading-list', {
        method: 'POST',
        body: JSON.stringify({ arxiv_id: arxivId }),
      });
    } catch (e: any) {
      if (isNetworkError(e)) {
        await enqueueMutation({ type: 'reading_list_add', paperId: arxivId });
        return { status: 'queued_offline' };
      }
      throw e;
    }
  }

  async removeFromReadingList(arxivId: string): Promise<{ status: string }> {
    try {
      return await this.request<{ status: string }>(`/api/reading-list/${arxivId}`, {
        method: 'DELETE',
      });
    } catch (e: any) {
      if (isNetworkError(e)) {
        await enqueueMutation({ type: 'reading_list_remove', paperId: arxivId });
        return { status: 'queued_offline' };
      }
      throw e;
    }
  }

  async markAsRead(arxivId: string): Promise<{ status: string }> {
    return await this.request<{ status: string }>(`/api/reading-list/${arxivId}/read`, {
      method: 'PUT',
    });
  }

  async getReadingList(filter: 'unread' | 'read' = 'unread'): Promise<{ papers: Paper[] }> {
    return await this.request<{ papers: Paper[] }>(`/api/reading-list?filter=${filter}`);
  }

  async askPaper(arxivId: string, question: string): Promise<{ answer: string }> {
    return await this.request<{ answer: string }>(`/api/papers/${arxivId}/ask`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    });
  }

  async summarizePaper(arxivId: string): Promise<{ status: string; summary?: string }> {
    return await this.request<{ status: string; summary?: string }>('/api/summarize-paper', {
      method: 'POST',
      body: JSON.stringify({ arxiv_id: arxivId }),
    });
  }

  // Notes API
  async getPaperNotes(arxivId: string): Promise<{ notes: Note[] }> {
    const res = await this.request<any>(`/api/papers/${arxivId}/notes`);
    if (Array.isArray(res)) {
      return { notes: res };
    }
    return { notes: res?.notes || [] };
  }

  async addPaperNote(
    arxivId: string,
    content: string,
    noteType?: string
  ): Promise<{ status: string; note_id?: number; id?: number }> {
    try {
      const res = await this.request<{ status: string; note_id?: number; id?: number }>(
        `/api/papers/${arxivId}/notes`,
        {
          method: 'POST',
          body: JSON.stringify({ content, note_type: noteType }),
        }
      );
      return {
        ...res,
        note_id: res.note_id ?? res.id,
      };
    } catch (e: any) {
      if (isNetworkError(e)) {
        await enqueueMutation({ type: 'add_note', paperId: arxivId, content, noteType });
        return { status: 'queued_offline' };
      }
      throw e;
    }
  }

  async deletePaperNote(noteId: number): Promise<{ status: string }> {
    return await this.request<{ status: string }>(`/api/notes/${noteId}`, {
      method: 'DELETE',
    });
  }

  // Collections API
  async getCollections(): Promise<Collection[]> {
    return await this.request<Collection[]>('/api/collections');
  }

  async addPaperToCollection(collectionId: number, arxivId: string): Promise<{ status: string }> {
    return await this.request<{ status: string }>(`/api/collections/${collectionId}/papers`, {
      method: 'POST',
      body: JSON.stringify({ arxiv_id: arxivId }),
    });
  }

  async removePaperFromCollection(
    collectionId: number,
    arxivId: string
  ): Promise<{ status: string }> {
    return await this.request<{ status: string }>(
      `/api/collections/${collectionId}/papers/${arxivId}`,
      {
        method: 'DELETE',
      }
    );
  }

  // My Papers API
  async getMyPapers(): Promise<{ papers: MyPaper[] }> {
    return await this.request<{ papers: MyPaper[] }>('/api/my-papers');
  }

  async addMyPaper(paper: {
    title: string;
    arxiv_id?: string;
    doi?: string;
  }): Promise<{ status: string; message?: string }> {
    return await this.request<{ status: string; message?: string }>('/api/my-papers', {
      method: 'POST',
      body: JSON.stringify(paper),
    });
  }

  async deleteMyPaper(paperId: number): Promise<{ status: string }> {
    return await this.request<{ status: string }>(`/api/my-papers/${paperId}`, {
      method: 'DELETE',
    });
  }

  async getCitationHistory(
    paperId: number
  ): Promise<{ paper_id: number; history: { recorded_at: string; citation_count: number }[] }> {
    return await this.request<{
      paper_id: number;
      history: { recorded_at: string; citation_count: number }[];
    }>(`/api/my-papers/${paperId}/citation-history`);
  }

  async getCitationEvents(limit: number = 20): Promise<{ events: CitationEvent[] }> {
    return await this.request<{ events: CitationEvent[] }>(
      `/api/my-papers/citation-events?limit=${limit}`
    );
  }

  async refreshMyPapersCitations(): Promise<{ status: string }> {
    return await this.request<{ status: string }>('/api/my-papers/refresh-citations', {
      method: 'POST',
    });
  }

  // Offline queue utilities
  async flushOfflineMutations(): Promise<FlushResult> {
    return await flushOfflineQueue(this);
  }

  async getOfflineQueueCount(): Promise<number> {
    const queue = await getOfflineQueue();
    return queue.length;
  }
}

export const api = new AuraApiClient();
