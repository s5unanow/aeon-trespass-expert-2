/**
 * InlineRenderer — renders inline content spans.
 *
 * Exhaustive switch over BundleInlineNode kinds with assertNever fallback.
 */

import type { BundleInlineNode } from "@aeon-reader/contracts";
import { assertNever } from "@/lib/assertNever";
import { SymbolInline } from "./SymbolInline";

interface InlineRendererProps {
  node: BundleInlineNode;
}

export function InlineRenderer({ node }: InlineRendererProps) {
  switch (node.kind) {
    case "text": {
      let content: React.ReactNode = node.ru_text ?? node.text;
      if (node.bold) content = <strong>{content}</strong>;
      if (node.italic) content = <em>{content}</em>;
      if (node.monospace) content = <code>{content}</code>;
      return <span className="inline-text">{content}</span>;
    }
    case "symbol":
      return <SymbolInline symbolId={node.symbol_id} altText={node.alt_text} />;
    case "glossary_ref":
      return (
        <span
          className="inline-glossary-ref"
          data-term-id={node.term_id}
          title={node.surface_form}
        >
          {node.surface_form}
        </span>
      );
    default:
      return assertNever(node);
  }
}

interface InlineListProps {
  nodes: BundleInlineNode[];
}

/** Get the display text of a node (for spacing logic). */
function nodeText(node: BundleInlineNode): string {
  if (node.kind === "text") return node.ru_text ?? node.text;
  if (node.kind === "glossary_ref") return node.surface_form;
  return "";
}

export function InlineList({ nodes }: InlineListProps) {
  return (
    <>
      {nodes.map((node, i) => {
        // Insert space between adjacent nodes when neither boundary has whitespace
        let spacer: React.ReactNode = null;
        if (i > 0) {
          const prevText = nodeText(nodes[i - 1]);
          const curText = nodeText(node);
          const prevEnds = /\s$/.test(prevText);
          const curStarts = /^\s/.test(curText);
          if (!prevEnds && !curStarts && prevText && curText) {
            spacer = " ";
          }
        }
        return (
          <span key={i}>
            {spacer}
            <InlineRenderer node={node} />
          </span>
        );
      })}
    </>
  );
}
