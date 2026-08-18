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

export interface MessageProps {
  role: 'user' | 'assistant' | 'system';
  text: string;
  sources: Source[];
  streaming?: boolean;
}

export function Message({ role, text, sources, streaming }: MessageProps) {
  return (
    <div className={`message message-${role}`}>
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
