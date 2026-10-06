import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { Layers, Sparkles, Bookmark, Settings as SettingsIcon } from 'lucide-react-native';

import { theme } from './src/constants/theme';
import { AuthProvider } from './src/context/AuthContext';
import { TriageScreen } from './src/screens/TriageScreen';
import { FeedScreen } from './src/screens/FeedScreen';
import { ReadingListScreen } from './src/screens/ReadingListScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { PaperDetailScreen } from './src/screens/PaperDetailScreen';
import { MyPapersScreen } from './src/screens/MyPapersScreen';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

const navTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: theme.colors.background,
    card: theme.colors.surface,
    text: theme.colors.text,
    border: theme.colors.surfaceBorder,
    primary: theme.colors.primary,
  },
};

function BottomTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: {
          backgroundColor: theme.colors.background,
          borderBottomWidth: 1,
          borderBottomColor: theme.colors.surfaceBorder,
        },
        headerTintColor: theme.colors.text,
        headerTitleStyle: {
          fontWeight: '700',
          fontSize: theme.typography.lg,
        },
        tabBarStyle: {
          backgroundColor: theme.colors.surface,
          borderTopColor: theme.colors.surfaceBorder,
          paddingTop: 4,
        },
        tabBarActiveTintColor: theme.colors.primaryLight,
        tabBarInactiveTintColor: theme.colors.textDim,
      }}
    >
      <Tab.Screen
        name="TriageTab"
        component={TriageScreen}
        options={{
          title: 'Triage Deck',
          tabBarLabel: 'Triage',
          tabBarIcon: ({ color, size }) => <Sparkles color={color} size={size} />,
        }}
      />
      <Tab.Screen
        name="FeedTab"
        component={FeedScreen}
        options={{
          title: 'Paper Feed',
          tabBarLabel: 'Feed',
          tabBarIcon: ({ color, size }) => <Layers color={color} size={size} />,
        }}
      />
      <Tab.Screen
        name="ReadingListTab"
        component={ReadingListScreen}
        options={{
          title: 'Reading List',
          tabBarLabel: 'Saved',
          tabBarIcon: ({ color, size }) => <Bookmark color={color} size={size} />,
        }}
      />
      <Tab.Screen
        name="SettingsTab"
        component={SettingsScreen}
        options={{
          title: 'Settings',
          tabBarLabel: 'Settings',
          tabBarIcon: ({ color, size }) => <SettingsIcon color={color} size={size} />,
        }}
      />
    </Tab.Navigator>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <NavigationContainer theme={navTheme}>
          <StatusBar style="light" />
          <Stack.Navigator
            screenOptions={{
              headerStyle: {
                backgroundColor: theme.colors.background,
              },
              headerTintColor: theme.colors.text,
              headerTitleStyle: {
                fontWeight: '700',
              },
              headerBackVisible: true,
            }}
          >
            <Stack.Screen
              name="Root"
              component={BottomTabs}
              options={{ headerShown: false }}
            />
            <Stack.Screen
              name="PaperDetail"
              component={PaperDetailScreen}
              options={{ title: 'Paper Detail' }}
            />
            <Stack.Screen
              name="MyPapers"
              component={MyPapersScreen}
              options={{ title: 'My Publications' }}
            />
          </Stack.Navigator>
        </NavigationContainer>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
