module.exports = {
  preset: 'jest-expo',
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?)|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|lucide-react-native)',
  ],
  collectCoverageFrom: ['src/api/*.ts', 'src/context/*.tsx'],
  coverageThreshold: {
    './src/api/': { statements: 80, functions: 80, lines: 80 },
    './src/context/': { statements: 80, functions: 80, lines: 80 },
  },
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
};
