import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  enqueueMutation,
  getOfflineQueue,
  clearOfflineQueue,
  flushOfflineQueue,
  OFFLINE_QUEUE_STORAGE_KEY,
} from '../offlineQueue';
import { api, DEFAULT_SERVER_URL } from '../client';

describe('Offline Mutation Queue', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
    jest.clearAllMocks();
  });

  it('enqueues mutations and stores in AsyncStorage', async () => {
    await enqueueMutation({ type: 'rate', paperId: '2401.00001', rating: 1 });
    const queue = await getOfflineQueue();
    expect(queue).toHaveLength(1);
    expect(queue[0].type).toBe('rate');
    expect(queue[0].paperId).toBe('2401.00001');
    expect((queue[0] as any).rating).toBe(1);
  });

  it('coalesces rating mutations for the same paper', async () => {
    await enqueueMutation({ type: 'rate', paperId: '2401.00001', rating: 1 });
    await enqueueMutation({ type: 'rate', paperId: '2401.00001', rating: -1 });

    const queue = await getOfflineQueue();
    expect(queue).toHaveLength(1);
    expect((queue[0] as any).rating).toBe(-1);
  });

  it('preserves reading list operation order for the same paper', async () => {
    await enqueueMutation({ type: 'reading_list_add', paperId: '2401.00001' });
    await enqueueMutation({ type: 'reading_list_remove', paperId: '2401.00001' });

    const queue = await getOfflineQueue();
    expect(queue).toHaveLength(2);
    expect(queue[1].type).toBe('reading_list_remove');
  });

  it('appends multiple notes for the same paper without overwriting', async () => {
    await enqueueMutation({ type: 'add_note', paperId: '2401.00001', content: 'Note 1' });
    await enqueueMutation({ type: 'add_note', paperId: '2401.00001', content: 'Note 2' });

    const queue = await getOfflineQueue();
    expect(queue).toHaveLength(2);
  });

  it('clears the offline queue', async () => {
    await enqueueMutation({ type: 'rate', paperId: '2401.00001', rating: 1 });
    await clearOfflineQueue();
    const queue = await getOfflineQueue();
    expect(queue).toHaveLength(0);
  });

  it('flushes queued mutations successfully', async () => {
    await enqueueMutation({ type: 'rate', paperId: '2401.00001', rating: 1 });
    await enqueueMutation({ type: 'reading_list_add', paperId: '2401.00002' });
    await enqueueMutation({ type: 'add_note', paperId: '2401.00003', content: 'Critique: check methodology' });

    const mockClient = {
      ratePaper: jest.fn().mockResolvedValue({ status: 'ok' }),
      addToReadingList: jest.fn().mockResolvedValue({ status: 'ok' }),
      removeFromReadingList: jest.fn().mockResolvedValue({ status: 'ok' }),
      addPaperNote: jest.fn().mockResolvedValue({ status: 'ok' }),
    };

    const result = await flushOfflineQueue(mockClient);
    expect(result.total).toBe(3);
    expect(result.successCount).toBe(3);
    expect(result.failedCount).toBe(0);
    expect(result.remainingCount).toBe(0);

    expect(mockClient.ratePaper).toHaveBeenCalledWith('2401.00001', 1);
    expect(mockClient.addToReadingList).toHaveBeenCalledWith('2401.00002');
    expect(mockClient.addPaperNote).toHaveBeenCalledWith('2401.00003', 'Critique: check methodology', undefined, expect.any(String));

    const remaining = await getOfflineQueue();
    expect(remaining).toHaveLength(0);
  });

  it('preserves failed mutations in the queue during flush', async () => {
    await enqueueMutation({ type: 'rate', paperId: '2401.00001', rating: 1 });

    const mockClient = {
      ratePaper: jest.fn().mockRejectedValue(new Error('Network request failed')),
      addToReadingList: jest.fn().mockResolvedValue({ status: 'ok' }),
      removeFromReadingList: jest.fn().mockResolvedValue({ status: 'ok' }),
      addPaperNote: jest.fn().mockResolvedValue({ status: 'ok' }),
    };

    const result = await flushOfflineQueue(mockClient);
    expect(result.successCount).toBe(0);
    expect(result.failedCount).toBe(1);
    expect(result.remainingCount).toBe(1);

    const remaining = await getOfflineQueue();
    expect(remaining).toHaveLength(1);
  });
});

describe('AuraApiClient Offline Fallback', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
    await api.setServerUrl(DEFAULT_SERVER_URL);
    await AsyncStorage.setItem('@aura_auth_token', 'test-token');
    await AsyncStorage.setItem('@aura_auth_user', JSON.stringify({ id: 1, email: 'test@aura.test' }));
    await api.init();
    jest.clearAllMocks();
  });

  it('queues rating mutation when network request fails', async () => {
    (globalThis as any).fetch = jest.fn().mockRejectedValue(new Error('Network request failed'));

    const res = await api.ratePaper('2401.00001', 1);
    expect(res.status).toBe('queued_offline');

    const queue = await getOfflineQueue(`${DEFAULT_SERVER_URL}|1`);
    expect(queue).toHaveLength(1);
    expect(queue[0].type).toBe('rate');
    expect((queue[0] as any).rating).toBe(1);
  });

  it('queues reading list mutation when network request fails', async () => {
    (globalThis as any).fetch = jest.fn().mockRejectedValue(new Error('Network request failed'));

    const res = await api.addToReadingList('2401.00001');
    expect(res.status).toBe('queued_offline');

    const queue = await getOfflineQueue(`${DEFAULT_SERVER_URL}|1`);
    expect(queue).toHaveLength(1);
    expect(queue[0].type).toBe('reading_list_add');
  });

  it('queues note mutation when network request fails', async () => {
    (globalThis as any).fetch = jest.fn().mockRejectedValue(new Error('Network request failed'));

    const res = await api.addPaperNote('2401.00001', 'Quick idea', 'idea');
    expect(res.status).toBe('queued_offline');

    const queue = await getOfflineQueue(`${DEFAULT_SERVER_URL}|1`);
    expect(queue).toHaveLength(1);
    expect(queue[0].type).toBe('add_note');
  });
});

describe('Offline replay regression cases', () => {
  const client = () => ({
    ratePaper: jest.fn().mockResolvedValue({ status: 'ok' }),
    addToReadingList: jest.fn().mockResolvedValue({ status: 'ok' }),
    removeFromReadingList: jest.fn().mockResolvedValue({ status: 'ok' }),
    markAsRead: jest.fn().mockResolvedValue({ status: 'ok' }),
    addPaperNote: jest.fn().mockResolvedValue({ status: 'ok' }),
  });
  beforeEach(async () => { await AsyncStorage.clear(); jest.clearAllMocks(); });

  it('does not lose concurrent writes', async () => {
    await Promise.all(Array.from({ length: 20 }, (_, i) => enqueueMutation({ type: 'add_note', paperId: 'paper', content: `note ${i}` })));
    expect(await getOfflineQueue()).toHaveLength(20);
  });

  it('retains a new action added while replay is waiting on the network', async () => {
    await enqueueMutation({ type: 'rate', paperId: 'paper', rating: 1 });
    const replay = client();
    replay.ratePaper.mockImplementation(async () => {
      await enqueueMutation({ type: 'rate', paperId: 'paper', rating: 5 });
      return { status: 'ok' };
    });
    const result = await flushOfflineQueue(replay);
    expect(result.remainingCount).toBe(1);
    expect((await getOfflineQueue())[0]).toMatchObject({ rating: 5 });
  });

  it('does not acknowledge a requeued action as delivered', async () => {
    await enqueueMutation({ type: 'add_note', paperId: 'paper', content: 'Keep me' });
    const replay = client();
    replay.addPaperNote.mockResolvedValue({ status: 'queued_offline' });
    expect(await flushOfflineQueue(replay)).toMatchObject({ successCount: 0, remainingCount: 1 });
  });

  it('shares an in-flight flush and stops before dependent actions on failure', async () => {
    await enqueueMutation({ type: 'reading_list_add', paperId: 'paper' });
    await enqueueMutation({ type: 'reading_list_read', paperId: 'paper' });
    const replay = client();
    replay.addToReadingList.mockRejectedValue(new Error('offline'));
    const first = flushOfflineQueue(replay);
    const second = flushOfflineQueue(replay);
    expect(first).toBe(second);
    await first;
    expect(replay.addToReadingList).toHaveBeenCalledTimes(1);
    expect(replay.markAsRead).not.toHaveBeenCalled();
    expect(await getOfflineQueue()).toHaveLength(2);
  });

  it('isolates accounts and servers', async () => {
    await enqueueMutation({ type: 'add_note', paperId: 'paper', content: 'private' }, 'server-a|1');
    expect(await getOfflineQueue('server-a|2')).toEqual([]);
    expect(await getOfflineQueue('server-b|1')).toEqual([]);
    const replay = client();
    await flushOfflineQueue(replay, 'server-a|2');
    expect(replay.addPaperNote).not.toHaveBeenCalled();
    expect(await getOfflineQueue('server-a|1')).toHaveLength(1);
  });

  it('reports storage failure instead of claiming the work is saved', async () => {
    jest.mocked(AsyncStorage.setItem).mockRejectedValueOnce(new Error('Disk full'));
    await expect(enqueueMutation({ type: 'rate', paperId: 'paper', rating: 1 })).rejects.toThrow('Disk full');
  });
});
