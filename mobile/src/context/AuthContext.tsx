import React, { createContext, useContext, useState, useEffect } from 'react';
import { AppState } from 'react-native';
import { api, ApiError, DEFAULT_SERVER_URL } from '../api/client';
import { User } from '../types';

interface AuthContextType {
  serverUrl: string;
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, pass: string) => Promise<void>;
  logout: () => Promise<void>;
  updateServerUrl: (url: string) => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [serverUrl, setServerUrl] = useState<string>(DEFAULT_SERVER_URL);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const unsubscribe = api.onUnauthorized(() => {
      setToken(null);
      setUser(null);
    });
    const bootstrap = async () => {
      try {
        const { serverUrl: savedUrl, token: savedToken } = await api.init();
        setServerUrl(savedUrl);
        setToken(savedToken);
        setUser(api.getCachedUser());

        if (savedToken) {
          try {
            const me = await api.getMe();
            setUser(me);
          } catch (e) {
            if (e instanceof ApiError && e.status === 401) {
              await api.setToken(null);
              setToken(null);
              setUser(null);
            }
          }
        }
      } catch (err) {
        console.error('Auth initialization error:', err);
      } finally {
        setIsLoading(false);
      }
    };

    bootstrap();
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (!token || !user) return;
    const sync = () => {
      if (AppState.currentState === 'active') void api.flushOfflineMutations().catch(() => undefined);
    };
    sync();
    const timer = setInterval(sync, 30000);
    const subscription = AppState.addEventListener('change', state => { if (state === 'active') sync(); });
    return () => { clearInterval(timer); subscription.remove(); };
  }, [token, user?.id]);

  const login = async (email: string, pass: string) => {
    setIsLoading(true);
    try {
      const { token: newToken, user: newUser } = await api.login(email, pass);
      setToken(newToken);
      setUser(newUser);
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    await api.logout();
    setToken(null);
    setUser(null);
  };

  const updateServerUrl = async (newUrl: string) => {
    await api.setServerUrl(newUrl);
    setServerUrl(api.getServerUrl());
    setToken(api.getToken());
    setUser(api.getCachedUser());
  };

  const refreshUser = async () => {
    if (!token) return;
    try {
      const me = await api.getMe();
      setUser(me);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setToken(null);
        setUser(null);
      }
    }
  };

  return (
    <AuthContext.Provider
      value={{
        serverUrl,
        token,
        user,
        isAuthenticated: !!token,
        isLoading,
        login,
        logout,
        updateServerUrl,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
};
