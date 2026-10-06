import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  TextInput,
  Modal,
  Alert,
} from 'react-native';
import {
  BookOpen,
  Plus,
  RefreshCw,
  Trash2,
  Award,
  Bell,
  X,
  ExternalLink,
} from 'lucide-react-native';
import { theme } from '../constants/theme';
import { api } from '../api/client';
import { MyPaper, CitationEvent } from '../types';

interface MyPapersScreenProps {
  navigation: any;
}

export const MyPapersScreen: React.FC<MyPapersScreenProps> = ({ navigation }) => {
  const [papers, setPapers] = useState<MyPaper[]>([]);
  const [citationEvents, setCitationEvents] = useState<CitationEvent[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [isRefreshingCitations, setIsRefreshingCitations] = useState<boolean>(false);

  // Add Paper Modal state
  const [isAddModalVisible, setIsAddModalVisible] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>('');
  const [newArxivId, setNewArxivId] = useState<string>('');
  const [newDoi, setNewDoi] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const fetchData = useCallback(async () => {
    try {
      const [papersRes, eventsRes] = await Promise.all([
        api.getMyPapers(),
        api.getCitationEvents(5),
      ]);
      setPapers(papersRes.papers || []);
      setCitationEvents(eventsRes.events || []);
    } catch (err: any) {
      console.warn('Failed to fetch My Papers data:', err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const onRefresh = () => {
    setIsRefreshing(true);
    fetchData();
  };

  const handleRefreshCitations = async () => {
    setIsRefreshingCitations(true);
    try {
      await api.refreshMyPapersCitations();
      Alert.alert('Citation Refresh', 'Citation counts have been updated.');
      fetchData();
    } catch (e: any) {
      Alert.alert('Refresh Error', e.message || 'Failed to refresh citations.');
    } finally {
      setIsRefreshingCitations(false);
    }
  };

  const handleAddPaper = async () => {
    const title = newTitle.trim();
    if (!title) {
      Alert.alert('Validation', 'Please provide a publication title.');
      return;
    }
    setIsSubmitting(true);
    try {
      await api.addMyPaper({
        title,
        arxiv_id: newArxivId.trim() || undefined,
        doi: newDoi.trim() || undefined,
      });
      setIsAddModalVisible(false);
      setNewTitle('');
      setNewArxivId('');
      setNewDoi('');
      Alert.alert('Success', 'Publication registered for citation tracking.');
      fetchData();
    } catch (e: any) {
      Alert.alert('Registration Error', e.message || 'Failed to add paper.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeletePaper = (paper: MyPaper) => {
    Alert.alert(
      'Remove Publication',
      `Stop tracking citations for "${paper.title}"?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.deleteMyPaper(paper.id);
              setPapers((prev) => prev.filter((p) => p.id !== paper.id));
            } catch (e: any) {
              Alert.alert('Error', e.message || 'Failed to remove publication.');
            }
          },
        },
      ]
    );
  };

  const totalCitations = papers.reduce((acc, p) => acc + (p.citation_count || 0), 0);

  const renderHeader = () => (
    <View style={styles.headerContainer}>
      {/* Overview Stat Card */}
      <View style={styles.statsCard}>
        <View style={styles.statItem}>
          <Text style={styles.statValue}>{papers.length}</Text>
          <Text style={styles.statLabel}>Tracked Works</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.statItem}>
          <Text style={[styles.statValue, { color: theme.colors.warning }]}>{totalCitations}</Text>
          <Text style={styles.statLabel}>Total Citations</Text>
        </View>
      </View>

      {/* Action Buttons */}
      <View style={styles.actionBar}>
        <TouchableOpacity
          style={[styles.btn, styles.primaryBtn]}
          onPress={() => setIsAddModalVisible(true)}
        >
          <Plus size={16} color={theme.colors.white} />
          <Text style={styles.primaryBtnText}>Track Publication</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, styles.secondaryBtn]}
          onPress={handleRefreshCitations}
          disabled={isRefreshingCitations}
        >
          {isRefreshingCitations ? (
            <ActivityIndicator size="small" color={theme.colors.text} />
          ) : (
            <>
              <RefreshCw size={15} color={theme.colors.textSecondary} />
              <Text style={styles.secondaryBtnText}>Update Citations</Text>
            </>
          )}
        </TouchableOpacity>
      </View>

      {/* Recent Citation Events Alert Banner */}
      {citationEvents.length > 0 && (
        <View style={styles.eventsBanner}>
          <View style={styles.eventsHeader}>
            <Bell size={16} color="#f59e0b" />
            <Text style={styles.eventsTitle}>Recent Citation Alerts</Text>
          </View>
          {citationEvents.map((ev) => (
            <View key={ev.id} style={styles.eventRow}>
              <View style={styles.eventDot} />
              <View style={styles.eventDetails}>
                <Text style={styles.eventPaperTitle} numberOfLines={1}>
                  {ev.citing_title || `Paper ${ev.citing_arxiv_id}`}
                </Text>
                <Text style={styles.eventSubtitle}>
                  cited {ev.my_paper_title} • {new Date(ev.detected_at).toLocaleDateString()}
                </Text>
              </View>
            </View>
          ))}
        </View>
      )}

      <Text style={styles.sectionHeader}>Registered Publications</Text>
    </View>
  );

  const renderItem = ({ item }: { item: MyPaper }) => (
    <View style={styles.card}>
      <View style={styles.cardContent}>
        <Text style={styles.paperTitle}>{item.title}</Text>

        <View style={styles.identifierRow}>
          {item.arxiv_id ? (
            <View style={styles.idBadge}>
              <Text style={styles.idBadgeText}>arXiv: {item.arxiv_id}</Text>
            </View>
          ) : null}
          {item.doi ? (
            <View style={styles.idBadge}>
              <Text style={styles.idBadgeText}>DOI: {item.doi}</Text>
            </View>
          ) : null}
        </View>
      </View>

      <View style={styles.cardFooter}>
        <View style={styles.citationBadge}>
          <Award size={14} color="#f59e0b" />
          <Text style={styles.citationBadgeText}>
            {item.citation_count} {item.citation_count === 1 ? 'citation' : 'citations'}
          </Text>
        </View>

        <TouchableOpacity
          style={styles.deleteButton}
          onPress={() => handleDeletePaper(item)}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        >
          <Trash2 size={16} color={theme.colors.textMuted} />
        </TouchableOpacity>
      </View>
    </View>
  );

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={papers}
        keyExtractor={(item) => item.id.toString()}
        renderItem={renderItem}
        ListHeaderComponent={renderHeader}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <BookOpen size={48} color={theme.colors.textDim} />
            <Text style={styles.emptyTitle}>No Publications Tracked</Text>
            <Text style={styles.emptySubtitle}>
              Register your papers to monitor incoming citations and automatically ingest citing works into your feed.
            </Text>
          </View>
        }
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={onRefresh}
            tintColor={theme.colors.primaryLight}
          />
        }
      />

      {/* Add Publication Modal */}
      <Modal
        visible={isAddModalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setIsAddModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Track New Publication</Text>
              <TouchableOpacity onPress={() => setIsAddModalVisible(false)}>
                <X size={20} color={theme.colors.textMuted} />
              </TouchableOpacity>
            </View>

            <Text style={styles.inputLabel}>Paper Title *</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="e.g., Deep Learning for Cosmological Surveys"
              placeholderTextColor={theme.colors.textDim}
              value={newTitle}
              onChangeText={setNewTitle}
            />

            <Text style={styles.inputLabel}>arXiv Identifier (Optional)</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="e.g., 2301.12345"
              placeholderTextColor={theme.colors.textDim}
              value={newArxivId}
              onChangeText={setNewArxivId}
              autoCapitalize="none"
            />

            <Text style={styles.inputLabel}>DOI (Optional)</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="e.g., 10.1038/s41586-021-03819-2"
              placeholderTextColor={theme.colors.textDim}
              value={newDoi}
              onChangeText={setNewDoi}
              autoCapitalize="none"
            />

            <TouchableOpacity
              style={[
                styles.modalSubmitBtn,
                (!newTitle.trim() || isSubmitting) && styles.modalSubmitBtnDisabled,
              ]}
              onPress={handleAddPaper}
              disabled={!newTitle.trim() || isSubmitting}
            >
              {isSubmitting ? (
                <ActivityIndicator size="small" color={theme.colors.white} />
              ) : (
                <Text style={styles.modalSubmitBtnText}>Register Publication</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
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
    backgroundColor: theme.colors.background,
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    padding: theme.spacing.md,
    paddingBottom: theme.spacing.xl * 2,
  },
  headerContainer: {
    marginBottom: theme.spacing.md,
  },
  statsCard: {
    flexDirection: 'row',
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
  },
  statDivider: {
    width: 1,
    backgroundColor: theme.colors.surfaceBorder,
    marginVertical: 4,
  },
  statValue: {
    color: theme.colors.text,
    fontSize: theme.typography.xxl,
    fontWeight: '700',
  },
  statLabel: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.xs,
    marginTop: 2,
    fontWeight: '500',
  },
  actionBar: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginBottom: theme.spacing.md,
  },
  btn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
    borderRadius: theme.borderRadius.sm,
    gap: 6,
  },
  primaryBtn: {
    backgroundColor: theme.colors.primary,
  },
  primaryBtnText: {
    color: theme.colors.white,
    fontSize: theme.typography.sm,
    fontWeight: '600',
  },
  secondaryBtn: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  secondaryBtnText: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.sm,
    fontWeight: '600',
  },
  eventsBanner: {
    backgroundColor: 'rgba(245, 158, 11, 0.08)',
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    borderLeftWidth: 3,
    borderLeftColor: '#f59e0b',
    marginBottom: theme.spacing.md,
  },
  eventsHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 8,
  },
  eventsTitle: {
    color: '#f59e0b',
    fontSize: theme.typography.sm,
    fontWeight: '700',
  },
  eventRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginTop: 6,
    gap: 8,
  },
  eventDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#f59e0b',
    marginTop: 6,
  },
  eventDetails: {
    flex: 1,
  },
  eventPaperTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.xs,
    fontWeight: '600',
  },
  eventSubtitle: {
    color: theme.colors.textMuted,
    fontSize: 11,
    marginTop: 1,
  },
  sectionHeader: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.xs,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: theme.spacing.xs,
    marginBottom: theme.spacing.xs,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  cardContent: {
    marginBottom: theme.spacing.sm,
  },
  paperTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.md,
    fontWeight: '600',
    lineHeight: 22,
    marginBottom: 6,
  },
  identifierRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  idBadge: {
    backgroundColor: theme.colors.surfaceLight,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  idBadgeText: {
    color: theme.colors.textSecondary,
    fontSize: 11,
    fontWeight: '500',
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: theme.spacing.xs,
    borderTopWidth: 1,
    borderTopColor: theme.colors.surfaceBorder,
  },
  citationBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  citationBadgeText: {
    color: '#f59e0b',
    fontSize: theme.typography.xs,
    fontWeight: '700',
  },
  deleteButton: {
    padding: 6,
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: theme.spacing.xl * 2,
    paddingHorizontal: theme.spacing.lg,
  },
  emptyTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.lg,
    fontWeight: '700',
    marginTop: theme.spacing.md,
    marginBottom: theme.spacing.xs,
  },
  emptySubtitle: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.sm,
    textAlign: 'center',
    lineHeight: 20,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.lg,
  },
  modalContent: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.lg,
    width: '100%',
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.md,
  },
  modalTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.lg,
    fontWeight: '700',
  },
  inputLabel: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.xs,
    fontWeight: '600',
    marginBottom: 4,
    marginTop: 8,
  },
  modalInput: {
    backgroundColor: theme.colors.background,
    color: theme.colors.text,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
    fontSize: theme.typography.sm,
  },
  modalSubmitBtn: {
    backgroundColor: theme.colors.primary,
    paddingVertical: 10,
    borderRadius: theme.borderRadius.sm,
    alignItems: 'center',
    marginTop: theme.spacing.lg,
  },
  modalSubmitBtnDisabled: {
    opacity: 0.5,
  },
  modalSubmitBtnText: {
    color: theme.colors.white,
    fontSize: theme.typography.sm,
    fontWeight: '600',
  },
});
