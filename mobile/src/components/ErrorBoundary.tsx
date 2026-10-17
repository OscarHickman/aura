import React from 'react';
import { RecoveryView } from './RecoveryView';

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <RecoveryView
      message="AURA could not display this screen. Try reopening it. Your saved work is still on your server."
      onRetry={() => this.setState({ failed: false })}
    />;
    return this.props.children;
  }
}
