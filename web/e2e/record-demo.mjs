// Drive the live stack through the demo conversation while recording video.
// Run from web/: node e2e/record-demo.mjs  (stack up on :8080 with real keys)
import { chromium } from '@playwright/test';

const BASE = process.env.DEMO_URL ?? 'http://localhost:8080';
const PROMPT =
  process.env.DEMO_PROMPT ??
  'Investigate new opportunities to increase the spread of my portfolio. Compare candidates in a table.';

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  deviceScaleFactor: 2,
  recordVideo: { dir: 'e2e/recordings', size: { width: 1280, height: 800 } },
});
const page = await context.newPage();
await page.goto(BASE);
await page.waitForSelector('.holdings');
await page.waitForTimeout(1500);

await page.locator('.new-chat').click();
// Pin the recording's own chat id now: deleting "the newest chat" at the end
// would race anything else creating chats meanwhile.
const chatId = (await (await fetch(`${BASE}/api/chats`)).json())[0].id;
const input = page.locator('.chat-input input');
await input.pressSequentially(PROMPT, { delay: 35 });
await page.waitForTimeout(400);
await page.locator('.chat-input button').click();

// The sources list renders right before `done`; hold the final frame after it.
await page.locator('.sources').waitFor({ timeout: 240_000 });
await page.waitForTimeout(3000);

const video = page.video();
await context.close();
console.log(await video.path());

if (!process.env.KEEP_CHAT) {
  await fetch(`${BASE}/api/chats/${chatId}`, { method: 'DELETE' });
}
await browser.close();
