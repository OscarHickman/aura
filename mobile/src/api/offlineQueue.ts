import AsyncStorage from '@react-native-async-storage/async-storage';

export const OFFLINE_QUEUE_STORAGE_KEY = '@aura_offline_mutations';

type MutationData =
  | { type: 'rate'; paperId: string; rating: number }
  | { type: 'reading_list_add' | 'reading_list_remove' | 'reading_list_read'; paperId: string }
  | { type: 'add_note'; paperId: string; content: string; noteType?: string };
export type QueuedMutation = MutationData & { id: string; timestamp: number };
export type NewQueuedMutation = MutationData & { id?: string; timestamp?: number };

const storageKey = (scope: string) => scope
  ? `${OFFLINE_QUEUE_STORAGE_KEY}:${encodeURIComponent(scope)}`
  : OFFLINE_QUEUE_STORAGE_KEY;

// Serialise read/modify/write operations; network calls never hold this lock.
const writes = new Map<string, Promise<unknown>>();
function serialise<T>(scope: string, operation: () => Promise<T>): Promise<T> {
  const previous = writes.get(scope) || Promise.resolve();
  const next = previous.catch(() => undefined).then(operation);
  writes.set(scope, next);
  void next.finally(() => {
    if (writes.get(scope) === next) writes.delete(scope);
  }).catch(() => undefined);
  return next;
}

async function readQueue(scope: string): Promise<QueuedMutation[]> {
  const raw = await AsyncStorage.getItem(storageKey(scope));
  if (!raw) return [];
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed)) throw new Error('Offline changes could not be read.');
  return parsed;
}

export function getOfflineQueue(scope = ''): Promise<QueuedMutation[]> {
  return serialise(scope, () => readQueue(scope));
}

export function clearOfflineQueue(scope = ''): Promise<void> {
  return serialise(scope, () => AsyncStorage.removeItem(storageKey(scope)));
}

export function enqueueMutation(mutation: NewQueuedMutation, scope = ''): Promise<QueuedMutation> {
  return serialise(scope, async () => {
    const item = {
      ...mutation,
      id: mutation.id || `${mutation.type}_${Date.now()}_${Math.random().toString(36).slice(2)}`,
      timestamp: mutation.timestamp ?? Date.now(),
    } as QueuedMutation;
    const queue = await readQueue(scope);
    // Coalesce only adjacent ratings. Reading-list operations are order dependent
    // (add → read → remove), so retain their order even for the same paper.
    const last = queue[queue.length - 1];
    if (item.type === 'rate' && last?.type === 'rate' && last.paperId === item.paperId) {
      queue.pop();
    }
    queue.push(item);
    await AsyncStorage.setItem(storageKey(scope), JSON.stringify(queue));
    return item;
  });
}

export function removeMutationById(id: string, scope = ''): Promise<void> {
  return serialise(scope, async () => {
    const queue = await readQueue(scope);
    await AsyncStorage.setItem(storageKey(scope), JSON.stringify(queue.filter(item => item.id !== id)));
  });
}

export interface FlushResult {
  total: number;
  successCount: number;
  failedCount: number;
  remainingCount: number;
}
interface ReplayClient {
  ratePaper: (paperId: string, rating: number) => Promise<unknown>;
  addToReadingList: (paperId: string) => Promise<unknown>;
  removeFromReadingList: (paperId: string) => Promise<unknown>;
  markAsRead?: (paperId: string) => Promise<unknown>;
  addPaperNote: (paperId: string, content: string, noteType?: string, mutationId?: string) => Promise<unknown>;
}
const flushes = new Map<string, Promise<FlushResult>>();

export function flushOfflineQueue(client: ReplayClient, scope = ''): Promise<FlushResult> {
  const existing = flushes.get(scope);
  if (existing) return existing;
  const flush = (async () => {
    const queue = await getOfflineQueue(scope);
    let successCount = 0;
    let failedCount = 0;
    for (const item of queue) {
      // A newer rating may have replaced this one while an earlier request ran.
      if (!(await getOfflineQueue(scope)).some(pending => pending.id === item.id)) continue;
      try {
        let result: any;
        switch (item.type) {
          case 'rate': result = await client.ratePaper(item.paperId, item.rating); break;
          case 'reading_list_add': result = await client.addToReadingList(item.paperId); break;
          case 'reading_list_remove': result = await client.removeFromReadingList(item.paperId); break;
          case 'reading_list_read':
            if (!client.markAsRead) throw new Error('Mark read replay unavailable');
            result = await client.markAsRead(item.paperId); break;
          case 'add_note': result = await client.addPaperNote(item.paperId, item.content, item.noteType, item.id); break;
          default: throw new Error('Unknown offline action');
        }
        if (result?.status === 'queued_offline') throw new Error('Still offline');
        await removeMutationById(item.id, scope);
        successCount++;
      } catch (err: any) {
        // If it's a permanent client error (4xx other than 401/429), remove it from the queue
        // so it doesn't act as a poison pill blocking all future offline mutations.
        const isPermanentClientError =
          typeof err?.status === 'number' &&
          err.status >= 400 &&
          err.status < 500 &&
          err.status !== 401 &&
          err.status !== 429;

        if (isPermanentClientError) {
          await removeMutationById(item.id, scope);
          failedCount++;
          continue;
        }

        // For transient/network errors, 401 auth issues, 429 rate limits, and 5xx errors:
        // preserve order and stop flush so items can be retried later.
        failedCount++;
        break;
      }
    }
    return { total: queue.length, successCount, failedCount, remainingCount: (await getOfflineQueue(scope)).length };
  })();
  flushes.set(scope, flush);
  void flush.finally(() => flushes.delete(scope)).catch(() => undefined);
  return flush;
}
