import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, ApiError, DEFAULT_SERVER_URL } from '../client';

describe('AuraApiClient', () => {
  const originalFetch = (globalThis as any).fetch;

  beforeEach(async () => {
    await AsyncStorage.clear();
    await api.setServerUrl(DEFAULT_SERVER_URL);
    await AsyncStorage.setItem('@aura_auth_token', 'test-token');
    await AsyncStorage.setItem('@aura_auth_user', JSON.stringify({ id: 1, email: 'test@aura.test' }));
    await api.init();
    jest.clearAllMocks();
  });

  afterAll(() => {
    (globalThis as any).fetch = originalFetch;
  });

  describe('configuration & storage', () => {
    it('initialises with default server URL and null token when storage is empty', async () => {
      await AsyncStorage.clear();
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

describe('Authenticated offline lifecycle', () => {
  const user = { id: 1, email: 'user@aura.test', is_admin: false };
  const paper = { arxiv_id: '2401.00001', title: 'Cached paper', authors: [], categories: [], abstract: 'Abstract' };
  const ok = (data: unknown) => ({ ok: true, json: async () => data });
  beforeEach(async () => {
    await AsyncStorage.clear();
    await api.setServerUrl(DEFAULT_SERVER_URL);
    await AsyncStorage.setItem('@aura_auth_token', 'token');
    await AsyncStorage.setItem('@aura_auth_user', JSON.stringify(user));
    await api.init();
  });

  it('keeps failed replayed notes without duplicating or discarding them', async () => {
    globalThis.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed'));
    await api.addPaperNote(paper.arxiv_id, 'Important idea', 'idea');
    await api.flushOfflineMutations();
    expect(await api.getOfflineQueueCount()).toBe(1);
    globalThis.fetch = jest.fn().mockResolvedValue(ok({ status: 'ok' }));
    expect(await api.flushOfflineMutations()).toMatchObject({ successCount: 1, remainingCount: 0 });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('restores cached reading and detail views offline and projects mark-read', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue(ok({ papers: [paper] }));
    await api.getReadingList();
    globalThis.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed'));
    expect(await api.getReadingList()).toMatchObject({ offline: true, papers: [paper] });
    expect(await api.getPaper(paper.arxiv_id)).toEqual(paper);
    expect(await api.markAsRead(paper.arxiv_id)).toEqual({ status: 'queued_offline' });
    expect((await api.getReadingList()).papers).toEqual([]);
    expect((await api.getReadingList('read')).papers.map(p => p.arxiv_id)).toEqual([paper.arxiv_id]);
  });

  it('shows newly saved papers and pending notes before a reading-list cache exists', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue(ok({ papers: [paper], total: 1 }));
    await api.getPapers();
    globalThis.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed'));
    await api.addToReadingList(paper.arxiv_id);
    await api.addPaperNote(paper.arxiv_id, 'Offline thought', 'idea');
    expect((await api.getReadingList()).papers.map(p => p.arxiv_id)).toEqual([paper.arxiv_id]);
    expect((await api.getPaperNotes(paper.arxiv_id)).notes[0]).toMatchObject({ pending: true, content: 'Offline thought' });
  });

  it('does not expose cached papers or replay changes to a different account', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue(ok({ papers: [paper] }));
    await api.getReadingList();
    globalThis.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed'));
    await api.ratePaper(paper.arxiv_id, 5);
    await api.logout();
    globalThis.fetch = jest.fn().mockResolvedValue(ok({ token: 'token-2', user: { ...user, id: 2 } }));
    await api.login('other@aura.test', 'password');
    expect(await api.getOfflineQueueCount()).toBe(0);
    globalThis.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed'));
    await expect(api.getReadingList()).rejects.toThrow('Network request failed');
  });

  it('clears credentials before changing servers and validates addresses', async () => {
    await expect(api.setServerUrl('ftp://example.com')).rejects.toThrow('HTTP');
    expect(api.getToken()).toBe('token');
    await api.setServerUrl('https://new-server.test/aura');
    expect(api.getToken()).toBeNull();
    expect(api.getCachedUser()).toBeNull();
  });

  it('notifies the app of a 401 but does not queue HTTP errors labelled timeout', async () => {
    const listener = jest.fn();
    const unsubscribe = api.onUnauthorized(listener);
    globalThis.fetch = jest.fn().mockResolvedValue({ ok: false, status: 400, json: async () => ({ error: 'timeout invalid' }) });
    await expect(api.ratePaper(paper.arxiv_id, 99)).rejects.toBeInstanceOf(ApiError);
    expect(await api.getOfflineQueueCount()).toBe(0);
    globalThis.fetch = jest.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ error: 'Expired' }) });
    await expect(api.getMe()).rejects.toMatchObject({ status: 401 });
    expect(api.getToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it('uses a persistent installation-specific device name when logging in', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue(ok({ token: 'new-token', user }));
    await api.login(user.email, 'password');
    await api.login(user.email, 'password');
    const calls = jest.mocked(globalThis.fetch).mock.calls;
    const name = JSON.parse(calls[0][1]?.body as string).token_name;
    expect(name).toMatch(/^AURA Phone .+/);
    expect(JSON.parse(calls[1][1]?.body as string).token_name).toBe(name);
  });

  it('aborts hung requests and clears connection timers on rejection', async () => {
    jest.useFakeTimers();
    globalThis.fetch = jest.fn((_url: RequestInfo | URL, options?: RequestInit) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
    }));
    const pending = expect(api.getMe()).rejects.toThrow('aborted');
    await jest.advanceTimersByTimeAsync(15000);
    await pending;
    expect(api.getToken()).toBe('token');
    globalThis.fetch = jest.fn().mockRejectedValue(new Error('Network request failed'));
    await api.testConnection();
    expect(jest.getTimerCount()).toBe(0);
    jest.useRealTimers();
  });

  describe('new research intelligence & parity methods', () => {
    it('creates a collection via POST /api/collections', async () => {
      globalThis.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ id: 42, name: 'Cosmology Top Picks' }),
      });
      const res = await api.createCollection('Cosmology Top Picks', 'Key papers');
      expect(res).toEqual({ id: 42, name: 'Cosmology Top Picks' });
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${DEFAULT_SERVER_URL}/api/collections`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'Cosmology Top Picks', description: 'Key papers' }),
        })
      );
    });

    it('fetches deep summary via GET /api/papers/:id/deep-summary', async () => {
      globalThis.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ arxiv_id: '2401.12345', mode: 'grad_student', summary: 'Deep dive summary.' }),
      });
      const res = await api.getDeepSummary('2401.12345', 'grad_student');
      expect(res.summary).toBe('Deep dive summary.');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${DEFAULT_SERVER_URL}/api/papers/2401.12345/deep-summary?mode=grad_student`,
        expect.anything()
      );
    });

    it('fetches BibTeX citation via GET /api/papers/:id/bibtex', async () => {
      globalThis.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ arxiv_id: '2401.12345', bibtex: '@article{2401.12345,\n  title={Aura}\n}' }),
      });
      const res = await api.getPaperBibtex('2401.12345');
      expect(res.bibtex).toContain('@article{2401.12345');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${DEFAULT_SERVER_URL}/api/papers/2401.12345/bibtex`,
        expect.anything()
      );
    });

    it('fetches weekly briefs list and single brief', async () => {
      globalThis.fetch = jest.fn().mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ briefs: [{ date: '2026-10-18', content: '# Brief' }] }),
      }).mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ brief: { date: '2026-10-18', content: '# Brief Detail' } }),
      });

      const listRes = await api.getBriefs();
      expect(listRes.briefs).toHaveLength(1);
      const singleRes = await api.getBrief('2026-10-18');
      expect(singleRes.brief.content).toBe('# Brief Detail');
    });

    it('fetches trends and velocity alerts via GET /api/trends', async () => {
      globalThis.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          trends: { topics: [] },
          alerts: [{ id: 1, tag: 'dark energy', spike_factor: 3.2 }],
          upcoming_events: [],
        }),
      });
      const res = await api.getTrends();
      expect(res.alerts).toHaveLength(1);
      expect(res.alerts?.[0].spike_factor).toBe(3.2);
    });

    it('fetches user clusters via GET /api/user/clusters', async () => {
      globalThis.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          clusters: [{ id: 0, label: 'SBI & Field-Level Inference', size: 12, top_terms: ['sbi', 'posterior'] }],
        }),
      });
      const res = await api.getUserClusters();
      expect(res.clusters).toHaveLength(1);
      expect(res.clusters[0].label).toBe('SBI & Field-Level Inference');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${DEFAULT_SERVER_URL}/api/user/clusters`,
        expect.anything()
      );
    });

    it('handles daily audio briefing operations', async () => {
      globalThis.fetch = jest.fn()
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ ok: true, audio_url: '/api/audio/stream/briefing.mp3', duration_seconds: 180 }),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ ok: true, audio_url: '/api/audio/stream/briefing.mp3' }),
        });

      const getRes = await api.getDailyAudioBriefing();
      expect(getRes.ok).toBe(true);
      expect(getRes.audio_url).toBe('/api/audio/stream/briefing.mp3');

      const forceRes = await api.getDailyAudioBriefing(true);
      expect(forceRes.ok).toBe(true);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${DEFAULT_SERVER_URL}/api/audio/daily?force=true`,
        expect.anything()
      );
    });

    it('handles Zotero status and sync', async () => {
      globalThis.fetch = jest.fn()
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ configured: true, valid: true, user_id: '12345' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ ok: true, synced_count: 1 }),
        });

      const statusRes = await api.getZoteroStatus();
      expect(statusRes.configured).toBe(true);

      const syncRes = await api.syncZotero('2401.00001');
      expect(syncRes.ok).toBe(true);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${DEFAULT_SERVER_URL}/api/zotero/sync`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ arxiv_id: '2401.00001' }),
        })
      );
    });

    it('handles multi-paper comparative synthesis', async () => {
      globalThis.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          matrix: [],
          synthesis_markdown: '# Synthesis',
        }),
      });

      const res = await api.comparePapers(['2401.00001', '2401.00002']);
      expect(res.ok).toBe(true);
      expect(res.synthesis_markdown).toBe('# Synthesis');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        `${DEFAULT_SERVER_URL}/api/papers/compare`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ arxiv_ids: ['2401.00001', '2401.00002'] }),
        })
      );
    });
  });
});
