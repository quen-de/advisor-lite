import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Source } from '../lib/api';

interface HastNode {
  type: string;
  value?: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

const MARKER = /\[(\d+)\]/g;

function splitTextNode(node: HastNode): HastNode[] {
  const text = node.value ?? '';
  const out: HastNode[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    if (match.index > last) out.push({ type: 'text', value: text.slice(last, match.index) });
    out.push({
      type: 'element',
      tagName: 'sup',
      properties: { className: 'cite' },
      children: [{ type: 'text', value: match[1] }],
    });
    last = match.index + match[0].length;
  }
  if (out.length === 0) return [node];
  if (last < text.length) out.push({ type: 'text', value: text.slice(last) });
  return out;
}

/** Rehype plugin turning [n] markers in text nodes into citation chips. */
function citationChips() {
  return (tree: HastNode) => {
    const walk = (node: HastNode) => {
      if (!node.children) return;
      node.children = node.children.flatMap((child) =>
        child.type === 'text' ? splitTextNode(child) : [child],
      );
      node.children.forEach(walk);
    };
    walk(tree);
  };
}

export interface ToolLine {
  id: string;
  text: string;
  done: boolean;
}

/** One closed-or-growing thinking sequence: the commentary the model
 * streamed before a tool round, plus the tool calls of that round. */
export interface Bubble {
  thoughts: string;
  tools: ToolLine[];
}

export interface MessageProps {
  role: 'user' | 'assistant' | 'system';
  text: string;
  sources: Source[];
  bubbles?: Bubble[];
  streaming?: boolean;
}

export function Message({ role, text, sources, bubbles = [], streaming }: MessageProps) {
  return (
    <div className={`message message-${role}`}>
      {bubbles.map((bubble, index) => (
        <div className="thinking-bubble" key={index}>
          {bubble.thoughts && <p className="bubble-thoughts">{bubble.thoughts}</p>}
          {bubble.tools.length > 0 && (
            <ul className="bubble-tools">
              {bubble.tools.map((tool, toolIndex) => (
                <li
                  key={tool.id || toolIndex}
                  className={tool.done ? 'tool-line tool-done' : 'tool-line'}
                >
                  <span className="tool-mark" aria-hidden="true">
                    {tool.done ? '✓' : '·'}
                  </span>
                  {tool.text}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
      <div className="message-body">
        {role === 'assistant' ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[citationChips]}>
            {text}
          </ReactMarkdown>
        ) : (
          <p>{text}</p>
        )}
        {streaming && <span className="caret" aria-hidden="true" />}
      </div>
      {sources.length > 0 && (
        <ul className="sources">
          {sources.map((source) => (
            <li key={source.id}>
              <span className="source-id">{source.id}</span>
              <a href={source.url} target="_blank" rel="noreferrer">
                {source.title}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
