import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { FeedScreen } from '../FeedScreen';
import { TriageScreen } from '../TriageScreen';
import { ReadingListScreen } from '../ReadingListScreen';
import { IntelScreen } from '../IntelScreen';
import { PaperDetailScreen } from '../PaperDetailScreen';
import { api } from '../../api/client';

jest.mock('expo-clipboard', () => ({
  setStringAsync: jest.fn().mockResolvedValue(true),
  getStringAsync: jest.fn().mockResolvedValue(''),
}));

jest.mock('lucide-react-native', () => {
  const icon = () => null;
  return Object.fromEntries([
    'Search', 'Sparkles', 'Bookmark', 'ThumbsUp', 'ThumbsDown', 'ChevronRight',
    'Check', 'Trash2', 'BookOpen', 'ExternalLink', 'RefreshCw', 'MessageSquare',
    'RotateCcw', 'TrendingUp', 'Calendar', 'AlertTriangle', 'X', 'Flame', 'Clock',
    'Copy', 'Plus', 'Layers', 'FileText', 'StickyNote', 'FolderPlus', 'Send'
  ].map(name => [name, icon]));
});

jest.mock('../../api/client', () => ({ api: {
  getPapers: jest.fn(), ratePaper: jest.fn(), addToReadingList: jest.fn(),
  removeFromReadingList: jest.fn(), getReadingList: jest.fn(), markAsRead: jest.fn(),
  getBriefs: jest.fn(), getBrief: jest.fn(), getTrends: jest.fn(),
  getPaper: jest.fn(), getPaperNotes: jest.fn(), getDeepSummary: jest.fn(),
  getPaperBibtex: jest.fn(), getCollections: jest.fn(), createCollection: jest.fn(),
  addPaperToCollection: jest.fn(),
} }));
jest.mock('@react-navigation/native', () => ({
  useFocusEffect: (effect: () => void) => require('react').useEffect(effect, [effect]),
}));
const mockApi = jest.mocked(api);
const navigation = { navigate: jest.fn(), push: jest.fn() };
const paper = (id: number) => ({ arxiv_id: `2401.${id}`, title: `Paper ${id}`, authors: ['Researcher'], categories: [], abstract: 'An abstract.' });
const response = (ids: number[], hasMore = false) => ({ papers: ids.map(paper), page: 1, per_page: 25, total: ids.length, filter: 'unrated', has_more: hasMore });
beforeEach(() => {
  jest.resetAllMocks();
  mockApi.getPapers.mockResolvedValue(response([1, 2]));
  mockApi.getReadingList.mockResolvedValue({ papers: [paper(1)] });
  mockApi.ratePaper.mockResolvedValue({ status: 'ok' });
  mockApi.markAsRead.mockResolvedValue({ status: 'ok' });
  mockApi.addToReadingList.mockResolvedValue({ status: 'ok' });
});

it('triages the current card, saves the next card, and opens its reader', async () => {
  await render(<TriageScreen navigation={navigation} />);
  await screen.findByText('Paper 1');
  await fireEvent.press(screen.getByText('Like'));
  await screen.findByText('Paper 2');
  expect(mockApi.ratePaper).toHaveBeenCalledWith('2401.1', 1);
  await fireEvent.press(screen.getByLabelText('Save paper'));
  expect(mockApi.addToReadingList).toHaveBeenCalledWith('2401.2');
  await fireEvent.press(screen.getByLabelText('Read paper details'));
  expect(navigation.navigate).toHaveBeenCalledWith('PaperDetail', { arxivId: '2401.2' });
  await fireEvent.press(screen.getByText('Skip'));
  expect(mockApi.ratePaper).toHaveBeenLastCalledWith('2401.2', -1);
  await screen.findByText("You're All Caught Up!");
});

it('loads successive feed pages once and stops at the end', async () => {
  mockApi.getPapers.mockResolvedValueOnce(response([1], true)).mockResolvedValueOnce(response([1, 2]));
  await render(<FeedScreen navigation={navigation} />);
  await screen.findByText('Paper 1');
  await fireEvent(screen.getByTestId('paper-feed'), 'onEndReached');
  await screen.findByText('Paper 2');
  expect(screen.getAllByText('Paper 1')).toHaveLength(1);
  expect(mockApi.getPapers).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  await fireEvent(screen.getByTestId('paper-feed'), 'onEndReached');
  expect(mockApi.getPapers).toHaveBeenCalledTimes(2);
});

it('submits search at page one and ignores a stale filter response', async () => {
  let finishOld!: (value: ReturnType<typeof response>) => void;
  mockApi.getPapers.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve; }));
  mockApi.getPapers.mockResolvedValueOnce(response([3]));
  await render(<FeedScreen navigation={navigation} />);
  const search = screen.getByPlaceholderText('Search papers, authors, topics...');
  await fireEvent.changeText(search, 'cosmology');
  await fireEvent(search, 'submitEditing');
  await screen.findByText('Paper 3');
  await act(async () => finishOld(response([1])));
  expect(screen.queryByText('Paper 1')).toBeNull();
  expect(mockApi.getPapers).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'cosmology', page: 1 }));
});

it('shows recovery instead of an empty feed when the server is unreachable', async () => {
  mockApi.getPapers.mockRejectedValueOnce(new Error('Network request failed'));
  await render(<FeedScreen navigation={navigation} />);
  await screen.findByText('Unable to load papers');
  await fireEvent.press(screen.getByText('Connection settings'));
  expect(navigation.navigate).toHaveBeenCalledWith('SettingsTab');
  await fireEvent.press(screen.getByText('Try again'));
  await screen.findByText('Paper 1');
});

it('marks a saved paper read and switches to read history', async () => {
  await render(<ReadingListScreen navigation={navigation} />);
  await screen.findByText('Paper 1');
  await fireEvent.press(screen.getByLabelText('Mark as read'));
  await waitFor(() => expect(screen.queryByText('Paper 1')).toBeNull());
  expect(mockApi.markAsRead).toHaveBeenCalledWith('2401.1');
  await fireEvent.press(screen.getByText('Read History'));
  await screen.findByText('Paper 1');
  expect(mockApi.getReadingList).toHaveBeenLastCalledWith('read');
  expect(screen.queryByLabelText('Mark as read')).toBeNull();
});

it('labels cached reading-list data as offline', async () => {
  mockApi.getReadingList.mockResolvedValue({ papers: [paper(1)], offline: true });
  await render(<ReadingListScreen navigation={navigation} />);
  await screen.findByText('Offline · Showing saved papers');
  expect(screen.getByText('Paper 1')).toBeTruthy();
});

it('renders IntelScreen briefs and allows switching to Trend Radar', async () => {
  mockApi.getBriefs.mockResolvedValue({
    briefs: [{ date: '2026-10-18', content: '# Weekly Executive Summary\nKey breakthroughs.' }],
  });
  mockApi.getBrief.mockResolvedValue({
    brief: { date: '2026-10-18', content: '# Weekly Executive Summary\nKey breakthroughs.' },
  });
  mockApi.getTrends.mockResolvedValue({
    trends: { topics: [{ topic: 'cosmology', count: 12 }] },
    alerts: [{ id: 1, tag: 'dark energy', previous_weekly_rate: 1.0, current_rate: 4.0, spike_factor: 4.0, detected_at: '2026-10-18' }],
    upcoming_events: [{ id: 1, name: 'Cosmo 2026', date: '2026-11-01', type: 'Conference' }],
  });

  await render(<IntelScreen navigation={navigation} />);
  await screen.findByText('Archived Research Briefs');
  expect(screen.getByText(/2026-10-18/)).toBeTruthy();

  // Switch to Trend Radar tab
  await fireEvent.press(screen.getByText('Trend Radar'));
  await screen.findByText('Significant Topic Spikes (Last 48h)');
  expect(screen.getByText('dark energy')).toBeTruthy();
  expect(screen.getByText('Cosmo 2026')).toBeTruthy();
});

it('PaperDetailScreen supports reading mode switch, BibTeX copy, and similar papers', async () => {
  mockApi.getPaper.mockResolvedValue({
    ...paper(1),
    similar_papers: [paper(2)],
  });
  mockApi.getPaperNotes.mockResolvedValue({ notes: [] });
  mockApi.getPaperBibtex.mockResolvedValue({ arxiv_id: '2401.1', bibtex: '@article{2401.1}' });
  mockApi.getDeepSummary.mockResolvedValue({ arxiv_id: '2401.1', mode: 'grad_student', summary: 'Grad summary content' });

  await render(<PaperDetailScreen route={{ params: { arxivId: '2401.1' } }} navigation={navigation} />);
  await screen.findByText('Paper 1');

  // Copy BibTeX
  await fireEvent.press(screen.getByText('BibTeX'));
  expect(mockApi.getPaperBibtex).toHaveBeenCalledWith('2401.1');

  // Switch to Grad Student deep summary mode
  await fireEvent.press(screen.getByText('Grad Student'));
  await screen.findByText('Grad summary content');
  expect(mockApi.getDeepSummary).toHaveBeenCalledWith('2401.1', 'grad_student');

  // Similar papers displayed
  expect(screen.getByText('Similar Papers (1)')).toBeTruthy();
  expect(screen.getByText('Paper 2')).toBeTruthy();
});

