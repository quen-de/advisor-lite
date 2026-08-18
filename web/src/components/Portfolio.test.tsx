import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PortfolioPanel } from './Portfolio';

const portfolio = {
  as_of: '2026-08-01',
  cash: 100,
  currency: 'USD',
  summary: '',
  positions: [
    { ticker: 'AAA', name: 'Alpha Corp', quantity: 10, cost_basis: 10, currency: 'USD' },
    { ticker: 'BBB', name: 'Beta Corp', quantity: 30, cost_basis: 10, currency: 'USD' },
  ],
};

describe('PortfolioPanel', () => {
  it('shows tickers with weight bars sized by cost-basis weight', () => {
    render(<PortfolioPanel portfolio={portfolio} />);
    expect(screen.getByText('AAA')).toBeInTheDocument();
    expect(screen.getByText('BBB')).toBeInTheDocument();
    const bars = document.querySelectorAll('.weight-bar');
    expect(bars).toHaveLength(3);
    expect((bars[0] as HTMLElement).style.width).toBe('20%');
    expect((bars[1] as HTMLElement).style.width).toBe('60%');
    expect((bars[2] as HTMLElement).style.width).toBe('20%');
  });

  it('commits a quantity edit as a PUT and reports the change', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    const onChanged = vi.fn();
    render(<PortfolioPanel portfolio={portfolio} onChanged={onChanged} />);
    const qty = screen.getAllByLabelText('Qty')[0];
    fireEvent.change(qty, { target: { value: '25' } });
    fireEvent.blur(qty);
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/positions/AAA');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body).quantity).toBe(25);
    vi.unstubAllGlobals();
  });

  it('removes a position via DELETE', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    const onChanged = vi.fn();
    render(<PortfolioPanel portfolio={portfolio} onChanged={onChanged} />);
    fireEvent.click(screen.getByLabelText('Remove BBB'));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith('/api/positions/BBB', { method: 'DELETE' });
    vi.unstubAllGlobals();
  });
});
