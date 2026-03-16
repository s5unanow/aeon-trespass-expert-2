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

export function InlineList({ nodes }: InlineListProps) {
  return (
    <>
      {nodes.map((node, i) => (
        <InlineRenderer key={i} node={node} />
      ))}
    </>
  );
}
