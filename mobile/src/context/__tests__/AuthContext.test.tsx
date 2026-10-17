import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { AuthProvider, useAuth } from '../AuthContext';
import { api, ApiError, DEFAULT_SERVER_URL } from '../../api/client';

jest.mock('../../api/client', () => {
  return {
    ApiError: jest.requireActual('../../api/client').ApiError,
    DEFAULT_SERVER_URL: 'http://100.88.127.35/aura',
    api: {
      init: jest.fn(),
      onUnauthorized: jest.fn(() => jest.fn()),
      getCachedUser: jest.fn(() => null),
      getServerUrl: jest.fn(),
      getToken: jest.fn(() => null),
      flushOfflineMutations: jest.fn().mockResolvedValue({}),
      getMe: jest.fn(),
      login: jest.fn(),
      logout: jest.fn(),
      setToken: jest.fn(),
      setServerUrl: jest.fn(),
    },
  };
});

describe('AuthContext', () => {
  const mockApi = api as jest.Mocked<typeof api>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockApi.init.mockResolvedValue({
      serverUrl: DEFAULT_SERVER_URL,
      token: null,
    });
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <AuthProvider>{children}</AuthProvider>
  );

  it('initialises without authentication when no token is saved', async () => {
    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
    expect(result.current.serverUrl).toBe(DEFAULT_SERVER_URL);
  });

  it('restores authentication and loads user when stored token exists', async () => {
    mockApi.init.mockResolvedValue({
      serverUrl: 'https://myserver.org/aura',
      token: 'existing_token_xyz',
    });
    mockApi.getMe.mockResolvedValue({
      id: 5,
      email: 'astro@phys.org',
      is_admin: true,
    });

    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('existing_token_xyz');
    expect(result.current.user).toEqual({
      id: 5,
      email: 'astro@phys.org',
      is_admin: true,
    });
    expect(mockApi.getMe).toHaveBeenCalledTimes(1);
  });

  it('clears stored token when initial getMe fails (token expired/invalid)', async () => {
    mockApi.init.mockResolvedValue({
      serverUrl: DEFAULT_SERVER_URL,
      token: 'stale_token',
    });
    mockApi.getMe.mockRejectedValue(new ApiError('Unauthorized', 401));

    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
    expect(mockApi.setToken).toHaveBeenCalledWith(null);
  });

  it('logs in successfully and sets authenticated state', async () => {
    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    mockApi.login.mockResolvedValue({
      token: 'new_token_123',
      user: { id: 1, email: 'new@user.com', is_admin: false },
    });

    await act(async () => {
      await result.current.login('new@user.com', 'password');
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('new_token_123');
    expect(result.current.user).toEqual({ id: 1, email: 'new@user.com', is_admin: false });
  });

  it('logs out and resets state', async () => {
    mockApi.init.mockResolvedValue({
      serverUrl: DEFAULT_SERVER_URL,
      token: 'active_token',
    });
    mockApi.getMe.mockResolvedValue({ id: 1, email: 'user@test.com', is_admin: false });

    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true);
    });

    await act(async () => {
      await result.current.logout();
    });

    expect(mockApi.logout).toHaveBeenCalledTimes(1);
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
  });

  it('updates server URL', async () => {
    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    mockApi.getServerUrl.mockReturnValue('https://custom-server.org/aura');
    await act(async () => {
      await result.current.updateServerUrl('https://custom-server.org/aura');
    });

    expect(mockApi.setServerUrl).toHaveBeenCalledWith('https://custom-server.org/aura');
    expect(result.current.serverUrl).toBe('https://custom-server.org/aura');
  });
  it('keeps the stored login and cached user when starting offline', async () => {
    const cached = { id: 7, email: 'offline@aura.test', is_admin: false };
    mockApi.init.mockResolvedValue({ serverUrl: DEFAULT_SERVER_URL, token: 'saved-token' });
    mockApi.getCachedUser.mockReturnValueOnce(cached);
    mockApi.getMe.mockRejectedValue(new TypeError('Network request failed'));
    const { result } = await renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.token).toBe('saved-token');
    expect(result.current.user).toEqual(cached);
    expect(mockApi.setToken).not.toHaveBeenCalled();
    await act(async () => { await result.current.refreshUser(); });
    expect(result.current.isAuthenticated).toBe(true);
  });

  it('updates visible auth state when a request reports an expired token', async () => {
    mockApi.init.mockResolvedValue({ serverUrl: DEFAULT_SERVER_URL, token: 'saved-token' });
    mockApi.getMe.mockResolvedValue({ id: 1, email: 'test@aura.test', is_admin: false });
    const { result } = await renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => { mockApi.onUnauthorized.mock.calls[0][0](); });
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
  });

  it('resets the loading state and propagates a failed login', async () => {
    const { result } = await renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    mockApi.login.mockRejectedValueOnce(new ApiError('Incorrect password', 401));
    await act(async () => { await expect(result.current.login('user', 'bad')).rejects.toThrow('Incorrect password'); });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isAuthenticated).toBe(false);
  });

});
