import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  CitationEvent,
  Collection,
  DeepSummaryResponse,
  DevicePushToken,
  MyPaper,
  Note,
  Paper,
  PapersResponse,
  ResearchBrief,
  TrendsData,
  User,
} from '../types';
import {
  enqueueMutation,
  flushOfflineQueue,
  FlushResult,
  getOfflineQueue,
  NewQueuedMutation,
} from './offlineQueue';

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

export function isNetworkError(error: any): boolean {
  if (error instanceof ApiError) return false;
  if (!error) return false;
  const msg = (error.message || '').toLowerCase();
  return (
    msg.includes('network') ||
    msg.includes('aborted') ||
    msg.includes('failed to fetch') ||
    msg.includes('networkerror') ||
    msg.includes('timeout')
  );
}

const STORAGE_KEYS = {
  SERVER_URL: '@aura_server_url',
  AUTH_TOKEN: '@aura_auth_token',
  USER: '@aura_auth_user',
  DEVICE_ID: '@aura_device_id',
};

// Default to user's Tailscale host or local fallback
export const DEFAULT_SERVER_URL = 'http://100.88.127.35/aura';

class AuraApiClient {
  private serverUrl: string = DEFAULT_SERVER_URL;
  private token: string | null = null;
  private user: User | null = null;
  private authListeners = new Set<() => void>();

  onUnauthorized(listener: () => void): () => void {
    this.authListeners.add(listener);
    return () => { this.authListeners.delete(listener); };
  }

  getCachedUser(): User | null { return this.user; }

  private getScope(): string {
    if (!this.token || !this.user) throw new Error('Sign in to save changes on this device.');
    return `${this.serverUrl}|${this.user.id}`;
  }

  private async saveUser(user: User): Promise<void> {
    this.user = user;
    await AsyncStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(user));
  }

  private cacheKey(scope: string, key: string): string {
    return `@aura_cache:${encodeURIComponent(scope)}:${key}`;
  }

  private async cache<T>(scope: string, key: string, value: T): Promise<void> {
    try { await AsyncStorage.setItem(this.cacheKey(scope, key), JSON.stringify(value)); }
    catch { /* Online reads can succeed even when the cache is full. */ }
  }

  private async readCache<T>(scope: string, key: string): Promise<T | null> {
    const raw = await AsyncStorage.getItem(this.cacheKey(scope, key));
    return raw ? JSON.parse(raw) : null;
  }

  private async mutate(mutation: NewQueuedMutation, endpoint: string, options: RequestInit): Promise<any> {
    const scope = this.getScope();
    // Keep new actions behind older unsent actions, even after reconnecting.
    if ((await getOfflineQueue(scope)).length) {
      await enqueueMutation(mutation, scope);
      return { status: 'queued_offline' };
    }
    if (this.getScope() !== scope) throw new Error('Account changed before saving');
    try { return await this.request(endpoint, options); }
    catch (error) {
      if (!isNetworkError(error)) throw error;
      await enqueueMutation(mutation, scope);
      return { status: 'queued_offline' };
    }
  }

  async init(): Promise<{ serverUrl: string; token: string | null }> {
    try {
      const [storedUrl, storedToken, storedUser] = await Promise.all([
        AsyncStorage.getItem(STORAGE_KEYS.SERVER_URL),
        AsyncStorage.getItem(STORAGE_KEYS.AUTH_TOKEN),
        AsyncStorage.getItem(STORAGE_KEYS.USER),
      ]);
      this.serverUrl = (storedUrl || DEFAULT_SERVER_URL).replace(/\/+$/, '');
      this.token = storedToken;
      this.user = storedToken && storedUser ? JSON.parse(storedUser) : null;
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
    const parsed = new URL(cleanUrl);
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash) {
      throw new Error('Enter an HTTP or HTTPS server address without credentials, a query or a fragment.');
    }
    if (cleanUrl !== this.serverUrl) await this.setToken(null);
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
      this.user = null;
      await AsyncStorage.multiRemove([STORAGE_KEYS.AUTH_TOKEN, STORAGE_KEYS.USER]);
    }
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const requestToken = this.token;
    const requestServer = this.serverUrl;
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
        if (response.status === 401 && endpoint !== '/api/auth/login' && requestToken === this.token && requestServer === this.serverUrl) {
          await this.setToken(null);
          this.authListeners.forEach(listener => listener());
        }
        throw new ApiError(errorMsg, response.status);
      }

      return await response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  async testConnection(customUrl?: string): Promise<{ ok: boolean; status?: string; error?: string }> {
    const targetUrl = customUrl ? customUrl.trim().replace(/\/+$/, '') : this.serverUrl;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 6000);
    try {
      const res = await fetch(`${targetUrl}/health`, { signal: controller.signal });
      if (res.ok) {
        return { ok: true, status: 'Connected successfully' };
      }
      return { ok: false, error: `HTTP ${res.status}` };
    } catch (e: any) {
      return { ok: false, error: e.message || 'Connection failed' };
    } finally {
      clearTimeout(timeout);
    }
  }

  async login(email: string, password: string): Promise<{ token: string; user: User }> {
    let deviceId = await AsyncStorage.getItem(STORAGE_KEYS.DEVICE_ID);
    if (!deviceId) {
      deviceId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
      await AsyncStorage.setItem(STORAGE_KEYS.DEVICE_ID, deviceId);
    }
    const data = await this.request<{ status: string; token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, token_name: `AURA Phone ${deviceId}` }),
    });
    await this.setToken(data.token);
    await this.saveUser(data.user);
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
    const token = this.token;
    const server = this.serverUrl;
    const user = await this.request<User>('/api/auth/me');
    if (token !== this.token || server !== this.serverUrl) throw new Error('Account changed');
    await this.saveUser(user);
    return user;
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
    const scope = this.user && this.token ? this.getScope() : null;
    let response: PapersResponse;
    try {
      response = await this.request<PapersResponse>(endpoint);
      if (scope) {
        await this.cache(scope, `feed:${endpoint}`, response);
        await Promise.all(response.papers.map(paper => this.cache(scope, `paper:${paper.arxiv_id}`, paper)));
      }
    } catch (error) {
      if (scope && isNetworkError(error)) {
        const cached = await this.readCache<PapersResponse>(scope, `feed:${endpoint}`);
        if (cached) {
          response = cached;
        } else {
          throw error;
        }
      } else {
        throw error;
      }
    }

    if (scope) {
      const queue = await getOfflineQueue(scope);
      if (queue.length > 0) {
        const ratingMap = new Map<string, number>();
        const readingMap = new Map<string, boolean>();
        for (const item of queue) {
          if (item.type === 'rate') ratingMap.set(item.paperId, item.rating);
          else if (item.type === 'reading_list_add') readingMap.set(item.paperId, true);
          else if (item.type === 'reading_list_remove') readingMap.set(item.paperId, false);
        }
        response = {
          ...response,
          papers: response.papers.map(p => ({
            ...p,
            rating: ratingMap.has(p.arxiv_id) ? ratingMap.get(p.arxiv_id) : p.rating,
            in_reading_list: readingMap.has(p.arxiv_id) ? Boolean(readingMap.get(p.arxiv_id)) : p.in_reading_list,
          })),
        };
      }
    }

    return response;
  }

  async getPaper(arxivId: string): Promise<Paper> {
    const scope = this.getScope();
    let paper: Paper | null = null;
    try {
      paper = await this.request<Paper>(`/api/papers/${arxivId}`);
      await this.cache(scope, `paper:${arxivId}`, paper);
    } catch (error) {
      if (isNetworkError(error)) {
        paper = await this.readCache<Paper>(scope, `paper:${arxivId}`);
        if (!paper) throw error;
      } else {
        throw error;
      }
    }

    if (paper && scope) {
      const queue = await getOfflineQueue(scope);
      for (const item of queue) {
        if (item.paperId === arxivId) {
          if (item.type === 'rate') paper = { ...paper, rating: item.rating };
          else if (item.type === 'reading_list_add') paper = { ...paper, in_reading_list: true };
          else if (item.type === 'reading_list_remove') paper = { ...paper, in_reading_list: false };
        }
      }
    }

    return paper;
  }

  async ratePaper(arxivId: string, rating: number): Promise<{ status: string; score?: number }> {
    return this.mutate({ type: 'rate', paperId: arxivId, rating }, '/api/rate', {
      method: 'POST', body: JSON.stringify({ arxiv_id: arxivId, rating }),
    });
  }

  async addToReadingList(arxivId: string): Promise<{ status: string }> {
    return this.mutate({ type: 'reading_list_add', paperId: arxivId }, '/api/reading-list', {
      method: 'POST', body: JSON.stringify({ arxiv_id: arxivId }),
    });
  }

  async removeFromReadingList(arxivId: string): Promise<{ status: string }> {
    return this.mutate({ type: 'reading_list_remove', paperId: arxivId }, `/api/reading-list/${arxivId}`, { method: 'DELETE' });
  }

  async markAsRead(arxivId: string): Promise<{ status: string }> {
    return this.mutate({ type: 'reading_list_read', paperId: arxivId }, `/api/reading-list/${arxivId}/read`, { method: 'PUT' });
  }

  async getReadingList(filter: 'unread' | 'read' = 'unread'): Promise<{ papers: Paper[]; offline?: boolean }> {
    const scope = this.getScope();
    let result: { papers: Paper[]; offline?: boolean };
    try {
      result = await this.request<{ papers: Paper[] }>(`/api/reading-list?filter=${filter}`);
      await this.cache(scope, `reading:${filter}`, result);
      await Promise.all(result.papers.map(paper => this.cache(scope, `paper:${paper.arxiv_id}`, paper)));
    } catch (error) {
      if (!isNetworkError(error)) throw error;
      const cached = await this.readCache<{ papers: Paper[] }>(scope, `reading:${filter}`);
      const other = await this.readCache<{ papers: Paper[] }>(scope, `reading:${filter === 'read' ? 'unread' : 'read'}`);
      const pending = await getOfflineQueue(scope);
      if (!cached && !other && !pending.some(item => item.type === 'reading_list_add')) throw error;
      result = { papers: cached?.papers || [], offline: true };
    }
    const papers = new Map(result.papers.map(paper => [paper.arxiv_id, paper]));
    for (const item of await getOfflineQueue(scope)) {
      if (item.type === 'reading_list_remove' || (item.type === 'reading_list_read' && filter === 'unread')) {
        papers.delete(item.paperId);
      } else if ((item.type === 'reading_list_add' && filter === 'unread') || (item.type === 'reading_list_read' && filter === 'read')) {
        const paper = await this.readCache<Paper>(scope, `paper:${item.paperId}`);
        if (paper) papers.set(item.paperId, { ...paper, in_reading_list: true });
      }
    }
    return { ...result, papers: [...papers.values()] };
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
    const scope = this.getScope();
    let notes: Note[];
    try {
      const response = await this.request<Note[] | { notes: Note[] }>(`/api/papers/${arxivId}/notes`);
      notes = Array.isArray(response) ? response : response.notes || [];
      await this.cache(scope, `notes:${arxivId}`, notes);
    } catch (error) {
      if (!isNetworkError(error)) throw error;
      notes = await this.readCache<Note[]>(scope, `notes:${arxivId}`) || [];
    }
    const queue = await getOfflineQueue(scope);
    queue.forEach((item, index) => {
      if (item.type === 'add_note' && item.paperId === arxivId && !notes.some(note => note.client_mutation_id === item.id)) {
        notes.push({ id: -(index + 1), content: item.content, note_type: item.noteType,
          created_at: new Date(item.timestamp).toISOString(), pending: true, client_mutation_id: item.id });
      }
    });
    return { notes };
  }

  async addPaperNote(
    arxivId: string,
    content: string,
    noteType?: string
  ): Promise<{ status: string; note_id?: number; id?: number }> {
    const mutationId = `note_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const result = await this.mutate(
      { id: mutationId, type: 'add_note', paperId: arxivId, content, noteType },
      `/api/papers/${arxivId}/notes`,
      { method: 'POST', body: JSON.stringify({ content, note_type: noteType, client_mutation_id: mutationId }) },
    );
    return { ...result, note_id: result.note_id ?? result.id };
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

  async createCollection(name: string, description?: string): Promise<{ id: number; name: string }> {
    return await this.request<{ id: number; name: string }>('/api/collections', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    });
  }

  async getDeepSummary(
    arxivId: string,
    mode: 'grad_student' | 'expert' = 'grad_student'
  ): Promise<DeepSummaryResponse> {
    return await this.request<DeepSummaryResponse>(
      `/api/papers/${encodeURIComponent(arxivId)}/deep-summary?mode=${mode}`
    );
  }

  async getPaperBibtex(arxivId: string): Promise<{ arxiv_id: string; bibtex: string }> {
    return await this.request<{ arxiv_id: string; bibtex: string }>(
      `/api/papers/${encodeURIComponent(arxivId)}/bibtex`
    );
  }

  async getBriefs(): Promise<{ briefs: ResearchBrief[] }> {
    return await this.request<{ briefs: ResearchBrief[] }>('/api/briefs');
  }

  async getBrief(date: string): Promise<{ brief: ResearchBrief }> {
    return await this.request<{ brief: ResearchBrief }>(`/api/briefs/${encodeURIComponent(date)}`);
  }

  async getTrends(): Promise<TrendsData> {
    return await this.request<TrendsData>('/api/trends');
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

  // Device push notification methods
  async registerDeviceToken(
    deviceToken: string,
    platform: string = 'android',
    deviceName?: string
  ): Promise<{ status: string; device: DevicePushToken }> {
    return await this.request<{ status: string; device: DevicePushToken }>('/api/devices', {
      method: 'POST',
      body: JSON.stringify({
        device_token: deviceToken,
        platform,
        device_name: deviceName,
      }),
    });
  }

  async unregisterDeviceToken(
    deviceToken: string
  ): Promise<{ status: string; unregistered: boolean }> {
    return await this.request<{ status: string; unregistered: boolean }>('/api/devices', {
      method: 'DELETE',
      body: JSON.stringify({ device_token: deviceToken }),
    });
  }

  async getDevices(): Promise<{ status: string; devices: DevicePushToken[] }> {
    return await this.request<{ status: string; devices: DevicePushToken[] }>('/api/devices');
  }

  async testDeviceNotification(
    title?: string,
    body?: string
  ): Promise<{ status: string; result: any }> {
    return await this.request<{ status: string; result: any }>('/api/devices/test', {
      method: 'POST',
      body: JSON.stringify({ title, body }),
    });
  }

  // Offline queue utilities
  async flushOfflineMutations(): Promise<FlushResult> {
    const scope = this.getScope();
    const token = this.token;
    const replay = (endpoint: string, options: RequestInit) => {
      if (this.token !== token || this.getScope() !== scope) throw new Error('Account changed during sync');
      return this.request(endpoint, options);
    };
    // Use raw requests: public mutation methods would queue a failed replay again.
    return flushOfflineQueue({
      ratePaper: (id, rating) => replay('/api/rate', { method: 'POST', body: JSON.stringify({ arxiv_id: id, rating }) }),
      addToReadingList: id => replay('/api/reading-list', { method: 'POST', body: JSON.stringify({ arxiv_id: id }) }),
      removeFromReadingList: id => replay(`/api/reading-list/${id}`, { method: 'DELETE' }),
      markAsRead: id => replay(`/api/reading-list/${id}/read`, { method: 'PUT' }),
      addPaperNote: (id, content, noteType, mutationId) => replay(`/api/papers/${id}/notes`, { method: 'POST', body: JSON.stringify({ content, note_type: noteType, client_mutation_id: mutationId }) }),
    }, scope);
  }

  async getOfflineQueueCount(): Promise<number> {
    if (!this.token || !this.user) return 0;
    const queue = await getOfflineQueue(this.getScope());
    return queue.length;
  }
}

export const api = new AuraApiClient();
