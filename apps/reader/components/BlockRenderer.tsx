/**
 * BlockRenderer — renders a block union into semantic HTML.
 *
 * Exhaustive switch over BundleBlock kinds with assertNever fallback.
 * No markdown, no HTML injection — deterministic rendering from typed unions.
 */

import type { BundleBlock } from "@aeon-reader/contracts";
import { assertNever } from "@/lib/assertNever";
import { InlineList } from "./InlineRenderer";

interface BlockRendererProps {
  block: BundleBlock;
}

export function BlockRenderer({ block }: BlockRendererProps) {
  switch (block.kind) {
    case "heading": {
      const Tag = `h${Math.min(block.level, 6)}` as
        | "h1"
        | "h2"
        | "h3"
        | "h4"
        | "h5"
        | "h6";
      return (
        <Tag id={block.anchor || block.block_id} className="block-heading">
          <InlineList nodes={block.content} />
        </Tag>
      );
    }
    case "paragraph":
      return (
        <p id={block.block_id} className="block-paragraph">
          <InlineList nodes={block.content} />
        </p>
      );
    case "list":
      if (block.list_type === "ordered") {
        return (
          <ol id={block.block_id} className="block-list block-list-ordered">
            {block.items.map((item) => (
              <li key={item.block_id} id={item.block_id} className="block-list-item">
                <InlineList nodes={item.content} />
              </li>
            ))}
          </ol>
        );
      }
      return (
        <ul id={block.block_id} className="block-list block-list-unordered">
          {block.items.map((item) => (
            <li key={item.block_id} id={item.block_id} className="block-list-item">
              <InlineList nodes={item.content} />
            </li>
          ))}
        </ul>
      );
    case "list_item":
      return (
        <div id={block.block_id} className="block-list-item-standalone">
          <InlineList nodes={block.content} />
        </div>
      );
    case "figure":
      return (
        <figure id={block.block_id} className="block-figure">
          {block.asset_ref && (
            <img src={block.asset_ref} alt={block.alt_text} loading="lazy" />
          )}
        </figure>
      );
    case "caption":
      return (
        <figcaption id={block.block_id} className="block-caption">
          <InlineList nodes={block.content} />
        </figcaption>
      );
    case "table": {
      if (block.cells.length === 0) {
        return (
          <div id={block.block_id} className="block-table-placeholder">
            <p>
              Table ({block.rows}&times;{block.cols})
            </p>
          </div>
        );
      }
      const rows: string[][][] = [];
      for (const cell of block.cells) {
        while (rows.length <= cell.row) rows.push([]);
        while (rows[cell.row].length <= cell.col) rows[cell.row].push([]);
        rows[cell.row][cell.col] = [cell.text];
      }
      return (
        <div id={block.block_id} className="block-table-wrap">
          <table className="block-table">
            <tbody>
              {rows.map((row, rIdx) => (
                <tr key={rIdx}>
                  {row.map((cellArr, cIdx) => {
                    const cellText = cellArr[0] ?? "";
                    const isHeader = rIdx === 0;
                    const Tag = isHeader ? "th" : "td";
                    return <Tag key={cIdx}>{cellText}</Tag>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    case "callout":
      return (
        <aside
          id={block.block_id}
          className={`block-callout block-callout-${block.callout_type}`}
          role="note"
        >
          <InlineList nodes={block.content} />
        </aside>
      );
    case "divider":
      return <hr id={block.block_id} className="block-divider" />;
    default:
      return assertNever(block);
  }
}
