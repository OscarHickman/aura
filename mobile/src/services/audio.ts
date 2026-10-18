import { Audio, AVPlaybackStatus } from 'expo-av';

export interface AudioPlaybackState {
  isLoaded: boolean;
  isPlaying: boolean;
  positionMillis: number;
  durationMillis: number;
  rate: number;
  error?: string;
}

type AudioStateListener = (state: AudioPlaybackState) => void;

class AudioBriefingService {
  private sound: Audio.Sound | null = null;
  private currentUrl: string | null = null;
  private listeners: Set<AudioStateListener> = new Set();
  private state: AudioPlaybackState = {
    isLoaded: false,
    isPlaying: false,
    positionMillis: 0,
    durationMillis: 0,
    rate: 1.0,
  };

  subscribe(listener: AudioStateListener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private updateState(newState: Partial<AudioPlaybackState>) {
    this.state = { ...this.state, ...newState };
    this.listeners.forEach((listener) => listener(this.state));
  }

  private onPlaybackStatusUpdate = (status: AVPlaybackStatus) => {
    if (!status.isLoaded) {
      if (status.error) {
        this.updateState({ isLoaded: false, isPlaying: false, error: status.error });
      }
      return;
    }

    this.updateState({
      isLoaded: true,
      isPlaying: status.isPlaying,
      positionMillis: status.positionMillis,
      durationMillis: status.durationMillis || 0,
      rate: status.rate,
    });
  };

  async loadAudio(url: string): Promise<boolean> {
    if (this.currentUrl === url && this.sound) {
      return true;
    }

    try {
      if (this.sound) {
        await this.sound.unloadAsync();
        this.sound = null;
      }

      await Audio.setAudioModeAsync({
        playsInSilentModeIOS: true,
        staysActiveInBackground: true,
        shouldDuckAndroid: true,
      });

      const { sound } = await Audio.Sound.createAsync(
        { uri: url },
        { shouldPlay: false, rate: this.state.rate, shouldCorrectPitch: true },
        this.onPlaybackStatusUpdate
      );

      this.sound = sound;
      this.currentUrl = url;
      return true;
    } catch (e: any) {
      this.updateState({ error: e.message || 'Failed to load audio' });
      return false;
    }
  }

  async play(): Promise<void> {
    if (this.sound) {
      await this.sound.playAsync();
    }
  }

  async pause(): Promise<void> {
    if (this.sound) {
      await this.sound.pauseAsync();
    }
  }

  async togglePlayPause(): Promise<void> {
    if (this.state.isPlaying) {
      await this.pause();
    } else {
      await this.play();
    }
  }

  async seek(positionMillis: number): Promise<void> {
    if (this.sound) {
      await this.sound.setPositionAsync(positionMillis);
    }
  }

  async skip(deltaMillis: number): Promise<void> {
    if (this.sound && this.state.isLoaded) {
      const target = Math.max(
        0,
        Math.min(this.state.durationMillis, this.state.positionMillis + deltaMillis)
      );
      await this.seek(target);
    }
  }

  async setRate(rate: number): Promise<void> {
    if (this.sound) {
      await this.sound.setRateAsync(rate, true);
      this.updateState({ rate });
    }
  }

  async stopAndUnload(): Promise<void> {
    if (this.sound) {
      await this.sound.stopAsync();
      await this.sound.unloadAsync();
      this.sound = null;
      this.currentUrl = null;
      this.updateState({ isLoaded: false, isPlaying: false, positionMillis: 0 });
    }
  }
}

export const audioBriefingService = new AudioBriefingService();
