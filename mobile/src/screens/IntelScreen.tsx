import React, { useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Modal,
} from 'react-native';
import {
  TrendingUp,
  Sparkles,
  Calendar,
  AlertTriangle,
  ChevronRight,
  X,
  Flame,
  Clock,
  BookOpen,
} from 'lucide-react-native';
import { theme } from '../constants/theme';
import { api } from '../api/client';
import { useFocusEffect } from '@react-navigation/native';
import { RecoveryView } from '../components/RecoveryView';
import { ResearchBrief, VelocityAlert, TrendsData } from '../types';

interface IntelScreenProps {
  navigation: any;
}

export const IntelScreen: React.FC<IntelScreenProps> = ({ navigation }) => {
  const requestId = useRef(0);
  const [activeTab, setActiveTab] = useState<'briefs' | 'trends'>('briefs');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<boolean>(false);

  // Briefs data
  const [briefs, setBriefs] = useState<ResearchBrief[]>([]);
  const [selectedBrief, setSelectedBrief] = useState<ResearchBrief | null>(null);
  const [isLoadingBriefDetail, setIsLoadingBriefDetail] = useState<boolean>(false);

  // Trends data
  const [trendsData, setTrendsData] = useState<TrendsData | null>(null);

  const loadData = useCallback(async () => {
    const id = ++requestId.current;
    setIsLoading(true);
    setError(false);
    try {
      if (activeTab === 'briefs') {
        const res = await api.getBriefs();
        if (id !== requestId.current) return;
        setBriefs(res.briefs || []);
      } else {
        const res = await api.getTrends();
        if (id !== requestId.current) return;
        setTrendsData(res);
      }
    } catch (e) {
      if (id === requestId.current) setError(true);
    } finally {
      if (id === requestId.current) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, [activeTab]);

  useFocusEffect(
    useCallback(() => {
      void loadData();
      return () => {
        requestId.current++;
      };
    }, [loadData])
  );

  const onRefresh = () => {
    setIsRefreshing(true);
    void loadData();
  };

  const handleOpenBrief = async (briefDate: string) => {
    setIsLoadingBriefDetail(true);
    try {
      const res = await api.getBrief(briefDate);
      setSelectedBrief(res.brief);
    } catch {
      // Fallback to local brief object if already in list
      const fallback = briefs.find((b) => b.date === briefDate) || null;
      setSelectedBrief(fallback);
    } finally {
      setIsLoadingBriefDetail(false);
    }
  };

  return (
    <View style={styles.container}>
      {/* Top Segmented Selector */}
      <View style={styles.segmentedContainer}>
        <TouchableOpacity
          style={[styles.segmentBtn, activeTab === 'briefs' && styles.segmentBtnActive]}
          onPress={() => setActiveTab('briefs')}
          activeOpacity={0.7}
        >
          <BookOpen
            size={16}
            color={activeTab === 'briefs' ? theme.colors.primaryLight : theme.colors.textDim}
          />
          <Text style={[styles.segmentText, activeTab === 'briefs' && styles.segmentTextActive]}>
            Weekly Briefs
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.segmentBtn, activeTab === 'trends' && styles.segmentBtnActive]}
          onPress={() => setActiveTab('trends')}
          activeOpacity={0.7}
        >
          <TrendingUp
            size={16}
            color={activeTab === 'trends' ? theme.colors.primaryLight : theme.colors.textDim}
          />
          <Text style={[styles.segmentText, activeTab === 'trends' && styles.segmentTextActive]}>
            Trend Radar
          </Text>
        </TouchableOpacity>
      </View>

      {isLoading && !isRefreshing ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading research intelligence...</Text>
        </View>
      ) : error ? (
        <RecoveryView
          message="Could not load intelligence data. Check server connectivity."
          onRetry={loadData}
        />
      ) : (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={onRefresh}
              tintColor={theme.colors.primary}
            />
          }
        >
          {activeTab === 'briefs' ? (
            briefs.length === 0 ? (
              <View style={styles.emptyContainer}>
                <Sparkles size={36} color={theme.colors.textDim} />
                <Text style={styles.emptyTitle}>No Briefs Generated Yet</Text>
                <Text style={styles.emptySubtitle}>
                  Weekly research briefs are automatically generated by the server and synthesise the
                  most significant papers in your monitored fields.
                </Text>
              </View>
            ) : (
              <View style={styles.listSection}>
                <Text style={styles.sectionHeader}>Archived Research Briefs</Text>
                {briefs.map((brief) => (
                  <TouchableOpacity
                    key={brief.date}
                    style={styles.briefCard}
                    onPress={() => handleOpenBrief(brief.date)}
                    activeOpacity={0.7}
                  >
                    <View style={styles.briefHeader}>
                      <View style={styles.briefDateRow}>
                        <Calendar size={14} color={theme.colors.primaryLight} />
                        <Text style={styles.briefDate}>Week of {brief.date}</Text>
                      </View>
                      <ChevronRight size={16} color={theme.colors.textDim} />
                    </View>
                    <Text style={styles.briefSnippet} numberOfLines={3}>
                      {brief.content.replace(/^#+.*$/gm, '').trim()}
                    </Text>
                    <Text style={styles.tapToRead}>Tap to read full brief &rarr;</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )
          ) : (
            <View style={styles.trendsSection}>
              {/* Velocity Spike Alerts */}
              {trendsData?.alerts && trendsData.alerts.length > 0 && (
                <View style={styles.alertBox}>
                  <View style={styles.alertBoxHeader}>
                    <Flame size={18} color="#f59e0b" />
                    <Text style={styles.alertBoxTitle}>Significant Topic Spikes (Last 48h)</Text>
                  </View>
                  {trendsData.alerts.map((alert, idx) => (
                    <View key={idx} style={styles.alertItem}>
                      <View style={styles.alertTagRow}>
                        <Text style={styles.alertTag}>{alert.tag}</Text>
                        <Text style={styles.alertMultiplier}>
                          {alert.spike_factor?.toFixed(1) || '2.0'}x velocity spike
                        </Text>
                      </View>
                      <Text style={styles.alertRateText}>
                        Current publication rate: {alert.current_rate} papers/week (baseline:{' '}
                        {alert.previous_weekly_rate})
                      </Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Upcoming Deadlines & Conferences */}
              {trendsData?.upcoming_events && trendsData.upcoming_events.length > 0 && (
                <View style={styles.cardSection}>
                  <View style={styles.sectionTitleRow}>
                    <Calendar size={18} color={theme.colors.primaryLight} />
                    <Text style={styles.sectionTitle}>Conferences & Deadlines</Text>
                  </View>
                  {trendsData.upcoming_events.map((ev) => (
                    <View key={ev.id} style={styles.eventItem}>
                      <View style={styles.eventMainRow}>
                        <Text style={styles.eventName}>{ev.name}</Text>
                        <View style={styles.eventTypeBadge}>
                          <Text style={styles.eventTypeText}>{ev.type}</Text>
                        </View>
                      </View>
                      <View style={styles.eventMetaRow}>
                        <Clock size={12} color={theme.colors.textDim} />
                        <Text style={styles.eventDate}>{ev.date}</Text>
                        {ev.notes ? (
                          <Text style={styles.eventNotes} numberOfLines={1}>
                            &bull; {ev.notes}
                          </Text>
                        ) : null}
                      </View>
                    </View>
                  ))}
                </View>
              )}

              {/* Topic Momentum & Summaries */}
              {trendsData?.trends && Object.keys(trendsData.trends).length > 0 && (
                <View style={styles.cardSection}>
                  <View style={styles.sectionTitleRow}>
                    <TrendingUp size={18} color={theme.colors.primaryLight} />
                    <Text style={styles.sectionTitle}>Monthly Topic Intelligence</Text>
                  </View>
                  {Object.entries(trendsData.trends).map(([topic, data]: [string, any]) => {
                    const summaryText = typeof data === 'string' ? data : data?.summary || '';
                    return (
                      <View key={topic} style={styles.topicCard}>
                        <Text style={styles.topicName}>{topic.replace(/_/g, ' ').toUpperCase()}</Text>
                        {summaryText ? (
                          <Text style={styles.topicSummary}>{summaryText}</Text>
                        ) : (
                          <Text style={styles.topicEmpty}>
                            Analyzing recent arXiv publications for this topic...
                          </Text>
                        )}
                      </View>
                    );
                  })}
                </View>
              )}
            </View>
          )}
        </ScrollView>
      )}

      {/* Full Brief Reader Modal */}
      <Modal
        visible={!!selectedBrief}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setSelectedBrief(null)}
      >
        <View style={styles.modalContainer}>
          <View style={styles.modalHeader}>
            <View style={styles.modalTitleBlock}>
              <Text style={styles.modalHeading}>Weekly Research Brief</Text>
              <Text style={styles.modalSubheading}>Week of {selectedBrief?.date}</Text>
            </View>
            <TouchableOpacity
              onPress={() => setSelectedBrief(null)}
              style={styles.closeBtn}
              activeOpacity={0.7}
            >
              <X size={20} color={theme.colors.text} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalScroll} contentContainerStyle={styles.modalScrollContent}>
            {isLoadingBriefDetail ? (
              <ActivityIndicator size="large" color={theme.colors.primary} />
            ) : (
              <Text style={styles.briefFullContent}>{selectedBrief?.content}</Text>
            )}
          </ScrollView>
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
  segmentedContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: theme.colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.surfaceBorder,
    gap: 10,
  },
  segmentBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: 'transparent',
  },
  segmentBtnActive: {
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(99, 102, 241, 0.4)',
  },
  segmentText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.sm,
    fontWeight: '600',
  },
  segmentTextActive: {
    color: theme.colors.primaryLight,
    fontWeight: '700',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  loadingText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.sm,
    marginTop: 12,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  sectionHeader: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 12,
  },
  listSection: {
    gap: 12,
  },
  briefCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
    marginBottom: 12,
  },
  briefHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  briefDateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  briefDate: {
    color: theme.colors.text,
    fontSize: theme.typography.md,
    fontWeight: '700',
  },
  briefSnippet: {
    color: theme.colors.textDim,
    fontSize: theme.typography.sm,
    lineHeight: 20,
    marginBottom: 10,
  },
  tapToRead: {
    color: theme.colors.primaryLight,
    fontSize: theme.typography.xs,
    fontWeight: '600',
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
    paddingHorizontal: 24,
  },
  emptyTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.lg,
    fontWeight: '700',
    marginTop: 16,
    marginBottom: 8,
  },
  emptySubtitle: {
    color: theme.colors.textDim,
    fontSize: theme.typography.sm,
    textAlign: 'center',
    lineHeight: 20,
  },
  trendsSection: {
    gap: 16,
  },
  alertBox: {
    backgroundColor: 'rgba(245, 158, 11, 0.1)',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.3)',
  },
  alertBoxHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  alertBoxTitle: {
    color: '#f59e0b',
    fontSize: theme.typography.sm,
    fontWeight: '700',
  },
  alertItem: {
    marginBottom: 10,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(245, 158, 11, 0.15)',
  },
  alertTagRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  alertTag: {
    color: theme.colors.text,
    fontSize: theme.typography.sm,
    fontWeight: '700',
  },
  alertMultiplier: {
    color: '#f59e0b',
    fontSize: theme.typography.xs,
    fontWeight: '700',
    backgroundColor: 'rgba(245, 158, 11, 0.2)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  alertRateText: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
  },
  cardSection: {
    backgroundColor: theme.colors.surface,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
    gap: 12,
  },
  sectionTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  sectionTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.md,
    fontWeight: '700',
  },
  eventItem: {
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.surfaceBorder,
  },
  eventMainRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  eventName: {
    color: theme.colors.text,
    fontSize: theme.typography.sm,
    fontWeight: '600',
    flex: 1,
    marginRight: 8,
  },
  eventTypeBadge: {
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  eventTypeText: {
    color: theme.colors.primaryLight,
    fontSize: 10,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  eventMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  eventDate: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
  },
  eventNotes: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
    flex: 1,
  },
  topicCard: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.surfaceBorder,
  },
  topicName: {
    color: theme.colors.primaryLight,
    fontSize: theme.typography.xs,
    fontWeight: '700',
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  topicSummary: {
    color: theme.colors.text,
    fontSize: theme.typography.sm,
    lineHeight: 20,
  },
  topicEmpty: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
    fontStyle: 'italic',
  },
  modalContainer: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.surfaceBorder,
    backgroundColor: theme.colors.surface,
  },
  modalTitleBlock: {
    flex: 1,
  },
  modalHeading: {
    color: theme.colors.text,
    fontSize: theme.typography.lg,
    fontWeight: '700',
  },
  modalSubheading: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
    marginTop: 2,
  },
  closeBtn: {
    padding: 8,
    borderRadius: 8,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
  },
  modalScroll: {
    flex: 1,
  },
  modalScrollContent: {
    padding: 20,
    paddingBottom: 60,
  },
  briefFullContent: {
    color: theme.colors.text,
    fontSize: theme.typography.md,
    lineHeight: 26,
  },
});
