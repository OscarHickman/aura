import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { theme } from '../constants/theme';

export function RecoveryView({ message, onRetry, onSettings }: {
  message?: string; onRetry: () => void; onSettings?: () => void;
}) {
  return <View style={styles.container} accessibilityRole="alert">
    <Text style={styles.title}>Unable to load papers</Text>
    <Text style={styles.message}>{message || 'Check your Wi-Fi or Tailscale connection and make sure your AURA server is running.'}</Text>
    <TouchableOpacity accessibilityRole="button" style={styles.button} onPress={onRetry}>
      <Text style={styles.label}>Try again</Text>
    </TouchableOpacity>
    {onSettings && <TouchableOpacity accessibilityRole="button" style={styles.button} onPress={onSettings}>
      <Text style={styles.label}>Connection settings</Text>
    </TouchableOpacity>}
  </View>;
}
const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24, backgroundColor: theme.colors.background },
  title: { color: theme.colors.text, fontSize: 20, fontWeight: '700', marginBottom: 12 },
  message: { color: theme.colors.textMuted, textAlign: 'center', marginBottom: 20 },
  button: { backgroundColor: theme.colors.primary, borderRadius: 12, padding: 14, marginBottom: 10 },
  label: { color: theme.colors.white, fontWeight: '600' },
});
