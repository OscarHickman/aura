import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  enqueueMutation,
  getOfflineQueue,
  clearOfflineQueue,
  flushOfflineQueue,
  OFFLINE_QUEUE_STORAGE_KEY,
} from '../offlineQueue';
import { api } from '../client';

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

  it('coalesces reading list mutations for the same paper', async () => {
    await enqueueMutation({ type: 'reading_list_add', paperId: '2401.00001' });
    await enqueueMutation({ type: 'reading_list_remove', paperId: '2401.00001' });

    const queue = await getOfflineQueue();
    expect(queue).toHaveLength(1);
    expect(queue[0].type).toBe('reading_list_remove');
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
    expect(mockClient.addPaperNote).toHaveBeenCalledWith('2401.00003', 'Critique: check methodology', undefined);

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
    jest.clearAllMocks();
  });

  it('queues rating mutation when network request fails', async () => {
    (globalThis as any).fetch = jest.fn().mockRejectedValue(new Error('Network request failed'));

    const res = await api.ratePaper('2401.00001', 1);
    expect(res.status).toBe('queued_offline');

    const queue = await getOfflineQueue();
    expect(queue).toHaveLength(1);
    expect(queue[0].type).toBe('rate');
    expect((queue[0] as any).rating).toBe(1);
  });

  it('queues reading list mutation when network request fails', async () => {
    (globalThis as any).fetch = jest.fn().mockRejectedValue(new Error('Network request failed'));

    const res = await api.addToReadingList('2401.00001');
    expect(res.status).toBe('queued_offline');

    const queue = await getOfflineQueue();
    expect(queue).toHaveLength(1);
    expect(queue[0].type).toBe('reading_list_add');
  });

  it('queues note mutation when network request fails', async () => {
    (globalThis as any).fetch = jest.fn().mockRejectedValue(new Error('Network request failed'));

    const res = await api.addPaperNote('2401.00001', 'Quick idea', 'idea');
    expect(res.status).toBe('queued_offline');

    const queue = await getOfflineQueue();
    expect(queue).toHaveLength(1);
    expect(queue[0].type).toBe('add_note');
  });
});
