import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  Dimensions,
  Alert,
  Animated,
  PanResponder,
} from 'react-native';
import { ThumbsUp, ThumbsDown, Bookmark, ExternalLink, Sparkles, RefreshCw, MessageSquare, RotateCcw, Compass } from 'lucide-react-native';
import { theme } from '../constants/theme';
import { api } from '../api/client';
import { useFocusEffect } from '@react-navigation/native';
import { RecoveryView } from '../components/RecoveryView';
import { Paper } from '../types';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const SWIPE_THRESHOLD = 0.25 * SCREEN_WIDTH;
const isTestEnv = typeof process !== 'undefined' && process.env?.NODE_ENV === 'test';

interface TriageScreenProps {
  navigation: any;
}

export const TriageScreen: React.FC<TriageScreenProps> = ({ navigation }) => {
  const [error, setError] = useState(false);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isActing, setIsActing] = useState<boolean>(false);
  const [lastAction, setLastAction] = useState<{
    index: number;
    paperId: string;
    action: 'rate' | 'bookmark';
    previousRating?: number | null;
    previousInReadingList?: boolean;
  } | null>(null);

  const [triageMode, setTriageMode] = useState<'recommended' | 'explore'>('recommended');

  const loadPapers = useCallback(async (mode?: 'recommended' | 'explore') => {
    const activeMode = mode || triageMode;
    setIsLoading(true);
    setError(false);
    try {
      const filter = activeMode === 'explore' ? 'explore' : 'unrated';
      const res = await api.getPapers({ filter, per_page: 40 });
      setPapers(res.papers || []);
      setCurrentIndex(0);
      setLastAction(null);
    } catch (err: any) {
      setError(true);
    } finally {
      setIsLoading(false);
    }
  }, [triageMode]);

  useFocusEffect(
    useCallback(() => {
      // If we haven't loaded papers yet, load them
      if (papers.length === 0 && !error) {
        loadPapers();
      }
    }, [loadPapers, papers.length, error])
  );

  const currentPaper = papers[currentIndex];

  const position = useRef(new Animated.ValueXY()).current;
  const currentPaperRef = useRef<Paper | null>(null);
  currentPaperRef.current = currentPaper;
  const currentIndexRef = useRef(currentIndex);
  currentIndexRef.current = currentIndex;
  const isActingRef = useRef(isActing);
  isActingRef.current = isActing;

  const handleRate = useCallback(async (rating: number) => {
    const targetPaper = currentPaperRef.current;
    if (!targetPaper || isActingRef.current) return;
    setIsActing(true);
    const paperId = targetPaper.arxiv_id;
    const prevIdx = currentIndexRef.current;
    const prevRating = targetPaper.rating;
    try {
      await api.ratePaper(paperId, rating);
      setLastAction({
        index: prevIdx,
        paperId,
        action: 'rate',
        previousRating: prevRating,
      });
      setCurrentIndex((prev) => prev + 1);
    } catch (err: any) {
      Alert.alert('Rating Error', err.message);
    } finally {
      setIsActing(false);
    }
  }, []);

  const handleUndo = async () => {
    if (!lastAction || isActing) return;
    setIsActing(true);
    try {
      if (lastAction.action === 'rate') {
        // Revert rating to unrated (or previous rating)
        await api.ratePaper(lastAction.paperId, lastAction.previousRating ?? 0);
        setCurrentIndex(lastAction.index);
        setLastAction(null);
      }
    } catch (err: any) {
      Alert.alert('Undo Error', err.message);
    } finally {
      setIsActing(false);
    }
  };

  const handleToggleReadingList = useCallback(async () => {
    const targetPaper = currentPaperRef.current;
    if (!targetPaper || isActingRef.current) return;
    setIsActing(true);
    const paperId = targetPaper.arxiv_id;
    const wasInReadingList = Boolean(targetPaper.in_reading_list);
    const curIdx = currentIndexRef.current;
    try {
      if (wasInReadingList) {
        await api.removeFromReadingList(paperId);
      } else {
        await api.addToReadingList(paperId);
      }
      setPapers((prev) =>
        prev.map((p, idx) =>
          idx === curIdx ? { ...p, in_reading_list: !wasInReadingList } : p
        )
      );
    } catch (err: any) {
      Alert.alert('Reading List Error', err.message);
    } finally {
      setIsActing(false);
    }
  }, []);

  const swipeCard = useCallback(
    (direction: 'left' | 'right' | 'up', onComplete: () => void) => {
      let toX = 0;
      let toY = 0;
      if (direction === 'right') toX = SCREEN_WIDTH + 80;
      else if (direction === 'left') toX = -SCREEN_WIDTH - 80;
      else if (direction === 'up') toY = -SCREEN_WIDTH;

      if (isTestEnv) {
        position.setValue({ x: 0, y: 0 });
        onComplete();
        return;
      }

      Animated.timing(position, {
        toValue: { x: toX, y: toY },
        duration: 180,
        useNativeDriver: false,
      }).start(() => {
        position.setValue({ x: 0, y: 0 });
        onComplete();
      });
    },
    [position]
  );

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => false,
        onMoveShouldSetPanResponder: (_, gesture) => {
          return Math.abs(gesture.dx) > 15 || gesture.dy < -25;
        },
        onPanResponderMove: (_, gesture) => {
          position.setValue({ x: gesture.dx, y: gesture.dy });
        },
        onPanResponderRelease: (_, gesture) => {
          if (isActingRef.current || !currentPaperRef.current) {
            Animated.spring(position, {
              toValue: { x: 0, y: 0 },
              friction: 5,
              useNativeDriver: false,
            }).start();
            return;
          }

          if (gesture.dx > SWIPE_THRESHOLD) {
            swipeCard('right', () => handleRate(1));
          } else if (gesture.dx < -SWIPE_THRESHOLD) {
            swipeCard('left', () => handleRate(-1));
          } else if (gesture.dy < -100) {
            swipeCard('up', () => handleToggleReadingList());
          } else {
            Animated.spring(position, {
              toValue: { x: 0, y: 0 },
              friction: 5,
              useNativeDriver: false,
            }).start();
          }
        },
      }),
    [position, swipeCard, handleRate, handleToggleReadingList]
  );

  const rotate = position.x.interpolate({
    inputRange: [-SCREEN_WIDTH * 1.5, 0, SCREEN_WIDTH * 1.5],
    outputRange: ['-14deg', '0deg', '14deg'],
  });

  const likeOpacity = position.x.interpolate({
    inputRange: [25, SCREEN_WIDTH / 4],
    outputRange: [0, 1],
    extrapolate: 'clamp',
  });

  const skipOpacity = position.x.interpolate({
    inputRange: [-SCREEN_WIDTH / 4, -25],
    outputRange: [1, 0],
    extrapolate: 'clamp',
  });

  const saveOpacity = position.y.interpolate({
    inputRange: [-SCREEN_WIDTH / 4, -25],
    outputRange: [1, 0],
    extrapolate: 'clamp',
  });

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
        <Text style={styles.loadingText}>Fetching recommended papers...</Text>
      </View>
    );
  }

  if (error) return <RecoveryView onRetry={loadPapers} onSettings={() => navigation.navigate('SettingsTab')} />;

  if (!currentPaper || currentIndex >= papers.length) {
    return (
      <View style={styles.centerContainer}>
        <Sparkles size={48} color={theme.colors.primaryLight} />
        <Text style={styles.emptyTitle}>You're All Caught Up!</Text>
        <Text style={styles.emptySubtitle}>
          No more unrated recommendations right now.
        </Text>
        <TouchableOpacity style={styles.refreshButton} onPress={() => loadPapers()}>
          <RefreshCw size={18} color={theme.colors.white} />
          <Text style={styles.refreshButtonText}>Refresh Deck</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const scorePercent = Math.round((currentPaper.score ?? 0.5) * 100);

  return (
    <View style={styles.container}>
      {/* Mode Selector */}
      <View style={styles.modeToggleContainer}>
        <TouchableOpacity
          style={[styles.modeToggleBtn, triageMode === 'recommended' && styles.modeToggleBtnActive]}
          onPress={() => {
            if (triageMode !== 'recommended') {
              setTriageMode('recommended');
              loadPapers('recommended');
            }
          }}
        >
          <Sparkles size={14} color={triageMode === 'recommended' ? '#ffffff' : theme.colors.textDim} />
          <Text style={[styles.modeToggleText, triageMode === 'recommended' && styles.modeToggleTextActive]}>
            Top Matches
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.modeToggleBtn, triageMode === 'explore' && styles.modeToggleBtnActive]}
          onPress={() => {
            if (triageMode !== 'explore') {
              setTriageMode('explore');
              loadPapers('explore');
            }
          }}
        >
          <Compass size={14} color={triageMode === 'explore' ? '#ffffff' : theme.colors.textDim} />
          <Text style={[styles.modeToggleText, triageMode === 'explore' && styles.modeToggleTextActive]}>
            Explore Boundary
          </Text>
        </TouchableOpacity>
      </View>

      {/* Progress header */}
      <View style={styles.progressContainer}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text style={styles.progressText}>
            Card {currentIndex + 1} of {papers.length}
          </Text>
          {lastAction && (
            <TouchableOpacity
              onPress={handleUndo}
              disabled={isActing}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 4,
                paddingHorizontal: 8,
                paddingVertical: 4,
                borderRadius: 6,
                backgroundColor: theme.colors.surface,
              }}
            >
              <RotateCcw size={14} color={theme.colors.primaryLight} />
              <Text style={{ fontSize: theme.typography.xs, color: theme.colors.primaryLight, fontWeight: '600' }}>
                Undo
              </Text>
            </TouchableOpacity>
          )}
        </View>
        <View style={styles.scoreBadge}>
          <Text style={styles.scoreText}>{scorePercent}% Match</Text>
        </View>
      </View>

      {/* Main card with gesture responder */}
      <Animated.View
        style={[
          styles.cardWrapper,
          position.getLayout(),
          { transform: [{ rotate }] },
        ]}
        {...panResponder.panHandlers}
      >
        {/* Swipe Feedback Badges */}
        <Animated.View
          style={[styles.swipeBadge, styles.likeBadge, { opacity: likeOpacity }]}
          pointerEvents="none"
        >
          <Text style={styles.likeBadgeText}>LIKE</Text>
        </Animated.View>
        <Animated.View
          style={[styles.swipeBadge, styles.skipBadge, { opacity: skipOpacity }]}
          pointerEvents="none"
        >
          <Text style={styles.skipBadgeText}>SKIP</Text>
        </Animated.View>
        <Animated.View
          style={[styles.swipeBadge, styles.saveBadge, { opacity: saveOpacity }]}
          pointerEvents="none"
        >
          <Text style={styles.saveBadgeText}>SAVE</Text>
        </Animated.View>

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
      </Animated.View>

      {/* Floating Action Controls */}
      <View style={styles.actionBar}>
        {/* Dislike / Skip */}
        <TouchableOpacity
          style={[styles.actionBtn, styles.dislikeBtn]}
          onPress={() => swipeCard('left', () => handleRate(-1))}
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
          accessibilityLabel={currentPaper.in_reading_list ? "Unsave paper" : "Save paper"}
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
          accessibilityLabel="Read paper details"
          onPress={() => navigation.navigate('PaperDetail', { arxivId: currentPaper.arxiv_id })}
        >
          <MessageSquare size={22} color={theme.colors.primaryLight} />
        </TouchableOpacity>

        {/* Like / Thumbs up */}
        <TouchableOpacity
          style={[styles.actionBtn, styles.likeBtn]}
          onPress={() => swipeCard('right', () => handleRate(1))}
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
  modeToggleContainer: {
    flexDirection: 'row',
    marginHorizontal: theme.spacing.lg,
    marginTop: theme.spacing.sm,
    marginBottom: theme.spacing.xs,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: 3,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
    gap: 4,
  },
  modeToggleBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 7,
    borderRadius: theme.borderRadius.sm,
    gap: 6,
  },
  modeToggleBtnActive: {
    backgroundColor: theme.colors.primary,
  },
  modeToggleText: {
    fontSize: theme.typography.xs,
    fontWeight: '600',
    color: theme.colors.textDim,
  },
  modeToggleTextActive: {
    color: '#ffffff',
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
  swipeBadge: {
    position: 'absolute',
    top: 24,
    zIndex: 10,
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 2,
  },
  likeBadge: {
    left: 24,
    borderColor: theme.colors.success,
    backgroundColor: 'rgba(16, 185, 129, 0.2)',
    transform: [{ rotate: '-15deg' }],
  },
  likeBadgeText: {
    color: theme.colors.success,
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  skipBadge: {
    right: 24,
    borderColor: theme.colors.danger,
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
    transform: [{ rotate: '15deg' }],
  },
  skipBadgeText: {
    color: theme.colors.danger,
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  saveBadge: {
    alignSelf: 'center',
    top: 36,
    borderColor: theme.colors.warning,
    backgroundColor: 'rgba(245, 158, 11, 0.2)',
  },
  saveBadgeText: {
    color: theme.colors.warning,
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
});
