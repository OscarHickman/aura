import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
} from 'react-native';
import {
  Server,
  ShieldCheck,
  LogOut,
  CheckCircle2,
  XCircle,
  User as UserIcon,
  Key,
  BookOpen,
  RefreshCw,
} from 'lucide-react-native';
import { theme } from '../constants/theme';
import { useAuth } from '../context/AuthContext';
import { api } from '../api/client';

interface SettingsScreenProps {
  navigation?: any;
}

export const SettingsScreen: React.FC<SettingsScreenProps> = ({ navigation }) => {
  const { serverUrl, token, user, isAuthenticated, login, logout, updateServerUrl } = useAuth();

  const [urlInput, setUrlInput] = useState<string>(serverUrl);
  const [isTestingUrl, setIsTestingUrl] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  // Login form state
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [isLoggingIn, setIsLoggingIn] = useState<boolean>(false);

  // Offline queue state
  const [pendingMutations, setPendingMutations] = useState<number>(0);
  const [isSyncingOffline, setIsSyncingOffline] = useState<boolean>(false);

  const checkPendingMutations = useCallback(async () => {
    try {
      const count = await api.getOfflineQueueCount();
      setPendingMutations(count);
    } catch {
      // Ignore
    }
  }, []);

  useEffect(() => {
    checkPendingMutations();
  }, [checkPendingMutations]);

  const handleFlushOffline = async () => {
    setIsSyncingOffline(true);
    try {
      const res = await api.flushOfflineMutations();
      await checkPendingMutations();
      if (res.successCount > 0) {
        Alert.alert(
          'Synchronisation Complete',
          `Successfully replayed ${res.successCount} offline action(s).`
        );
      } else if (res.failedCount > 0) {
        Alert.alert(
          'Synchronisation Warning',
          `${res.failedCount} action(s) could not be replayed.`
        );
      } else {
        Alert.alert('Synchronisation', 'No pending offline actions found.');
      }
    } catch (e: any) {
      Alert.alert('Sync Error', e.message || 'Failed to sync offline mutations.');
    } finally {
      setIsSyncingOffline(false);
    }
  };

  const handleSaveUrl = async () => {
    try {
      await updateServerUrl(urlInput);
      Alert.alert('Saved', 'Server address updated.');
    } catch (e: any) {
      Alert.alert('Error', e.message);
    }
  };

  const handleTestConnection = async () => {
    setIsTestingUrl(true);
    setTestResult(null);
    try {
      const res = await api.testConnection(urlInput);
      if (res.ok) {
        setTestResult({ ok: true, message: 'Server reached and healthy!' });
      } else {
        setTestResult({ ok: false, message: res.error || 'Server unhealthy' });
      }
    } finally {
      setIsTestingUrl(false);
    }
  };

  const handleLogin = async () => {
    if (!email.trim() || !password) {
      Alert.alert('Validation', 'Please provide email and password.');
      return;
    }
    setIsLoggingIn(true);
    try {
      await login(email.trim(), password);
      Alert.alert('Success', 'Logged in successfully.');
      setPassword('');
    } catch (err: any) {
      Alert.alert('Login Failed', err.message || 'Check your credentials and server URL.');
    } finally {
      setIsLoggingIn(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Home Server Configuration */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Server size={20} color={theme.colors.primaryLight} />
          <Text style={styles.cardTitle}>Home Server Connection</Text>
        </View>

        <Text style={styles.label}>Server Base URL (LAN or Tailscale IP)</Text>
        <TextInput
          style={styles.input}
          value={urlInput}
          onChangeText={(txt) => {
            setUrlInput(txt);
            setTestResult(null);
          }}
          placeholder="http://100.88.127.35/aura"
          placeholderTextColor={theme.colors.textDim}
          autoCapitalize="none"
          autoCorrect={false}
        />

        <View style={styles.urlButtonRow}>
          <TouchableOpacity
            style={[styles.btn, styles.secondaryBtn]}
            onPress={handleTestConnection}
            disabled={isTestingUrl}
          >
            {isTestingUrl ? (
              <ActivityIndicator size="small" color={theme.colors.text} />
            ) : (
              <Text style={styles.secondaryBtnText}>Test Ping</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.btn, styles.primaryBtn]}
            onPress={handleSaveUrl}
          >
            <Text style={styles.primaryBtnText}>Save Address</Text>
          </TouchableOpacity>
        </View>

        {testResult && (
          <View
            style={[
              styles.testResultBox,
              testResult.ok ? styles.testSuccess : styles.testFail,
            ]}
          >
            {testResult.ok ? (
              <CheckCircle2 size={16} color={theme.colors.success} />
            ) : (
              <XCircle size={16} color={theme.colors.danger} />
            )}
            <Text
              style={[
                styles.testResultText,
                { color: testResult.ok ? theme.colors.success : theme.colors.danger },
              ]}
            >
              {testResult.message}
            </Text>
          </View>
        )}
      </View>

      {/* Account / Authentication Section */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <ShieldCheck size={20} color={theme.colors.primaryLight} />
          <Text style={styles.cardTitle}>Account Authentication</Text>
        </View>

        {isAuthenticated && user ? (
          <View>
            <View style={styles.userInfoRow}>
              <UserIcon size={18} color={theme.colors.textMuted} />
              <Text style={styles.userEmail}>{user.email}</Text>
              {user.is_admin && (
                <View style={styles.adminBadge}>
                  <Text style={styles.adminText}>Admin</Text>
                </View>
              )}
            </View>

            <TouchableOpacity style={styles.logoutBtn} onPress={logout}>
              <LogOut size={16} color={theme.colors.danger} />
              <Text style={styles.logoutText}>Sign Out</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View>
            <Text style={styles.label}>Account Email</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="user@example.com"
              placeholderTextColor={theme.colors.textDim}
              autoCapitalize="none"
              keyboardType="email-address"
            />

            <Text style={styles.label}>Password</Text>
            <TextInput
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder="••••••••"
              placeholderTextColor={theme.colors.textDim}
              secureTextEntry
            />

            <TouchableOpacity
              style={[styles.btn, styles.primaryBtn, { marginTop: theme.spacing.sm }]}
              onPress={handleLogin}
              disabled={isLoggingIn}
            >
              {isLoggingIn ? (
                <ActivityIndicator size="small" color={theme.colors.white} />
              ) : (
                <Text style={styles.primaryBtnText}>Log In to Home Server</Text>
              )}
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* Research Tracking */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <BookOpen size={20} color={theme.colors.primaryLight} />
          <Text style={styles.cardTitle}>Research Tracking</Text>
        </View>
        <Text style={styles.aboutText}>
          Track your own publications, monitor incoming citation alerts, and automatically
          ingest citing works into your feed.
        </Text>
        <TouchableOpacity
          style={[styles.btn, styles.primaryBtn, { marginTop: theme.spacing.sm }]}
          onPress={() => navigation?.navigate('MyPapers')}
        >
          <Text style={styles.primaryBtnText}>My Publications & Citation Tracking</Text>
        </TouchableOpacity>
      </View>

      {/* Offline Synchronisation */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <RefreshCw size={20} color={theme.colors.primaryLight} />
          <Text style={styles.cardTitle}>Offline Synchronisation</Text>
        </View>
        <Text style={styles.aboutText}>
          {pendingMutations > 0
            ? `${pendingMutations} pending mutation${pendingMutations > 1 ? 's' : ''} queued locally.`
            : 'All ratings, reading list actions, and notes are synchronised.'}
        </Text>
        {pendingMutations > 0 && (
          <TouchableOpacity
            style={[styles.btn, styles.secondaryBtn, { marginTop: theme.spacing.sm }]}
            onPress={handleFlushOffline}
            disabled={isSyncingOffline}
          >
            {isSyncingOffline ? (
              <ActivityIndicator size="small" color={theme.colors.text} />
            ) : (
              <Text style={styles.secondaryBtnText}>Sync Pending Actions Now</Text>
            )}
          </TouchableOpacity>
        )}
      </View>

      {/* About & Deployment info */}
      <View style={styles.aboutCard}>
        <Text style={styles.aboutTitle}>AURA Mobile for Android</Text>
        <Text style={styles.aboutText}>
          Connected to your personal research engine. Tagged releases automatically
          build standalone binaries and deploy backend updates to your home server.
        </Text>
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
    padding: theme.spacing.md,
    paddingBottom: theme.spacing.xl * 2,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.lg,
    marginBottom: theme.spacing.md,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: theme.spacing.md,
  },
  cardTitle: {
    color: theme.colors.text,
    fontSize: theme.typography.md,
    fontWeight: '700',
  },
  label: {
    color: theme.colors.textMuted,
    fontSize: theme.typography.xs,
    fontWeight: '600',
    marginBottom: 6,
    marginTop: 4,
  },
  input: {
    backgroundColor: theme.colors.background,
    color: theme.colors.text,
    borderRadius: theme.borderRadius.sm,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: theme.typography.sm,
    borderWidth: 1,
    borderColor: theme.colors.surfaceBorder,
    marginBottom: theme.spacing.sm,
  },
  urlButtonRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: 4,
  },
  btn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: theme.borderRadius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryBtn: {
    backgroundColor: theme.colors.primary,
  },
  primaryBtnText: {
    color: theme.colors.white,
    fontWeight: '600',
    fontSize: theme.typography.sm,
  },
  secondaryBtn: {
    backgroundColor: theme.colors.surfaceLight,
  },
  secondaryBtnText: {
    color: theme.colors.textSecondary,
    fontWeight: '600',
    fontSize: theme.typography.sm,
  },
  testResultBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: theme.spacing.md,
    padding: 10,
    borderRadius: theme.borderRadius.sm,
  },
  testSuccess: {
    backgroundColor: 'rgba(16, 185, 129, 0.12)',
  },
  testFail: {
    backgroundColor: 'rgba(239, 68, 68, 0.12)',
  },
  testResultText: {
    fontSize: theme.typography.xs,
    fontWeight: '600',
  },
  userInfoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: theme.colors.background,
    padding: theme.spacing.md,
    borderRadius: theme.borderRadius.sm,
    marginBottom: theme.spacing.md,
  },
  userEmail: {
    color: theme.colors.text,
    fontSize: theme.typography.sm,
    fontWeight: '600',
    flex: 1,
  },
  adminBadge: {
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  adminText: {
    color: theme.colors.primaryLight,
    fontSize: 11,
    fontWeight: '700',
  },
  logoutBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    borderRadius: theme.borderRadius.sm,
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
  },
  logoutText: {
    color: theme.colors.danger,
    fontWeight: '600',
    fontSize: theme.typography.sm,
  },
  aboutCard: {
    padding: theme.spacing.md,
    alignItems: 'center',
  },
  aboutTitle: {
    color: theme.colors.textDim,
    fontSize: theme.typography.xs,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  aboutText: {
    color: theme.colors.textDim,
    fontSize: 11,
    textAlign: 'center',
    lineHeight: 16,
  },
});
