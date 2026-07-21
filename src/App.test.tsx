import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renders the landing screen without crashing', () => {
    render(<App />);

    expect(screen.getByText(/Un artisan de confiance/i)).toBeInTheDocument();
  });
});
