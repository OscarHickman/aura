import React, { useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  TextInput,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { Search, Sparkles, Bookmark, ThumbsUp, ThumbsDown, ChevronRight } from 'lucide-react-native';
import { theme } from '../constants/theme';
import { api } from '../api/client';
import { useFocusEffect } from '@react-navigation/native';
import { RecoveryView } from '../components/RecoveryView';
import { Paper } from '../types';

interface FeedScreenProps {
  navigation: any;
}

export const FeedScreen: React.FC<FeedScreenProps> = ({ navigation }) => {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [filter, setFilter] = useState<'unrated' | 'liked' | 'all'>('unrated');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const page = useRef(0);
  const requestId = useRef(0);
  const loading = useRef(false);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState('');

  const fetchPapers = useCallback(async (reset = false) => {
    if (!reset && (loading.current || !hasMore)) return;
    const id = ++requestId.current;
    loading.current = true;
    if (reset) { setIsLoading(true); setPapers([]); }
    else setLoadingMore(true);
    setError(null);
    const currentPage = reset ? 1 : page.current + 1;
    try {
      const res = await api.getPapers({
        filter: submittedQuery ? undefined : filter,
        q: submittedQuery || undefined,
        page: currentPage,
        per_page: 25,
      });
      if (id !== requestId.current) return;
      const incoming = res.papers || [];
      setPapers(prev => reset ? incoming : [...new Map([...prev, ...incoming].map(p => [p.arxiv_id, p])).values()]);
      page.current = currentPage;
      // Older servers report only the number ranked so far; a full page may
      // still have a successor. New servers provide an explicit has_more.
      setHasMore(res.has_more ?? incoming.length === 25);
    } catch {
      if (id === requestId.current) setError('Check your connection and your AURA server, then try again.');
    } finally {
      if (id === requestId.current) {
        loading.current = false;
        setIsLoading(false);
        setLoadingMore(false);
        setIsRefreshing(false);
      }
    }
  }, [filter, submittedQuery, hasMore]);

  const fetchRef = useRef(fetchPapers);
  fetchRef.current = fetchPapers;
  useFocusEffect(useCallback(() => {
    void fetchRef.current(true);
    return () => { requestId.current++; loading.current = false; };
  }, [filter, submittedQuery]));

  const onRefresh = () => { setIsRefreshing(true); void fetchPapers(true); };
  const handleSearchSubmit = () => {
    const query = searchQuery.trim();
    if (query === submittedQuery) void fetchPapers(true);
    else setSubmittedQuery(query);
  };

  const handleRate = async (arxivId: string, rating: number) => {
    try {
      await api.ratePaper(arxivId, rating);
      setPapers((prev) =>
        prev.map((p) => (p.arxiv_id === arxivId ? { ...p, rating } : p))
      );
    } catch (e) {
      setError('Could not save your rating. Please try again.');
    }
  };

  const handleToggleReadingList = async (arxivId: string, currentlyInList?: boolean) => {
    try {
      if (currentlyInList) {
        await api.removeFromReadingList(arxivId);
      } else {
        await api.addToReadingList(arxivId);
      }
      setPapers((prev) =>
        prev.map((p) =>
          p.arxiv_id === arxivId ? { ...p, in_reading_list: !currentlyInList } : p
        )
      );
    } catch (e) {
      setError('Could not update your reading list. Please try again.');
    }
  };

  const renderItem = ({ item }: { item: Paper }) => {
    const scorePct = Math.round((item.score ?? 0.5) * 100);
    return (
      <TouchableOpacity
        style={styles.card}
        activeOpacity={0.7}
        onPress={() => navigation.navigate('PaperDetail', { arxivId: item.arxiv_id })}
      >
        <View style={styles.cardHeader}>
          <View style={styles.scoreBadge}>
            <Text style={styles.scoreText}>{scorePct}% match</Text>
          </View>
          <Text style={styles.dateText}>
            {item.published ? item.published.substring(0, 10) : ''}
          </Text>
        </View>

        <Text style={styles.title} numberOfLines={2}>
          {item.title}
        </Text>

        <Text style={styles.authors} numberOfLines={1}>
          {(item.authors || []).slice(0, 3).join(', ')}
          {(item.authors || []).length > 3 ? ' et al.' : ''}
        </Text>

        {item.summary ? (
          <View style={styles.summaryBox}>
            <Sparkles size={13} color={theme.colors.primaryLight} />
            <Text style={styles.summaryText} numberOfLines={2}>
              {item.summary}
            </Text>
          </View>
        ) : (
          <Text style={styles.abstractSnippet} numberOfLines={2}>
            {item.abstract}
          </Text>
        )}

        <View style={styles.cardFooter}>
          <View style={styles.categories}>
            {(item.categories || []).slice(0, 2).map((cat, idx) => (
              <View key={idx} style={styles.catBadge}>
                <Text style={styles.catText}>{cat}</Text>
              </View>
            ))}
          </View>

          <View style={styles.actions}>
            <TouchableOpacity
              style={styles.actionIcon}
              accessibilityLabel="Dislike paper"
              onPress={() => handleRate(item.arxiv_id, 0)}
            >
              <ThumbsDown
                size={18}
                color={item.rating === 0 || item.rating === -1 ? theme.colors.danger : theme.colors.textDim}
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionIcon}
              accessibilityLabel="Like paper"
              onPress={() => handleRate(item.arxiv_id, 1)}
            >
              <ThumbsUp
                size={18}
                color={item.rating === 1 ? theme.colors.success : theme.colors.textDim}
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionIcon}
              accessibilityLabel={item.in_reading_list ? "Unsave paper" : "Save paper"}
              onPress={() => handleToggleReadingList(item.arxiv_id, item.in_reading_list)}
            >
              <Bookmark
                size={18}
                color={item.in_reading_list ? theme.colors.warning : theme.colors.textDim}
              />
            </TouchableOpacity>

            <ChevronRight size={18} color={theme.colors.textDim} />
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      {/* Search header */}
      <View style={styles.searchContainer}>
        <Search size={18} color={theme.colors.textDim} style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          placeholder="Search papers, authors, topics..."
          placeholderTextColor={theme.colors.textDim}
          value={searchQuery}
          onChangeText={setSearchQuery}
          onSubmitEditing={handleSearchSubmit}
          returnKeyType="search"
        />
      </View>

      {/* Filter Tabs */}
      <View style={styles.filterRow}>
        {(['unrated', 'liked', 'all'] as const).map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[styles.filterTab, filter === tab && styles.filterTabActive]}
            onPress={() => setFilter(tab)}
          >
            <Text
              style={[styles.filterTabText, filter === tab && styles.filterTabTextActive]}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {error && papers.length > 0 && <TouchableOpacity onPress={() => fetchPapers(false)}><Text style={styles.emptyText}>{error} Tap to retry.</Text></TouchableOpacity>}
      {/* Feed list */}
      {isLoading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
        </View>
      ) : error && papers.length === 0 ? (
        <RecoveryView onRetry={() => fetchPapers(true)} onSettings={() => navigation.navigate('SettingsTab')} />
      ) : (
        <FlatList
          testID="paper-feed"
          onEndReached={() => { if (!error) void fetchPapers(false); }}
          onEndReachedThreshold={0.4}
          ListFooterComponent={loadingMore ? <ActivityIndicator /> : null}
          data={papers}
          keyExtractor={(item) => item.arxiv_id}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={onRefresh}
              tintColor={theme.colors.primary}
            />
          }
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyText}>No papers found for this filter.</Text>
            </View>
          }
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surface,
    marginHorizontal: theme.spacing.md,
    marginTop: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    borderRadius: theme.borderRadius.md,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  searchIcon: {
    marginRight: theme.spacing.sm,
  },
  searchInput: {
    flex: 1,
    height: 44,
    color: theme.colors.text,
    fontSize: theme.typography.sm,
  },
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xs,
  },
  filterTab: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: theme.borderRadius.full,
    backgroundColor: theme.colors.surface,
  },
  filterTabActive: {
    backgroundColor: theme.colors.primary,
  },
  filterTabText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.xs,
    fontWeight: '600',
  },
  filterTabTextActive: {
    color: theme.colors.white,
  },
  listContent: {
    paddingHorizontal: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.xs,
  },
  scoreBadge: {
    backgroundColor: 'rgba(99, 102, 241, 0.12)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: theme.borderRadius.full,
  },
  scoreText: {
    color: theme.colors.primaryLight,
    fontSize: theme.typography.xs,
    fontWeight: '700',
  },
  dateText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.md,
    fontWeight: '700',
    lineHeight: 22,
    marginBottom: 4,
  },
  authors: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.xs,
    marginBottom: theme.spacing.sm,
  },
  summaryBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(99, 102, 241, 0.07)',
    padding: theme.spacing.xs + 2,
    borderRadius: theme.borderRadius.sm,
    marginBottom: theme.spacing.sm,
  },
  summaryText: {
    flex: 1,
    color: theme.colors.textSecondary,
    fontSize: theme.typography.xs,
    lineHeight: 18,
  },
  abstractSnippet: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
    lineHeight: 18,
    marginBottom: theme.spacing.sm,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
  },
  categories: {
    flexDirection: 'row',
    gap: 4,
  },
  catBadge: {
    backgroundColor: theme.colors.surfaceLight,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  catText: {
    color: theme.colors.textSecondary,
    fontSize: 10,
    fontWeight: '600',
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  actionIcon: {
    padding: 4,
  },
  emptyContainer: {
    padding: theme.spacing.xl * 2,
    alignItems: 'center',
  },
  emptyText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.sm,
  },
});
