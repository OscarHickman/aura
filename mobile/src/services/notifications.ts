import { Platform } from 'react-native';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { api } from '../api/client';

// Configure notification behavior for incoming notifications while app is in foreground
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export interface PushRegistrationResult {
  token: string | null;
  status: 'granted' | 'denied' | 'unsupported' | 'error';
  error?: string;
}

/**
 * Register the current device for Expo push notifications and sync the token to AURA backend.
 */
export async function registerForPushNotificationsAsync(): Promise<PushRegistrationResult> {
  try {
    if (!Device.isDevice) {
      return {
        token: null,
        status: 'unsupported',
        error: 'Push notifications require a physical device.',
      };
    }

    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'AURA Research Notifications',
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: '#6366f1',
      });
    }

    const perm = await Notifications.getPermissionsAsync();
    const existingStatus = perm?.status;
    let finalStatus = existingStatus;
    if (existingStatus !== 'granted') {
      const requested = await Notifications.requestPermissionsAsync();
      finalStatus = requested?.status;
    }

    if (finalStatus !== 'granted') {
      return {
        token: null,
        status: 'denied',
        error: 'Notification permissions were not granted.',
      };
    }

    const pushTokenData = await Notifications.getExpoPushTokenAsync();
    const token = pushTokenData.data;

    if (token) {
      const deviceName = Device.modelName || `${Device.brand || ''} ${Device.designName || ''}`.trim() || 'Android Device';
      try {
        await api.registerDeviceToken(token, Platform.OS, deviceName);
      } catch (err: any) {
        console.warn('Failed to sync push token with backend:', err?.message);
      }
    }

    return {
      token,
      status: 'granted',
    };
  } catch (error: any) {
    console.error('Error registering for push notifications:', error);
    return {
      token: null,
      status: 'error',
      error: error?.message || 'Unknown error occurred during push registration.',
    };
  }
}
