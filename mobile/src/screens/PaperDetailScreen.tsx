import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Linking,
  Alert,
} from 'react-native';
import {
  Sparkles,
  ExternalLink,
  Bookmark,
  ThumbsUp,
  ThumbsDown,
  Send,
  FileText,
  MessageSquare,
  StickyNote,
} from 'lucide-react-native';
import { theme } from '../constants/theme';
import { api } from '../api/client';
import { Paper, Note } from '../types';

interface PaperDetailScreenProps {
  route: any;
  navigation: any;
}

export const PaperDetailScreen: React.FC<PaperDetailScreenProps> = ({ route, navigation }) => {
  const { arxivId } = route.params;
  const [paper, setPaper] = useState<Paper | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Q&A state
  const [question, setQuestion] = useState<string>('');
  const [qaHistory, setQaHistory] = useState<{ q: string; a: string }[]>([]);
  const [isAsking, setIsAsking] = useState<boolean>(false);

  // Note state
  const [newNote, setNewNote] = useState<string>('');
  const [isSavingNote, setIsSavingNote] = useState<boolean>(false);

  const loadPaper = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await api.getPaper(arxivId);
      setPaper(data);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to fetch paper details');
    } finally {
      setIsLoading(false);
    }
  }, [arxivId]);

  useEffect(() => {
    loadPaper();
  }, [loadPaper]);

  const handleRate = async (rating: number) => {
    if (!paper) return;
    try {
      await api.ratePaper(paper.arxiv_id, rating);
      setPaper({ ...paper, rating });
    } catch (e: any) {
      Alert.alert('Rate Error', e.message);
    }
  };

  const handleToggleReadingList = async () => {
    if (!paper) return;
    try {
      if (paper.in_reading_list) {
        await api.removeFromReadingList(paper.arxiv_id);
        setPaper({ ...paper, in_reading_list: false });
      } else {
        await api.addToReadingList(paper.arxiv_id);
        setPaper({ ...paper, in_reading_list: true });
      }
    } catch (e: any) {
      Alert.alert('Reading List Error', e.message);
    }
  };

  const handleAsk = async () => {
    const q = question.trim();
    if (!q || !paper || isAsking) return;
    setIsAsking(true);
    setQuestion('');
    try {
      const res = await api.askPaper(paper.arxiv_id, q);
      setQaHistory((prev) => [...prev, { q, a: res.answer }]);
    } catch (err: any) {
      Alert.alert('Q&A Error', err.message || 'Failed to get answer');
    } finally {
      setIsAsking(false);
    }
  };

  const openUrl = (url: string) => {
    Linking.openURL(url).catch((e) => console.warn('Could not open link:', e));
  };

  if (isLoading || !paper) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  }

  const arxivUrl = `https://arxiv.org/abs/${paper.arxiv_id}`;
  const pdfUrl = `https://arxiv.org/pdf/${paper.arxiv_id}.pdf`;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header bar */}
      <View style={styles.headerBar}>
        <View style={styles.badgeRow}>
          {(paper.categories || []).map((cat, i) => (
            <View key={i} style={styles.categoryBadge}>
              <Text style={styles.categoryText}>{cat}</Text>
            </View>
          ))}
          {paper.cites_user_work && (
            <View style={[styles.categoryBadge, styles.citesBadge]}>
              <Text style={styles.citesText}>Cites Your Work</Text>
            </View>
          )}
        </View>

        <View style={styles.quickActions}>
          <TouchableOpacity
            style={[styles.iconButton, paper.rating === 1 && styles.iconActiveSuccess]}
            onPress={() => handleRate(1)}
          >
            <ThumbsUp
              size={20}
              color={paper.rating === 1 ? theme.colors.success : theme.colors.textMuted}
            />
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.iconButton, paper.rating === 0 && styles.iconActiveDanger]}
            onPress={() => handleRate(-1)}
          >
            <ThumbsDown
              size={20}
              color={paper.rating === 0 ? theme.colors.danger : theme.colors.textMuted}
            />
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.iconButton, paper.in_reading_list && styles.iconActiveWarning]}
            onPress={handleToggleReadingList}
          >
            <Bookmark
              size={20}
              color={paper.in_reading_list ? theme.colors.warning : theme.colors.textMuted}
            />
          </TouchableOpacity>
        </View>
      </View>

      {/* Title */}
      <Text style={styles.title}>{paper.title}</Text>

      {/* Authors */}
      <Text style={styles.authors}>{(paper.authors || []).join(', ')}</Text>

      {/* External Links */}
      <View style={styles.linksRow}>
        <TouchableOpacity style={styles.linkButton} onPress={() => openUrl(pdfUrl)}>
          <FileText size={16} color={theme.colors.primaryLight} />
          <Text style={styles.linkButtonText}>PDF</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.linkButton} onPress={() => openUrl(arxivUrl)}>
          <ExternalLink size={16} color={theme.colors.textMuted} />
          <Text style={styles.linkButtonText}>arXiv</Text>
        </TouchableOpacity>
      </View>

      {/* AI Summary */}
      {paper.summary && (
        <View style={styles.summarySection}>
          <View style={styles.sectionHeader}>
            <Sparkles size={16} color={theme.colors.primaryLight} />
            <Text style={styles.sectionTitle}>AI Summary</Text>
          </View>
          <Text style={styles.summaryText}>{paper.summary}</Text>
        </View>
      )}

      {/* Abstract */}
      <View style={styles.abstractSection}>
        <Text style={styles.sectionTitlePlain}>Abstract</Text>
        <Text style={styles.abstractText}>{paper.abstract}</Text>
      </View>

      {/* Interactive Paper Q&A */}
      <View style={styles.qaSection}>
        <View style={styles.sectionHeader}>
          <MessageSquare size={16} color={theme.colors.primaryLight} />
          <Text style={styles.sectionTitle}>Ask Paper (AI Q&A)</Text>
        </View>

        {qaHistory.map((item, idx) => (
          <View key={idx} style={styles.qaBubble}>
            <Text style={styles.qText}>Q: {item.q}</Text>
            <Text style={styles.aText}>{item.a}</Text>
          </View>
        ))}

        <View style={styles.askInputRow}>
          <TextInput
            style={styles.askInput}
            placeholder="Ask a question about this paper..."
            placeholderTextColor={theme.colors.textDim}
            value={question}
            onChangeText={setQuestion}
            multiline
          />
          <TouchableOpacity
            style={[styles.sendButton, (!question.trim() || isAsking) && styles.sendButtonDisabled]}
            onPress={handleAsk}
            disabled={!question.trim() || isAsking}
          >
            {isAsking ? (
              <ActivityIndicator size="small" color={theme.colors.white} />
            ) : (
              <Send size={16} color={theme.colors.white} />
            )}
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  content: {
    padding: theme.spacing.lg,
    paddingBottom: theme.spacing.xl * 2,
  },
  centerContainer: {
    flex: 1,
    backgroundColor: theme.colors.background,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.md,
  },
  badgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    flex: 1,
  },
  categoryBadge: {
    backgroundColor: theme.colors.surface,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  categoryText: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.xs,
    fontWeight: '600',
  },
  citesBadge: {
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    borderColor: 'rgba(245, 158, 11, 0.3)',
  },
  citesText: {
    color: '#f59e0b',
    fontSize: theme.typography.xs,
    fontWeight: '700',
  },
  quickActions: {
    flexDirection: 'row',
    gap: 8,
  },
  iconButton: {
    padding: 8,
    borderRadius: theme.borderRadius.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  iconActiveSuccess: {
    backgroundColor: 'rgba(16, 185, 129, 0.2)',
    borderColor: theme.colors.success,
  },
  iconActiveDanger: {
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
    borderColor: theme.colors.danger,
  },
  iconActiveWarning: {
    backgroundColor: 'rgba(245, 158, 11, 0.2)',
    borderColor: theme.colors.warning,
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
    lineHeight: 20,
    marginBottom: theme.spacing.md,
  },
  linksRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.lg,
  },
  linkButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: theme.colors.surface,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  linkButtonText: {
    color: theme.colors.text,
    fontSize: theme.typography.sm,
    fontWeight: '600',
  },
  summarySection: {
    backgroundColor: 'rgba(99, 102, 241, 0.08)',
    borderLeftWidth: 3,
    borderLeftColor: theme.colors.primary,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.lg,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  sectionTitle: {
    color: theme.colors.primaryLight,
    fontWeight: '700',
    fontSize: theme.typography.sm,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  sectionTitlePlain: {
    color: theme.colors.textMuted,
    fontWeight: '700',
    fontSize: theme.typography.sm,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  summaryText: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.sm,
    lineHeight: 22,
  },
  abstractSection: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.lg,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  abstractText: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.sm,
    lineHeight: 22,
  },
  qaSection: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  qaBubble: {
    backgroundColor: theme.colors.surfaceLight,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  qText: {
    color: theme.colors.primaryLight,
    fontSize: theme.typography.xs,
    fontWeight: '700',
    marginBottom: 4,
  },
  aText: {
    color: theme.colors.text,
    fontSize: theme.typography.sm,
    lineHeight: 20,
  },
  askInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: theme.spacing.sm,
  },
  askInput: {
    flex: 1,
    backgroundColor: theme.colors.background,
    color: theme.colors.text,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
    fontSize: theme.typography.sm,
    maxHeight: 80,
  },
  sendButton: {
    backgroundColor: theme.colors.primary,
    padding: 12,
    borderRadius: theme.borderRadius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    opacity: 0.4,
  },
});
