/**
 * FigureLightbox — lightbox overlay for figure images.
 *
 * Client component that opens when a figure is clicked.
 */

"use client";

import { useCallback, useEffect, useRef } from "react";
import { trapFocus } from "@/lib/a11y";

interface FigureLightboxProps {
  src: string;
  alt: string;
  open: boolean;
  onClose: () => void;
}

export function FigureLightbox({ src, alt, open, onClose }: FigureLightboxProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (open) {
      closeRef.current?.focus();
      document.addEventListener("keydown", handleKeyDown);
      const overlay = overlayRef.current;
      const cleanupTrap = overlay ? trapFocus(overlay) : undefined;
      return () => {
        document.removeEventListener("keydown", handleKeyDown);
        cleanupTrap?.();
      };
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className="lightbox-overlay"
      onClick={onClose}
      role="dialog"
      aria-label="Image viewer"
      aria-modal="true"
    >
      <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
        <img src={src} alt={alt} className="lightbox-image" />
        <button
          ref={closeRef}
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
