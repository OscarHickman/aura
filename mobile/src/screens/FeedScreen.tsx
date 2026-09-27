import React, { useState, useEffect, useCallback } from 'react';
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
  const [page, setPage] = useState<number>(1);

  const fetchPapers = useCallback(async (reset: boolean = false) => {
    if (reset) {
      setIsLoading(true);
      setPage(1);
    }
    try {
      const currentPage = reset ? 1 : page;
      const res = await api.getPapers({
        filter: searchQuery ? undefined : filter,
        q: searchQuery || undefined,
        page: currentPage,
        per_page: 25,
      });
      if (reset) {
        setPapers(res.papers || []);
      } else {
        setPapers((prev) => [...prev, ...(res.papers || [])]);
      }
    } catch (e) {
      console.warn('Failed to load feed:', e);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [filter, searchQuery, page]);

  useEffect(() => {
    fetchPapers(true);
  }, [filter]);

  const onRefresh = () => {
    setIsRefreshing(true);
    fetchPapers(true);
  };

  const handleSearchSubmit = () => {
    fetchPapers(true);
  };

  const handleRate = async (arxivId: string, rating: number) => {
    try {
      await api.ratePaper(arxivId, rating);
      setPapers((prev) =>
        prev.map((p) => (p.arxiv_id === arxivId ? { ...p, rating } : p))
      );
    } catch (e) {
      console.warn('Rate error:', e);
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
      console.warn('Reading list error:', e);
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
              onPress={() => handleRate(item.arxiv_id, -1)}
            >
              <ThumbsDown
                size={18}
                color={item.rating === 0 || item.rating === -1 ? theme.colors.danger : theme.colors.textDim}
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionIcon}
              onPress={() => handleRate(item.arxiv_id, 1)}
            >
              <ThumbsUp
                size={18}
                color={item.rating === 1 ? theme.colors.success : theme.colors.textDim}
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionIcon}
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

      {/* Feed list */}
      {isLoading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
        </View>
      ) : (
        <FlatList
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
