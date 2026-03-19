/**
 * SymbolInline — renders game symbols as inline SVG icons.
 *
 * When svg_data is available, renders the SVG inline with a tooltip.
 * Falls back to bracketed text placeholder when no SVG is provided.
 */

interface SymbolInlineProps {
  symbolId: string;
  altText: string;
  label: string;
  svgData: string;
}

export function SymbolInline({ symbolId, altText, label, svgData }: SymbolInlineProps) {
  const displayLabel = altText || label || symbolId;

  if (svgData) {
    return (
      <span
        className="inline-symbol inline-symbol--svg"
        data-symbol-id={symbolId}
        role="img"
        aria-label={displayLabel}
        title={displayLabel}
        dangerouslySetInnerHTML={{ __html: svgData }}
      />
    );
  }

  return (
    <span
      className="inline-symbol"
      data-symbol-id={symbolId}
      role="img"
      aria-label={displayLabel}
      title={displayLabel}
    >
      [{displayLabel}]
    </span>
  );
}
