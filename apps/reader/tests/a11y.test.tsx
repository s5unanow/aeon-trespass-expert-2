import path from "node:path";
import fs from "node:fs";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FigureLightbox } from "@/components/FigureLightbox";
import { trapFocus } from "@/lib/a11y";

// Mock trapFocus — real implementation needs a live DOM with focusable elements
vi.mock("@/lib/a11y", () => ({
  trapFocus: vi.fn(() => vi.fn()),
}));

describe("FigureLightbox", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <FigureLightbox src="/img.png" alt="test" open={false} onClose={vi.fn()} />
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders dialog with aria attributes when open", () => {
    const { container } = render(
      <FigureLightbox src="/img.png" alt="test" open={true} onClose={vi.fn()} />
    );
    const dialog = container.querySelector("[role='dialog']");
    expect(dialog).not.toBeNull();
    expect(dialog!.getAttribute("aria-label")).toBe("Image viewer");
    expect(dialog!.getAttribute("aria-modal")).toBe("true");
  });

  it("renders close button with aria-label", () => {
    const { container } = render(
      <FigureLightbox src="/img.png" alt="test" open={true} onClose={vi.fn()} />
    );
    const btn = container.querySelector("button[aria-label='Close lightbox']");
    expect(btn).not.toBeNull();
  });

  it("activates focus trap when open", () => {
    render(
      <FigureLightbox src="/img.png" alt="test" open={true} onClose={vi.fn()} />
    );
    expect(trapFocus).toHaveBeenCalled();
  });
});

describe("SearchDialog a11y", () => {
  // SearchDialog depends on Pagefind which isn't available in test env,
  // so we verify the ARIA roles via a static check on the source
  it("uses role=list and role=listitem (not listbox/option)", () => {
    const src = fs.readFileSync(
      path.resolve(__dirname, "../components/SearchDialog.tsx"),
      "utf-8"
    );
    expect(src).toContain('role="list"');
    expect(src).toContain('role="listitem"');
    expect(src).not.toContain('role="listbox"');
    expect(src).not.toContain('role="option"');
  });
});

describe("global styles", () => {
  it("includes skip-link and focus-visible styles", () => {
    const css = fs.readFileSync(
      path.resolve(__dirname, "../styles/globals.css"),
      "utf-8"
    );
    expect(css).toContain(".skip-link");
    expect(css).toContain(":focus-visible");
  });
});
