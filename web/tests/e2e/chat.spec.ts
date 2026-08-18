import { expect, test } from '@playwright/test';

const portfolio = {
  as_of: '2026-08-01',
  cash: 12000,
  currency: 'USD',
  summary: 'demo',
  positions: [
    { ticker: 'NVDA', name: 'NVIDIA Corp', quantity: 40, cost_basis: 94.1, currency: 'USD' },
    { ticker: 'MSFT', name: 'Microsoft Corp', quantity: 25, cost_basis: 388, currency: 'USD' },
  ],
};

const sseBody = [
  'event: delta\ndata: {"text":"Let me check the latest numbers."}\n\n',
  'event: demote\ndata: {}\n\n',
  'event: status\ndata: {"id":"t1","text":"Reading the portfolio"}\n\n',
  'event: status_done\ndata: {"id":"t1"}\n\n',
  'event: delta\ndata: {"text":"NVDA looks stretched [1]."}\n\n',
  'event: sources\ndata: {"sources":[{"id":1,"title":"NVDA Q2","url":"https://news.example/nvda"}],"text":"NVDA looks stretched [1]."}\n\n',
  'event: done\ndata: {"chat_id":"c1"}\n\n',
].join('');

test('ask a question, get a cited answer', async ({ page }) => {
  await page.route('**/api/portfolio', (route) => route.fulfill({ json: portfolio }));
  await page.route('**/api/chats', (route) =>
    route.request().method() === 'POST'
      ? route.fulfill({ json: { id: 'c1', title: 'New conversation', created_at: '2026-08-18' } })
      : route.fulfill({ json: [] }),
  );
  await page.route('**/api/chats/c1/exchanges', (route) => route.fulfill({ json: [] }));
  await page.route('**/api/chats/c1/messages', (route) =>
    route.fulfill({
      contentType: 'text/event-stream',
      body: sseBody,
    }),
  );

  await page.goto('/');
  await expect(page.getByText(/not financial advice/i)).toBeVisible();
  await expect(page.getByText('NVDA')).toBeVisible();

  await page.getByRole('button', { name: 'New conversation' }).first().click();
  await page.getByLabel('Message').fill('Should I trim NVDA?');
  await page.getByRole('button', { name: 'Send' }).click();

  await expect(page.getByText('NVDA looks stretched')).toBeVisible();
  await expect(page.locator('.bubble-thoughts')).toHaveText('Let me check the latest numbers.');
  await expect(page.locator('.tool-line')).toContainText('Reading the portfolio');
  await expect(page.locator('.tool-line')).toHaveClass(/tool-done/); // check mark after the hold
  await expect(page.locator('sup.cite')).toHaveText('1');
  await expect(page.getByRole('link', { name: /NVDA Q2/ })).toHaveAttribute(
    'href',
    'https://news.example/nvda',
  );
});
