import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react-native';
import { AuthProvider, useAuth } from '../AuthContext';
import { api, DEFAULT_SERVER_URL } from '../../api/client';

jest.mock('../../api/client', () => {
  return {
    DEFAULT_SERVER_URL: 'http://100.88.127.35/aura',
    api: {
      init: jest.fn(),
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
    mockApi.getMe.mockRejectedValue(new Error('401 Unauthorized'));

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

    await act(async () => {
      await result.current.updateServerUrl('https://custom-server.org/aura');
    });

    expect(mockApi.setServerUrl).toHaveBeenCalledWith('https://custom-server.org/aura');
    expect(result.current.serverUrl).toBe('https://custom-server.org/aura');
  });
});
