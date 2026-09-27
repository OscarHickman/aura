import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { Bookmark, Check, Trash2, ChevronRight, BookOpen } from 'lucide-react-native';
import { theme } from '../constants/theme';
import { api } from '../api/client';
import { Paper } from '../types';

interface ReadingListScreenProps {
  navigation: any;
}

export const ReadingListScreen: React.FC<ReadingListScreenProps> = ({ navigation }) => {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [activeTab, setActiveTab] = useState<'unread' | 'read'>('unread');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  const fetchReadingList = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.getReadingList(activeTab);
      setPapers(res.papers || []);
    } catch (e) {
      console.warn('Failed to fetch reading list:', e);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchReadingList();
  }, [fetchReadingList]);

  const onRefresh = () => {
    setIsRefreshing(true);
    fetchReadingList();
  };

  const handleMarkAsRead = async (arxivId: string) => {
    try {
      await api.markAsRead(arxivId);
      setPapers((prev) => prev.filter((p) => p.arxiv_id !== arxivId));
    } catch (e) {
      console.warn('Mark read error:', e);
    }
  };

  const handleRemove = async (arxivId: string) => {
    try {
      await api.removeFromReadingList(arxivId);
      setPapers((prev) => prev.filter((p) => p.arxiv_id !== arxivId));
    } catch (e) {
      console.warn('Remove error:', e);
    }
  };

  const renderItem = ({ item }: { item: Paper }) => (
    <TouchableOpacity
      style={styles.card}
      activeOpacity={0.7}
      onPress={() => navigation.navigate('PaperDetail', { arxivId: item.arxiv_id })}
    >
      <View style={styles.cardMain}>
        <Text style={styles.title} numberOfLines={2}>
          {item.title}
        </Text>
        <Text style={styles.authors} numberOfLines={1}>
          {(item.authors || []).slice(0, 3).join(', ')}
        </Text>
      </View>

      <View style={styles.actions}>
        {activeTab === 'unread' && (
          <TouchableOpacity
            style={[styles.actionBtn, styles.checkBtn]}
            onPress={() => handleMarkAsRead(item.arxiv_id)}
          >
            <Check size={16} color={theme.colors.success} />
          </TouchableOpacity>
        )}

        <TouchableOpacity
          style={[styles.actionBtn, styles.deleteBtn]}
          onPress={() => handleRemove(item.arxiv_id)}
        >
          <Trash2 size={16} color={theme.colors.danger} />
        </TouchableOpacity>

        <ChevronRight size={18} color={theme.colors.textDim} />
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {/* Segment Tabs */}
      <View style={styles.tabBar}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'unread' && styles.tabActive]}
          onPress={() => setActiveTab('unread')}
        >
          <Text style={[styles.tabText, activeTab === 'unread' && styles.tabTextActive]}>
            Unread
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'read' && styles.tabActive]}
          onPress={() => setActiveTab('read')}
        >
          <Text style={[styles.tabText, activeTab === 'read' && styles.tabTextActive]}>
            Read History
          </Text>
        </TouchableOpacity>
      </View>

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
              <BookOpen size={40} color={theme.colors.textDim} />
              <Text style={styles.emptyTitle}>Your reading list is empty</Text>
              <Text style={styles.emptySubtitle}>
                Save papers from the Triage deck or Feed to read them here.
              </Text>
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
  tabBar: {
    flexDirection: 'row',
    margin: theme.spacing.md,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.full,
    padding: 4,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  tab: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: theme.borderRadius.full,
  },
  tabActive: {
    backgroundColor: theme.colors.primary,
  },
  tabText: {
    color: theme.colors.textMuted,
    fontWeight: '600',
    fontSize: theme.typography.sm,
  },
  tabTextActive: {
    color: theme.colors.white,
  },
  listContent: {
    paddingHorizontal: theme.spacing.md,
    paddingBottom: theme.spacing.xl,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.surface,
    padding: theme.spacing.md,
    borderRadius: theme.borderRadius.md,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  cardMain: {
    flex: 1,
    marginRight: theme.spacing.sm,
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.sm,
    fontWeight: '600',
    lineHeight: 20,
    marginBottom: 4,
  },
  authors: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  actionBtn: {
    padding: 8,
    borderRadius: theme.borderRadius.sm,
    backgroundColor: theme.colors.surfaceLight,
  },
  checkBtn: {
    backgroundColor: 'rgba(16, 185, 129, 0.12)',
  },
  deleteBtn: {
    backgroundColor: 'rgba(239, 68, 68, 0.12)',
  },
  emptyContainer: {
    padding: theme.spacing.xl * 2,
    alignItems: 'center',
    marginTop: theme.spacing.xl,
  },
  emptyTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.md,
    fontWeight: '700',
    marginTop: theme.spacing.md,
  },
  emptySubtitle: {
    color: theme.colors.textDim,
    fontSize: theme.typography.sm,
    textAlign: 'center',
    marginTop: 4,
  },
});
