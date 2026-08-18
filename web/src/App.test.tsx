import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('App', () => {
  it('renders the demo stamp', () => {
    render(<App />);
    expect(screen.getByText(/not financial advice/i)).toBeInTheDocument();
  });
});
