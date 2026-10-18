import { registerForPushNotificationsAsync } from '../notifications';
import * as Notifications from 'expo-notifications';
import { api } from '../../api/client';

let mockIsDevice = true;

jest.mock('expo-device', () => ({
  get isDevice() {
    return mockIsDevice;
  },
  modelName: 'Pixel 8',
  brand: 'Google',
  designName: 'shiba',
}));

jest.mock('expo-notifications', () => ({
  setNotificationHandler: jest.fn(),
  setNotificationChannelAsync: jest.fn().mockResolvedValue({}),
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(),
  AndroidImportance: {
    MAX: 5,
  },
}));

jest.mock('../../api/client', () => ({
  api: {
    registerDeviceToken: jest.fn(),
  },
}));

describe('registerForPushNotificationsAsync', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsDevice = true;
  });

  it('returns unsupported status when not a physical device', async () => {
    mockIsDevice = false;
    const result = await registerForPushNotificationsAsync();
    expect(result.status).toBe('unsupported');
    expect(result.token).toBeNull();
  });

  it('registers device token successfully when permissions are granted', async () => {
    mockIsDevice = true;
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: 'granted' });
    (Notifications.getExpoPushTokenAsync as jest.Mock).mockResolvedValue({
      data: 'ExponentPushToken[unit-test-token]',
    });
    (api.registerDeviceToken as jest.Mock).mockResolvedValue({
      status: 'ok',
      device: { device_token: 'ExponentPushToken[unit-test-token]' },
    });

    const result = await registerForPushNotificationsAsync();
    expect(result.status).toBe('granted');
    expect(result.token).toBe('ExponentPushToken[unit-test-token]');
    expect(api.registerDeviceToken).toHaveBeenCalledWith(
      'ExponentPushToken[unit-test-token]',
      expect.any(String),
      'Pixel 8'
    );
  });

  it('requests permissions if not already granted', async () => {
    mockIsDevice = true;
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: 'undetermined' });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: 'granted' });
    (Notifications.getExpoPushTokenAsync as jest.Mock).mockResolvedValue({
      data: 'ExponentPushToken[unit-test-token-2]',
    });
    (api.registerDeviceToken as jest.Mock).mockResolvedValue({ status: 'ok' });

    const result = await registerForPushNotificationsAsync();
    expect(Notifications.requestPermissionsAsync).toHaveBeenCalled();
    expect(result.status).toBe('granted');
    expect(result.token).toBe('ExponentPushToken[unit-test-token-2]');
  });

  it('returns denied when user denies notification permission', async () => {
    mockIsDevice = true;
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ status: 'undetermined' });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValue({ status: 'denied' });

    const result = await registerForPushNotificationsAsync();
    expect(result.status).toBe('denied');
    expect(result.token).toBeNull();
    expect(api.registerDeviceToken).not.toHaveBeenCalled();
  });
});
