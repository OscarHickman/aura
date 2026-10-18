import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Play, Pause, RotateCcw, RotateCw, Volume2 } from 'lucide-react-native';
import { audioBriefingService, AudioPlaybackState } from '../services/audio';

interface AudioPlayerProps {
  audioUrl?: string;
  title: string;
  durationSeconds?: number;
}

export const AudioPlayer: React.FC<AudioPlayerProps> = ({
  audioUrl,
  title,
  durationSeconds,
}) => {
  const [state, setState] = useState<AudioPlaybackState>({
    isLoaded: false,
    isPlaying: false,
    positionMillis: 0,
    durationMillis: (durationSeconds || 0) * 1000,
    rate: 1.0,
  });
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const unsubscribe = audioBriefingService.subscribe(setState);
    return () => {
      unsubscribe();
    };
  }, []);

  const handlePlayToggle = async () => {
    if (!state.isLoaded && audioUrl) {
      setIsLoading(true);
      const loaded = await audioBriefingService.loadAudio(audioUrl);
      setIsLoading(false);
      if (loaded) {
        await audioBriefingService.play();
      }
      return;
    }
    await audioBriefingService.togglePlayPause();
  };

  const handleSkip = (deltaSeconds: number) => {
    audioBriefingService.skip(deltaSeconds * 1000);
  };

  const cycleRate = () => {
    const nextRate = state.rate === 1.0 ? 1.25 : state.rate === 1.25 ? 1.5 : state.rate === 1.5 ? 2.0 : 1.0;
    audioBriefingService.setRate(nextRate);
  };

  const formatTime = (millis: number) => {
    const totalSecs = Math.floor(millis / 1000);
    const mins = Math.floor(totalSecs / 60);
    const secs = totalSecs % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  const totalMillis = state.durationMillis || (durationSeconds || 0) * 1000;
  const progressPercent = totalMillis > 0 ? (state.positionMillis / totalMillis) * 100 : 0;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Volume2 size={18} color="#2563eb" style={styles.icon} />
          <Text style={styles.title} numberOfLines={1}>
            {title}
          </Text>
        </View>
        <TouchableOpacity onPress={cycleRate} style={styles.rateButton}>
          <Text style={styles.rateText}>{state.rate}x</Text>
        </TouchableOpacity>
      </View>

      {/* Progress Track */}
      <View style={styles.progressBarTrack}>
        <View style={[styles.progressBarFill, { width: `${Math.min(100, Math.max(0, progressPercent))}%` }]} />
      </View>

      <View style={styles.timeRow}>
        <Text style={styles.timeText}>{formatTime(state.positionMillis)}</Text>
        <Text style={styles.timeText}>{formatTime(totalMillis)}</Text>
      </View>

      {/* Control Buttons */}
      <View style={styles.controlsRow}>
        <TouchableOpacity onPress={() => handleSkip(-15)} style={styles.controlButton}>
          <RotateCcw size={20} color="#4b5563" />
        </TouchableOpacity>

        <TouchableOpacity
          onPress={handlePlayToggle}
          style={styles.playButton}
          disabled={isLoading}
        >
          {isLoading ? (
            <ActivityIndicator size="small" color="#ffffff" />
          ) : state.isPlaying ? (
            <Pause size={22} color="#ffffff" />
          ) : (
            <Play size={22} color="#ffffff" style={{ marginLeft: 2 }} />
          )}
        </TouchableOpacity>

        <TouchableOpacity onPress={() => handleSkip(15)} style={styles.controlButton}>
          <RotateCw size={20} color="#4b5563" />
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 14,
    marginVertical: 10,
    borderWidth: 1,
    borderColor: '#e5e7eb',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 8,
  },
  icon: {
    marginRight: 6,
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
  },
  rateButton: {
    backgroundColor: '#f3f4f6',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  rateText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#374151',
  },
  progressBarTrack: {
    height: 4,
    backgroundColor: '#f3f4f6',
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: '#2563eb',
  },
  timeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
    marginBottom: 8,
  },
  timeText: {
    fontSize: 11,
    color: '#9ca3af',
  },
  controlsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 20,
  },
  controlButton: {
    padding: 8,
  },
  playButton: {
    backgroundColor: '#2563eb',
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
