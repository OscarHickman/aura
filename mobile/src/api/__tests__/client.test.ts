import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, DEFAULT_SERVER_URL } from '../client';

describe('AuraApiClient', () => {
  const originalFetch = (globalThis as any).fetch;

  beforeEach(async () => {
    await AsyncStorage.clear();
    await api.setServerUrl(DEFAULT_SERVER_URL);
    await api.setToken(null);
    jest.clearAllMocks();
  });

  afterAll(() => {
    (globalThis as any).fetch = originalFetch;
  });

  describe('configuration & storage', () => {
    it('initialises with default server URL and null token when storage is empty', async () => {
      const state = await api.init();
      expect(state.serverUrl).toBe(DEFAULT_SERVER_URL);
      expect(state.token).toBeNull();
      expect(api.getServerUrl()).toBe(DEFAULT_SERVER_URL);
      expect(api.getToken()).toBeNull();
    });

    it('restores stored serverUrl and token from AsyncStorage', async () => {
      await AsyncStorage.setItem('@aura_server_url', 'https://example.com/aura/');
      await AsyncStorage.setItem('@aura_auth_token', 'test_token_123');

      const state = await api.init();
      expect(state.serverUrl).toBe('https://example.com/aura');
      expect(state.token).toBe('test_token_123');
      expect(api.getServerUrl()).toBe('https://example.com/aura');
      expect(api.getToken()).toBe('test_token_123');
    });

    it('cleans trailing slashes when setting server URL', async () => {
      await api.setServerUrl('https://my-server.net:5000///');
      expect(api.getServerUrl()).toBe('https://my-server.net:5000');
      expect(await AsyncStorage.getItem('@aura_server_url')).toBe('https://my-server.net:5000');
    });

    it('persists and clears token in AsyncStorage', async () => {
      await api.setToken('auth_token_abc');
      expect(api.getToken()).toBe('auth_token_abc');
      expect(await AsyncStorage.getItem('@aura_auth_token')).toBe('auth_token_abc');

      await api.setToken(null);
      expect(api.getToken()).toBeNull();
      expect(await AsyncStorage.getItem('@aura_auth_token')).toBeNull();
    });
  });

  describe('request execution and auth headers', () => {
    it('injects Bearer token header when authenticated', async () => {
      await api.setToken('secret_token');

      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ id: 1, email: 'user@test.com' }),
      } as any);

      const me = await api.getMe();
      expect(me.email).toBe('user@test.com');
      expect((globalThis as any).fetch).toHaveBeenCalledTimes(1);

      const [url, options] = ((globalThis as any).fetch as jest.Mock).mock.calls[0];
      expect(url).toBe(`${DEFAULT_SERVER_URL}/api/auth/me`);
      expect(options.headers['Authorization']).toBe('Bearer secret_token');
      expect(options.headers['Accept']).toBe('application/json');
    });

    it('does not send Authorization header when unauthenticated', async () => {
      await api.setToken(null);

      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok' }),
      } as any);

      await api.testConnection();
      const [, options] = ((globalThis as any).fetch as jest.Mock).mock.calls[0];
      expect(options?.headers?.['Authorization']).toBeUndefined();
    });

    it('extracts server JSON error message when response is not ok', async () => {
      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: 'Invalid email or password' }),
      } as any);

      await expect(api.login('bad@test.com', 'wrongpass')).rejects.toThrow('Invalid email or password');
    });

    it('falls back to status code error when server does not return JSON error', async () => {
      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new Error('Not JSON');
        },
      } as any);

      await expect(api.getMe()).rejects.toThrow('Server error (502)');
    });
  });

  describe('authentication methods', () => {
    it('login stores token and returns user details on success', async () => {
      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: 'ok',
          token: 'token_login_success',
          user: { id: 2, email: 'astro@lab.org', is_admin: false },
        }),
      } as any);

      const res = await api.login('astro@lab.org', 'hunter2');
      expect(res.token).toBe('token_login_success');
      expect(res.user.email).toBe('astro@lab.org');
      expect(api.getToken()).toBe('token_login_success');
      expect(await AsyncStorage.getItem('@aura_auth_token')).toBe('token_login_success');
    });

    it('logout sends logout request and always clears token locally', async () => {
      await api.setToken('valid_token');

      (globalThis as any).fetch = jest.fn().mockRejectedValue(new Error('Network disconnected'));

      await api.logout();
      expect(api.getToken()).toBeNull();
      expect(await AsyncStorage.getItem('@aura_auth_token')).toBeNull();
    });
  });

  describe('papers and research API methods', () => {
    it('serialises query parameters properly for getPapers', async () => {
      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ papers: [], total: 0, page: 2, per_page: 15 }),
      } as any);

      await api.getPapers({
        filter: 'liked',
        page: 2,
        per_page: 15,
        q: 'cosmology',
        tag: 'sbi',
      });

      const [url] = ((globalThis as any).fetch as jest.Mock).mock.calls[0];
      const parsed = new URL(url);
      expect(parsed.searchParams.get('filter')).toBe('liked');
      expect(parsed.searchParams.get('page')).toBe('2');
      expect(parsed.searchParams.get('per_page')).toBe('15');
      expect(parsed.searchParams.get('q')).toBe('cosmology');
      expect(parsed.searchParams.get('tag')).toBe('sbi');
    });

    it('calls ratePaper with arxiv_id and rating', async () => {
      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok', score: 0.85 }),
      } as any);

      const res = await api.ratePaper('2401.00001', 5);
      expect(res.status).toBe('ok');
      const [, options] = ((globalThis as any).fetch as jest.Mock).mock.calls[0];
      expect(JSON.parse(options.body)).toEqual({ arxiv_id: '2401.00001', rating: 5 });
    });

    it('calls reading list endpoints correctly', async () => {
      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok' }),
      } as any);

      await api.addToReadingList('2401.00001');
      await api.markAsRead('2401.00001');
      await api.removeFromReadingList('2401.00001');

      expect(((globalThis as any).fetch as jest.Mock).mock.calls.length).toBe(3);
    });

    it('calls askPaper with question context', async () => {
      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ answer: 'They used the Planck 2018 dataset.' }),
      } as any);

      const res = await api.askPaper('2401.00001', 'What dataset?');
      expect(res.answer).toBe('They used the Planck 2018 dataset.');
    });

    it('fetches notes and normalises array or object responses', async () => {
      (globalThis as any).fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          { id: 1, content: 'Crucial methodology insight', created_at: '2026-01-01' },
        ],
      } as any);

      const res = await api.getPaperNotes('2401.00001');
      expect(res.notes).toHaveLength(1);
      expect(res.notes[0].content).toBe('Crucial methodology insight');
    });

    it('handles adding and deleting notes', async () => {
      (globalThis as any).fetch = jest
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'ok', id: 42 }),
        } as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'ok' }),
        } as any);

      const addRes = await api.addPaperNote('2401.00001', 'Method idea', 'idea');
      expect(addRes.status).toBe('ok');
      expect(addRes.note_id).toBe(42);

      const delRes = await api.deletePaperNote(42);
      expect(delRes.status).toBe('ok');
    });

    it('handles collection operations', async () => {
      (globalThis as any).fetch = jest
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => [{ id: 10, name: 'Cosmology Chapter' }],
        } as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'ok' }),
        } as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'ok' }),
        } as any);

      const cols = await api.getCollections();
      expect(cols).toHaveLength(1);
      expect(cols[0].name).toBe('Cosmology Chapter');

      const addRes = await api.addPaperToCollection(10, '2401.00001');
      expect(addRes.status).toBe('ok');

      const delRes = await api.removePaperFromCollection(10, '2401.00001');
      expect(delRes.status).toBe('ok');
    });

    it('handles My Papers and citation tracking endpoints', async () => {
      (globalThis as any).fetch = jest
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            papers: [{ id: 1, title: 'My Novel Model', citation_count: 5 }],
          }),
        } as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'ok' }),
        } as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            events: [{ id: 99, my_paper_id: 1, citing_arxiv_id: '2501.00002' }],
          }),
        } as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'ok' }),
        } as any);

      const papersRes = await api.getMyPapers();
      expect(papersRes.papers).toHaveLength(1);
      expect(papersRes.papers[0].citation_count).toBe(5);

      const addRes = await api.addMyPaper({ title: 'New Thesis Paper', arxiv_id: '2501.99999' });
      expect(addRes.status).toBe('ok');

      const eventsRes = await api.getCitationEvents(5);
      expect(eventsRes.events).toHaveLength(1);

      const refreshRes = await api.refreshMyPapersCitations();
      expect(refreshRes.status).toBe('ok');
    });
  });
});
