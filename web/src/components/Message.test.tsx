import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Message } from './Message';

describe('Message', () => {
  it('renders citation chips and sources', () => {
    render(
      <Message
        role="assistant"
        parts={[{ kind: 'text', text: 'NVDA beat estimates [1].' }]}
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
        parts={[{ kind: 'text', text: '| Ticker | Weight |\n|---|---|\n| NVDA | 8.7% |' }]}
        sources={[]}
      />,
    );
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'NVDA' })).toBeInTheDocument();
  });

  it('renders plain user text without sources block', () => {
    render(
      <Message role="user" parts={[{ kind: 'text', text: 'What do I hold?' }]} sources={[]} />,
    );
    expect(screen.getByText('What do I hold?')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('interleaves bubbles and text segments in order', () => {
    render(
      <Message
        role="assistant"
        parts={[
          {
            kind: 'bubble',
            thoughts: 'Check holdings first.',
            tools: [{ text: 'Reading the portfolio', done: true }],
          },
          { kind: 'text', text: 'The portfolio is tech-heavy.' },
          { kind: 'bubble', thoughts: 'Now search.', tools: [{ text: 'Searching', done: false }] },
          { kind: 'text', text: 'Final answer.' },
        ]}
        sources={[]}
      />,
    );
    const rendered = screen.getAllByText(/./, { selector: '.bubble-thoughts, .message-body p' });
    expect(rendered.map((node) => node.textContent)).toEqual([
      'Check holdings first.',
      'The portfolio is tech-heavy.',
      'Now search.',
      'Final answer.',
    ]);
    expect(screen.getByText('✓')).toBeInTheDocument();
  });
});
