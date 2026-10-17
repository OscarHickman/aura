import React from 'react';
import { Text } from 'react-native';
import { render, screen, fireEvent } from '@testing-library/react-native';
import { ErrorBoundary } from '../ErrorBoundary';

it('recovers from a render failure when retried', async () => {
  const error = jest.spyOn(console, 'error').mockImplementation(() => {});
  let broken = true;
  function Child() {
    if (broken) throw new Error('Render failure');
    return <Text>Recovered</Text>;
  }
  try {
    await render(<ErrorBoundary><Child /></ErrorBoundary>);
    expect(screen.getByText('Try again')).toBeTruthy();
    broken = false;
    await fireEvent.press(screen.getByText('Try again'));
    expect(screen.getByText('Recovered')).toBeTruthy();
  } finally { error.mockRestore(); }
});
