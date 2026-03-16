/**
 * FigureLightbox — lightbox overlay for figure images.
 *
 * Client component that opens when a figure is clicked.
 */

"use client";

import { useCallback, useEffect } from "react";

interface FigureLightboxProps {
  src: string;
  alt: string;
  open: boolean;
  onClose: () => void;
}

export function FigureLightbox({ src, alt, open, onClose }: FigureLightboxProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div
      className="lightbox-overlay"
      onClick={onClose}
      role="dialog"
      aria-label="Image viewer"
    >
      <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
        <img src={src} alt={alt} className="lightbox-image" />
        <button
          className="lightbox-close"
          onClick={onClose}
          type="button"
          aria-label="Close lightbox"
        >
          &times;
        </button>
      </div>
    </div>
  );
}
