import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Message } from './Message';

describe('Message', () => {
  it('renders citation chips and sources', () => {
    render(
      <Message
        role="assistant"
        text="NVDA beat estimates [1]."
        sources={[{ id: 1, title: 'NVDA Q2', url: 'https://news.example/nvda' }]}
      />,
    );
    expect(screen.getByText('1', { selector: 'sup' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /NVDA Q2/ })).toHaveAttribute(
      'href',
      'https://news.example/nvda',
    );
  });

  it('renders markdown tables', () => {
    render(
      <Message
        role="assistant"
        text={'| Ticker | Weight |\n|---|---|\n| NVDA | 8.7% |'}
        sources={[]}
      />,
    );
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'NVDA' })).toBeInTheDocument();
  });

  it('renders plain user text without sources block', () => {
    render(<Message role="user" text="What do I hold?" sources={[]} />);
    expect(screen.getByText('What do I hold?')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });
});
