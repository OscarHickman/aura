import AsyncStorage from '@react-native-async-storage/async-storage';

export const OFFLINE_QUEUE_STORAGE_KEY = '@aura_offline_mutations';

export interface QueuedRateMutation {
  id: string;
  type: 'rate';
  paperId: string;
  rating: number;
  timestamp: number;
}

export interface QueuedReadingListAddMutation {
  id: string;
  type: 'reading_list_add';
  paperId: string;
  timestamp: number;
}

export interface QueuedReadingListRemoveMutation {
  id: string;
  type: 'reading_list_remove';
  paperId: string;
  timestamp: number;
}

export interface QueuedNoteMutation {
  id: string;
  type: 'add_note';
  paperId: string;
  content: string;
  noteType?: string;
  timestamp: number;
}

export type QueuedMutation =
  | QueuedRateMutation
  | QueuedReadingListAddMutation
  | QueuedReadingListRemoveMutation
  | QueuedNoteMutation;

export async function getOfflineQueue(): Promise<QueuedMutation[]> {
  try {
    const raw = await AsyncStorage.getItem(OFFLINE_QUEUE_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    console.warn('Failed to retrieve offline mutation queue:', e);
    return [];
  }
}

export async function clearOfflineQueue(): Promise<void> {
  try {
    await AsyncStorage.removeItem(OFFLINE_QUEUE_STORAGE_KEY);
  } catch (e) {
    console.warn('Failed to clear offline mutation queue:', e);
  }
}

export async function enqueueMutation(
  mutation: Omit<QueuedMutation, 'id' | 'timestamp'> & { id?: string; timestamp?: number }
): Promise<QueuedMutation> {
  const item: QueuedMutation = {
    ...mutation,
    id: mutation.id || `${mutation.type}_${mutation.paperId}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    timestamp: mutation.timestamp || Date.now(),
  } as QueuedMutation;

  try {
    const currentQueue = await getOfflineQueue();

    // Coalesce mutations for the same paper where appropriate
    let updatedQueue: QueuedMutation[];
    if (item.type === 'rate') {
      // Overwrite prior queued rating for this paper
      updatedQueue = currentQueue.filter((q) => !(q.type === 'rate' && q.paperId === item.paperId));
      updatedQueue.push(item);
    } else if (item.type === 'reading_list_add' || item.type === 'reading_list_remove') {
      // Replace prior reading list actions for this paper
      updatedQueue = currentQueue.filter(
        (q) => !( (q.type === 'reading_list_add' || q.type === 'reading_list_remove') && q.paperId === item.paperId )
      );
      updatedQueue.push(item);
    } else {
      // Notes are append-only
      updatedQueue = [...currentQueue, item];
    }

    await AsyncStorage.setItem(OFFLINE_QUEUE_STORAGE_KEY, JSON.stringify(updatedQueue));
    return item;
  } catch (e) {
    console.warn('Failed to persist queued mutation:', e);
    return item;
  }
}

export async function removeMutationById(id: string): Promise<void> {
  try {
    const currentQueue = await getOfflineQueue();
    const filtered = currentQueue.filter((item) => item.id !== id);
    await AsyncStorage.setItem(OFFLINE_QUEUE_STORAGE_KEY, JSON.stringify(filtered));
  } catch (e) {
    console.warn(`Failed to remove mutation ${id} from queue:`, e);
  }
}

export interface FlushResult {
  total: number;
  successCount: number;
  failedCount: number;
  remainingCount: number;
}

export async function flushOfflineQueue(apiClient: {
  ratePaper: (paperId: string, rating: number) => Promise<any>;
  addToReadingList: (paperId: string) => Promise<any>;
  removeFromReadingList: (paperId: string) => Promise<any>;
  addPaperNote: (paperId: string, content: string, noteType?: string) => Promise<any>;
}): Promise<FlushResult> {
  const queue = await getOfflineQueue();
  if (queue.length === 0) {
    return { total: 0, successCount: 0, failedCount: 0, remainingCount: 0 };
  }

  let successCount = 0;
  let failedCount = 0;
  const remaining: QueuedMutation[] = [];

  for (const item of queue) {
    try {
      if (item.type === 'rate') {
        await apiClient.ratePaper(item.paperId, item.rating);
      } else if (item.type === 'reading_list_add') {
        await apiClient.addToReadingList(item.paperId);
      } else if (item.type === 'reading_list_remove') {
        await apiClient.removeFromReadingList(item.paperId);
      } else if (item.type === 'add_note') {
        await apiClient.addPaperNote(item.paperId, item.content, item.noteType);
      }
      successCount++;
    } catch (e: any) {
      console.warn(`Offline replay error for ${item.type} on ${item.paperId}:`, e);
      failedCount++;
      remaining.push(item);
    }
  }

  try {
    await AsyncStorage.setItem(OFFLINE_QUEUE_STORAGE_KEY, JSON.stringify(remaining));
  } catch (e) {
    console.warn('Failed to update queue after flush:', e);
  }

  return {
    total: queue.length,
    successCount,
    failedCount,
    remainingCount: remaining.length,
  };
}
