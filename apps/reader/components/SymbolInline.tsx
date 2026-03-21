/**
 * SymbolInline — renders game symbols as inline SVG icons.
 *
 * When svg_data is available, renders the SVG inline with a tooltip.
 * Falls back to bracketed text placeholder when no SVG is provided.
 *
 * The anchorType prop controls CSS class for placement semantics:
 * - "inline" (default): rendered within text flow
 * - "line_prefix": rendered before the line content
 * - "cell_local": scoped to a table cell
 * - "block_attached": attached to a parent block
 * - "region_decoration": decorative element for a region
 */

import type { SymbolAnchorType } from "@aeon-reader/contracts";

interface SymbolInlineProps {
  symbolId: string;
  altText: string;
  label: string;
  svgData: string;
  anchorType: SymbolAnchorType;
}

export function SymbolInline({ symbolId, altText, label, svgData, anchorType }: SymbolInlineProps) {
  const displayLabel = altText || label || symbolId;
  const anchorClass = anchorType !== "inline" ? ` inline-symbol--${anchorType.replace(/_/g, "-")}` : "";

  if (svgData) {
    return (
      <span
        className={`inline-symbol inline-symbol--svg${anchorClass}`}
        data-symbol-id={symbolId}
        data-anchor-type={anchorType}
        role="img"
        aria-label={displayLabel}
        title={displayLabel}
        dangerouslySetInnerHTML={{ __html: svgData }}
      />
    );
  }

  return (
    <span
      className={`inline-symbol${anchorClass}`}
      data-symbol-id={symbolId}
      data-anchor-type={anchorType}
      role="img"
      aria-label={displayLabel}
      title={displayLabel}
    >
      [{displayLabel}]
    </span>
  );
}
