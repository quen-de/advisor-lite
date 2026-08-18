import { useState } from 'react';
import type { Portfolio, Position } from '../lib/api';
import { deletePosition, putPosition, setCash } from '../lib/api';

export interface PortfolioPanelProps {
  portfolio: Portfolio;
  onChanged?: () => void;
}

function NumberCell({
  label,
  value,
  onCommit,
}: {
  label: string;
  value: number;
  onCommit: (next: number) => void;
}) {
  const commit = (raw: string) => {
    const next = Number(raw);
    if (!Number.isFinite(next) || next < 0 || next === value) return;
    onCommit(next);
  };
  return (
    <label className="cell">
      <span className="cell-label">{label}</span>
      <input
        key={value}
        type="number"
        min="0"
        step="any"
        defaultValue={value}
        aria-label={label}
        onBlur={(event) => commit(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') (event.target as HTMLInputElement).blur();
        }}
      />
    </label>
  );
}

function AddPositionForm({
  currency,
  onChanged,
}: {
  currency: string;
  onChanged?: () => void;
}) {
  const [ticker, setTicker] = useState('');
  const [name, setName] = useState('');
  const [quantity, setQuantity] = useState('');
  const [costBasis, setCostBasis] = useState('');
  const valid = ticker.trim() !== '' && Number(quantity) > 0 && Number(costBasis) > 0;
  const submit = () => {
    if (!valid) return;
    void putPosition(ticker.trim().toUpperCase(), {
      name: name.trim() || ticker.trim().toUpperCase(),
      quantity: Number(quantity),
      cost_basis: Number(costBasis),
      currency,
    }).then(() => {
      setTicker('');
      setName('');
      setQuantity('');
      setCostBasis('');
      onChanged?.();
    });
  };
  return (
    <form
      className="add-position"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="add-position-row">
        <input
          value={ticker}
          onChange={(event) => setTicker(event.target.value)}
          placeholder="Ticker"
          aria-label="Ticker"
        />
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Name"
          aria-label="Name"
        />
      </div>
      <div className="add-position-row">
        <input
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
          placeholder="Qty"
          aria-label="Quantity"
          type="number"
          min="0"
          step="any"
        />
        <input
          value={costBasis}
          onChange={(event) => setCostBasis(event.target.value)}
          placeholder="Cost basis"
          aria-label="Cost basis"
          type="number"
          min="0"
          step="any"
        />
        <button type="submit" disabled={!valid}>
          Add
        </button>
      </div>
    </form>
  );
}

export function PortfolioPanel({ portfolio, onChanged }: PortfolioPanelProps) {
  const total =
    portfolio.positions.reduce((sum, p) => sum + p.quantity * p.cost_basis, 0) + portfolio.cash;
  const weightOf = (value: number) => (total > 0 ? (value / total) * 100 : 0);
  const update = (position: Position, patch: Partial<Position>) =>
    void putPosition(position.ticker, {
      name: position.name,
      quantity: position.quantity,
      cost_basis: position.cost_basis,
      currency: position.currency,
      ...patch,
    }).then(() => onChanged?.());
  return (
    <div>
      <p className="as-of">Cost-basis weights, as of {portfolio.as_of}</p>
      <ul className="holdings">
        {portfolio.positions.map((position) => {
          const weight = weightOf(position.quantity * position.cost_basis);
          return (
            <li key={position.ticker}>
              <div className="holding-head">
                <span className="ticker">{position.ticker}</span>
                <span className="holding-name">{position.name}</span>
                <span className="weight">{weight.toFixed(1)}%</span>
                <button
                  type="button"
                  className="holding-delete"
                  aria-label={`Remove ${position.ticker}`}
                  title="Remove position"
                  onClick={() => void deletePosition(position.ticker).then(() => onChanged?.())}
                >
                  ×
                </button>
              </div>
              <div className="holding-edit">
                <NumberCell
                  label="Qty"
                  value={position.quantity}
                  onCommit={(quantity) => update(position, { quantity })}
                />
                <NumberCell
                  label="Cost"
                  value={position.cost_basis}
                  onCommit={(cost_basis) => update(position, { cost_basis })}
                />
              </div>
              <div className="weight-track">
                <div className="weight-bar" style={{ width: `${Math.round(weight)}%` }} />
              </div>
            </li>
          );
        })}
        <li key="cash">
          <div className="holding-head">
            <span className="ticker">CASH</span>
            <span className="holding-name">{portfolio.currency}</span>
            <span className="weight">{weightOf(portfolio.cash).toFixed(1)}%</span>
          </div>
          <div className="holding-edit">
            <NumberCell
              label="Amount"
              value={portfolio.cash}
              onCommit={(cash) => void setCash(cash).then(() => onChanged?.())}
            />
          </div>
          <div className="weight-track">
            <div className="weight-bar" style={{ width: `${Math.round(weightOf(portfolio.cash))}%` }} />
          </div>
        </li>
      </ul>
      <AddPositionForm currency={portfolio.currency} onChanged={onChanged} />
    </div>
  );
}
