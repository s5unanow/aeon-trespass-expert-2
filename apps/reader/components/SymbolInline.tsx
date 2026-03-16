/**
 * SymbolInline — renders game symbols as inline icons.
 */

interface SymbolInlineProps {
  symbolId: string;
  altText: string;
}

export function SymbolInline({ symbolId, altText }: SymbolInlineProps) {
  return (
    <span
      className="inline-symbol"
      data-symbol-id={symbolId}
      role="img"
      aria-label={altText || symbolId}
    >
      [{altText || symbolId}]
    </span>
  );
}
