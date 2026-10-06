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
  Modal,
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
  FolderPlus,
  Trash2,
  X,
  Check,
} from 'lucide-react-native';
import { theme } from '../constants/theme';
import { api } from '../api/client';
import { Paper, Note, Collection } from '../types';

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

  // Notes state
  const [notes, setNotes] = useState<Note[]>([]);
  const [newNote, setNewNote] = useState<string>('');
  const [noteType, setNoteType] = useState<string>('general');
  const [isSavingNote, setIsSavingNote] = useState<boolean>(false);

  // Collections state
  const [collections, setCollections] = useState<Collection[]>([]);
  const [isCollectionModalVisible, setIsCollectionModalVisible] = useState<boolean>(false);

  const loadNotes = useCallback(async () => {
    try {
      const data = await api.getPaperNotes(arxivId);
      setNotes(data.notes || []);
    } catch (e) {
      console.warn('Failed to load paper notes:', e);
    }
  }, [arxivId]);

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
    loadNotes();
  }, [loadPaper, loadNotes]);

  const handleRate = async (rating: number) => {
    if (!paper) return;
    try {
      const res = await api.ratePaper(paper.arxiv_id, rating);
      setPaper({ ...paper, rating });
      if (res.status === 'queued_offline') {
        Alert.alert('Offline Mode', 'Your rating was saved offline and will sync when connected.');
      }
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

  const handleSaveNote = async () => {
    const text = newNote.trim();
    if (!text || isSavingNote) return;
    setIsSavingNote(true);
    try {
      const res = await api.addPaperNote(arxivId, text, noteType);
      setNewNote('');
      if (res.status === 'queued_offline') {
        Alert.alert('Offline Mode', 'Note queued offline. It will be saved upon reconnect.');
      }
      loadNotes();
    } catch (e: any) {
      Alert.alert('Note Error', e.message || 'Failed to save note');
    } finally {
      setIsSavingNote(false);
    }
  };

  const handleDeleteNote = async (noteId: number) => {
    try {
      await api.deletePaperNote(noteId);
      setNotes((prev) => prev.filter((n) => n.id !== noteId));
    } catch (e: any) {
      Alert.alert('Error', e.message || 'Failed to delete note');
    }
  };

  const openCollectionPicker = async () => {
    try {
      const list = await api.getCollections();
      setCollections(list || []);
      setIsCollectionModalVisible(true);
    } catch (e: any) {
      Alert.alert('Collections Error', e.message || 'Failed to load collections');
    }
  };

  const handleAddToCollection = async (collectionId: number) => {
    try {
      await api.addPaperToCollection(collectionId, arxivId);
      setIsCollectionModalVisible(false);
      Alert.alert('Saved', 'Paper added to collection successfully');
      loadPaper();
    } catch (e: any) {
      Alert.alert('Collection Error', e.message || 'Failed to add to collection');
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

        <TouchableOpacity style={styles.linkButton} onPress={openCollectionPicker}>
          <FolderPlus size={16} color={theme.colors.warning} />
          <Text style={styles.linkButtonText}>Collection</Text>
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

      {/* Research Notes */}
      <View style={styles.notesSection}>
        <View style={styles.sectionHeader}>
          <StickyNote size={16} color={theme.colors.primaryLight} />
          <Text style={styles.sectionTitle}>Research Notes ({notes.length})</Text>
        </View>

        {notes.length === 0 ? (
          <Text style={styles.emptyNotesText}>
            No research notes yet. Add your reflections, critiques, or ideas below.
          </Text>
        ) : (
          notes.map((note) => {
            const raw = note.content || '';
            let displayType = note.note_type || 'general';
            let displayContent = raw;
            const match = raw.match(/^\[(critique|idea|summary)\]\s*(.*)$/i);
            if (match) {
              displayType = match[1].toLowerCase();
              displayContent = match[2];
            }

            return (
              <View key={note.id} style={styles.noteCard}>
                <View style={styles.noteHeader}>
                  <View
                    style={[
                      styles.noteTypeBadge,
                      getNoteTypeBadgeStyle(displayType),
                    ]}
                  >
                    <Text style={styles.noteTypeText}>{displayType.toUpperCase()}</Text>
                  </View>
                  <TouchableOpacity
                    style={styles.deleteNoteBtn}
                    onPress={() => handleDeleteNote(note.id)}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  >
                    <Trash2 size={15} color={theme.colors.textMuted} />
                  </TouchableOpacity>
                </View>
                <Text style={styles.noteContentText}>{displayContent}</Text>
                {note.created_at ? (
                  <Text style={styles.noteDateText}>
                    {new Date(note.created_at).toLocaleDateString()}
                  </Text>
                ) : null}
              </View>
            );
          })
        )}

        {/* Add Note Form */}
        <View style={styles.addNoteContainer}>
          <Text style={styles.addNoteLabel}>Add a Note</Text>
          <View style={styles.noteTypeSelector}>
            {(['general', 'critique', 'idea', 'summary'] as const).map((type) => (
              <TouchableOpacity
                key={type}
                style={[
                  styles.noteTypePill,
                  noteType === type && styles.noteTypePillActive,
                ]}
                onPress={() => setNoteType(type)}
              >
                <Text
                  style={[
                    styles.noteTypePillText,
                    noteType === type && styles.noteTypePillTextActive,
                  ]}
                >
                  {type.charAt(0).toUpperCase() + type.slice(1)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          <TextInput
            style={styles.noteInput}
            placeholder={`Write a ${noteType} note...`}
            placeholderTextColor={theme.colors.textDim}
            value={newNote}
            onChangeText={setNewNote}
            multiline
            numberOfLines={3}
          />
          <TouchableOpacity
            style={[
              styles.saveNoteBtn,
              (!newNote.trim() || isSavingNote) && styles.saveNoteBtnDisabled,
            ]}
            onPress={handleSaveNote}
            disabled={!newNote.trim() || isSavingNote}
          >
            {isSavingNote ? (
              <ActivityIndicator size="small" color={theme.colors.white} />
            ) : (
              <Text style={styles.saveNoteBtnText}>Save Note</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {/* Add to Collection Modal */}
      <Modal
        visible={isCollectionModalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setIsCollectionModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Add to Collection</Text>
              <TouchableOpacity onPress={() => setIsCollectionModalVisible(false)}>
                <X size={20} color={theme.colors.textMuted} />
              </TouchableOpacity>
            </View>

            {collections.length === 0 ? (
              <Text style={styles.modalEmptyText}>
                No collections available. Create one in the web application.
              </Text>
            ) : (
              <ScrollView style={styles.modalScroll}>
                {collections.map((col) => (
                  <TouchableOpacity
                    key={col.id}
                    style={styles.collectionItem}
                    onPress={() => handleAddToCollection(col.id)}
                  >
                    <View style={styles.collectionInfo}>
                      <Text style={styles.collectionName}>{col.name}</Text>
                      {col.description ? (
                        <Text style={styles.collectionDesc} numberOfLines={1}>
                          {col.description}
                        </Text>
                      ) : null}
                    </View>
                    <FolderPlus size={18} color={theme.colors.primary} />
                  </TouchableOpacity>
                ))}
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
};

const getNoteTypeBadgeStyle = (type: string) => {
  switch (type) {
    case 'critique':
      return styles.noteType_critique;
    case 'idea':
      return styles.noteType_idea;
    case 'summary':
      return styles.noteType_summary;
    default:
      return styles.noteType_general;
  }
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
  notesSection: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
    marginTop: theme.spacing.lg,
  },
  emptyNotesText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.sm,
    fontStyle: 'italic',
    marginVertical: theme.spacing.sm,
  },
  noteCard: {
    backgroundColor: theme.colors.surfaceLight,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  noteHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  noteTypeBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  noteType_general: {
    backgroundColor: 'rgba(148, 163, 184, 0.2)',
  },
  noteType_critique: {
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
  },
  noteType_idea: {
    backgroundColor: 'rgba(245, 158, 11, 0.2)',
  },
  noteType_summary: {
    backgroundColor: 'rgba(59, 130, 246, 0.2)',
  },
  noteTypeText: {
    fontSize: 10,
    fontWeight: '700',
    color: theme.colors.text,
  },
  deleteNoteBtn: {
    padding: 4,
  },
  noteContentText: {
    color: theme.colors.text,
    fontSize: theme.typography.sm,
    lineHeight: 20,
  },
  noteDateText: {
    color: theme.colors.textDim,
    fontSize: 11,
    marginTop: 4,
  },
  addNoteContainer: {
    marginTop: theme.spacing.md,
    paddingTop: theme.spacing.md,
    borderTopWidth: 1,
    borderTopColor: theme.colors.surfaceBorder,
  },
  addNoteLabel: {
    color: theme.colors.text,
    fontSize: theme.typography.sm,
    fontWeight: '600',
    marginBottom: theme.spacing.xs,
  },
  noteTypeSelector: {
    flexDirection: 'row',
    gap: 6,
    marginBottom: theme.spacing.sm,
  },
  noteTypePill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 14,
    backgroundColor: theme.colors.surfaceLight,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  noteTypePillActive: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  noteTypePillText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.xs,
    fontWeight: '600',
  },
  noteTypePillTextActive: {
    color: theme.colors.white,
  },
  noteInput: {
    backgroundColor: theme.colors.background,
    color: theme.colors.text,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
    fontSize: theme.typography.sm,
    minHeight: 60,
    marginBottom: theme.spacing.sm,
  },
  saveNoteBtn: {
    backgroundColor: theme.colors.primary,
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: theme.borderRadius.sm,
    alignItems: 'center',
    alignSelf: 'flex-end',
  },
  saveNoteBtnDisabled: {
    opacity: 0.5,
  },
  saveNoteBtnText: {
    color: theme.colors.white,
    fontSize: theme.typography.sm,
    fontWeight: '600',
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
    maxHeight: '70%',
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
  modalEmptyText: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.sm,
    paddingVertical: theme.spacing.md,
  },
  modalScroll: {
    maxHeight: 300,
  },
  collectionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.surfaceBorder,
  },
  collectionInfo: {
    flex: 1,
    marginRight: 8,
  },
  collectionName: {
    color: theme.colors.text,
    fontSize: theme.typography.md,
    fontWeight: '600',
  },
  collectionDesc: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.xs,
    marginTop: 2,
  },
});
