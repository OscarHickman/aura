import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  Dimensions,
  Alert,
} from 'react-native';
import { ThumbsUp, ThumbsDown, Bookmark, ExternalLink, Sparkles, RefreshCw, MessageSquare } from 'lucide-react-native';
import { theme } from '../constants/theme';
import { api } from '../api/client';
import { Paper } from '../types';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface TriageScreenProps {
  navigation: any;
}

export const TriageScreen: React.FC<TriageScreenProps> = ({ navigation }) => {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isActing, setIsActing] = useState<boolean>(false);

  const loadPapers = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await api.getPapers({ filter: 'unrated', per_page: 40 });
      setPapers(res.papers || []);
      setCurrentIndex(0);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to load papers');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPapers();
  }, [loadPapers]);

  const currentPaper = papers[currentIndex];

  const handleRate = async (rating: number) => {
    if (!currentPaper || isActing) return;
    setIsActing(true);
    try {
      await api.ratePaper(currentPaper.arxiv_id, rating);
      setCurrentIndex((prev) => prev + 1);
    } catch (err: any) {
      Alert.alert('Rating Error', err.message);
    } finally {
      setIsActing(false);
    }
  };

  const handleToggleReadingList = async () => {
    if (!currentPaper || isActing) return;
    setIsActing(true);
    try {
      if (currentPaper.in_reading_list) {
        await api.removeFromReadingList(currentPaper.arxiv_id);
        currentPaper.in_reading_list = false;
      } else {
        await api.addToReadingList(currentPaper.arxiv_id);
        currentPaper.in_reading_list = true;
      }
      setPapers([...papers]);
    } catch (err: any) {
      Alert.alert('Reading List Error', err.message);
    } finally {
      setIsActing(false);
    }
  };

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
        <Text style={styles.loadingText}>Fetching recommended papers...</Text>
      </View>
    );
  }

  if (!currentPaper || currentIndex >= papers.length) {
    return (
      <View style={styles.centerContainer}>
        <Sparkles size={48} color={theme.colors.primaryLight} />
        <Text style={styles.emptyTitle}>You're All Caught Up!</Text>
        <Text style={styles.emptySubtitle}>
          No more unrated recommendations right now.
        </Text>
        <TouchableOpacity style={styles.refreshButton} onPress={loadPapers}>
          <RefreshCw size={18} color={theme.colors.white} />
          <Text style={styles.refreshButtonText}>Refresh Deck</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const scorePercent = Math.round((currentPaper.score ?? 0.5) * 100);

  return (
    <View style={styles.container}>
      {/* Progress header */}
      <View style={styles.progressContainer}>
        <Text style={styles.progressText}>
          Card {currentIndex + 1} of {papers.length}
        </Text>
        <View style={styles.scoreBadge}>
          <Text style={styles.scoreText}>{scorePercent}% Match</Text>
        </View>
      </View>

      {/* Main card */}
      <View style={styles.cardWrapper}>
        <ScrollView
          style={styles.card}
          contentContainerStyle={styles.cardContent}
          showsVerticalScrollIndicator={true}
        >
          {/* Categories */}
          <View style={styles.categoryRow}>
            {(currentPaper.categories || []).map((cat, idx) => (
              <View key={idx} style={styles.categoryBadge}>
                <Text style={styles.categoryText}>{cat}</Text>
              </View>
            ))}
            {currentPaper.from_followed_author && (
              <View style={[styles.categoryBadge, styles.networkBadge]}>
                <Text style={styles.networkBadgeText}>Followed Author</Text>
              </View>
            )}
          </View>

          {/* Title */}
          <Text style={styles.title}>{currentPaper.title}</Text>

          {/* Authors */}
          <Text style={styles.authors}>
            {(currentPaper.authors || []).slice(0, 4).join(', ')}
            {(currentPaper.authors || []).length > 4 ? ' et al.' : ''}
          </Text>

          {/* AI Summary Highlight */}
          {currentPaper.summary ? (
            <View style={styles.summaryBox}>
              <View style={styles.summaryHeader}>
                <Sparkles size={14} color={theme.colors.primaryLight} />
                <Text style={styles.summaryTitle}>AI Summary</Text>
              </View>
              <Text style={styles.summaryText}>{currentPaper.summary}</Text>
            </View>
          ) : null}

          {/* Abstract */}
          <Text style={styles.abstractHeader}>Abstract</Text>
          <Text style={styles.abstractText}>{currentPaper.abstract}</Text>
        </ScrollView>
      </View>

      {/* Floating Action Controls */}
      <View style={styles.actionBar}>
        {/* Dislike / Skip */}
        <TouchableOpacity
          style={[styles.actionBtn, styles.dislikeBtn]}
          onPress={() => handleRate(-1)}
          disabled={isActing}
        >
          <ThumbsDown size={24} color={theme.colors.danger} />
          <Text style={styles.dislikeBtnText}>Skip</Text>
        </TouchableOpacity>

        {/* Reading list bookmark */}
        <TouchableOpacity
          style={[
            styles.actionBtn,
            styles.bookmarkBtn,
            currentPaper.in_reading_list && styles.bookmarkBtnActive,
          ]}
          onPress={handleToggleReadingList}
          disabled={isActing}
        >
          <Bookmark
            size={22}
            color={currentPaper.in_reading_list ? theme.colors.warning : theme.colors.textMuted}
          />
        </TouchableOpacity>

        {/* Open Details / Ask */}
        <TouchableOpacity
          style={[styles.actionBtn, styles.detailBtn]}
          onPress={() => navigation.navigate('PaperDetail', { arxivId: currentPaper.arxiv_id })}
        >
          <MessageSquare size={22} color={theme.colors.primaryLight} />
        </TouchableOpacity>

        {/* Like / Thumbs up */}
        <TouchableOpacity
          style={[styles.actionBtn, styles.likeBtn]}
          onPress={() => handleRate(1)}
          disabled={isActing}
        >
          <ThumbsUp size={24} color={theme.colors.success} />
          <Text style={styles.likeBtnText}>Like</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
    paddingTop: theme.spacing.sm,
  },
  centerContainer: {
    flex: 1,
    backgroundColor: theme.colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.xl,
  },
  loadingText: {
    color: theme.colors.textMuted,
    marginTop: theme.spacing.md,
    fontSize: theme.typography.md,
  },
  emptyTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.xl,
    fontWeight: '700',
    marginTop: theme.spacing.lg,
  },
  emptySubtitle: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.sm,
    textAlign: 'center',
    marginTop: theme.spacing.xs,
    marginBottom: theme.spacing.xl,
  },
  refreshButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: theme.colors.primary,
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.xl,
    borderRadius: theme.borderRadius.full,
    gap: theme.spacing.sm,
  },
  refreshButtonText: {
    color: theme.colors.white,
    fontWeight: '600',
    fontSize: theme.typography.md,
  },
  progressContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.xs,
  },
  progressText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.sm,
    fontWeight: '500',
  },
  scoreBadge: {
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(99, 102, 241, 0.4)',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 2,
    borderRadius: theme.borderRadius.full,
  },
  scoreText: {
    color: theme.colors.primaryLight,
    fontSize: theme.typography.xs,
    fontWeight: '700',
  },
  cardWrapper: {
    flex: 1,
    marginHorizontal: theme.spacing.md,
    marginVertical: theme.spacing.sm,
    borderRadius: theme.borderRadius.lg,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
    overflow: 'hidden',
  },
  card: {
    flex: 1,
  },
  cardContent: {
    padding: theme.spacing.lg,
    paddingBottom: theme.spacing.xl * 2,
  },
  categoryRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
    marginBottom: theme.spacing.sm,
  },
  categoryBadge: {
    backgroundColor: theme.colors.surfaceLight,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 3,
    borderRadius: theme.borderRadius.sm,
  },
  categoryText: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.xs,
    fontWeight: '600',
  },
  networkBadge: {
    backgroundColor: 'rgba(56, 189, 248, 0.15)',
  },
  networkBadgeText: {
    color: '#38bdf8',
    fontSize: theme.typography.xs,
    fontWeight: '600',
  },
  title: {
    color: theme.colors.text,
    fontSize: theme.typography.xl,
    fontWeight: '700',
    lineHeight: 28,
    marginBottom: theme.spacing.xs,
  },
  authors: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.sm,
    marginBottom: theme.spacing.md,
  },
  summaryBox: {
    backgroundColor: 'rgba(99, 102, 241, 0.08)',
    borderLeftWidth: 3,
    borderLeftColor: theme.colors.primary,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.lg,
  },
  summaryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  summaryTitle: {
    color: theme.colors.primaryLight,
    fontWeight: '700',
    fontSize: theme.typography.xs,
    textTransform: 'uppercase',
  },
  summaryText: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.sm,
    lineHeight: 20,
  },
  abstractHeader: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.xs,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: theme.spacing.xs,
  },
  abstractText: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.md,
    lineHeight: 24,
  },
  actionBar: {
    flexDirection: 'row',
    justifyContent: 'space-evenly',
    alignItems: 'center',
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.md,
    backgroundColor: theme.colors.background,
    borderTopWidth: 1,
    borderTopColor: theme.colors.surfaceBorder,
  },
  actionBtn: {
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: theme.borderRadius.full,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.lg,
  },
  dislikeBtn: {
    backgroundColor: 'rgba(239, 68, 68, 0.12)',
    flexDirection: 'row',
    gap: 6,
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.3)',
  },
  dislikeBtnText: {
    color: theme.colors.danger,
    fontWeight: '700',
    fontSize: theme.typography.sm,
  },
  likeBtn: {
    backgroundColor: 'rgba(16, 185, 129, 0.12)',
    flexDirection: 'row',
    gap: 6,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.3)',
  },
  likeBtnText: {
    color: theme.colors.success,
    fontWeight: '700',
    fontSize: theme.typography.sm,
  },
  bookmarkBtn: {
    backgroundColor: theme.colors.surface,
    paddingHorizontal: theme.spacing.md,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  bookmarkBtnActive: {
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    borderColor: 'rgba(245, 158, 11, 0.4)',
  },
  detailBtn: {
    backgroundColor: theme.colors.surface,
    paddingHorizontal: theme.spacing.md,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
});
