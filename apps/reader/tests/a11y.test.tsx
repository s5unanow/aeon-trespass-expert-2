import path from "node:path";
import fs from "node:fs";
import { render, fireEvent } from "@testing-library/react";
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
  it("uses role=list for results and role=listitem for each result", async () => {
    // Mock pagefind search to return results for role verification
    const mockSearch = vi.fn().mockResolvedValue([
      { url: "/docs/core/page/1", excerpt: "A <mark>result</mark>" },
    ]);
    vi.doMock("@/lib/pagefind", () => ({ search: mockSearch }));

    const { SearchDialog } = await import("@/components/SearchDialog");
    const { act } = await import("@testing-library/react");

    const { container } = render(
      <SearchDialog open={true} onClose={vi.fn()} />
    );

    const resultsList = container.querySelector("[role='list']");
    expect(resultsList).not.toBeNull();
    expect(resultsList!.getAttribute("aria-label")).toBe("Search results");

    // Trigger a search to get listitem roles
    const input = container.querySelector("input")!;
    await act(async () => {
      fireEvent.change(input, { target: { value: "test" } });
    });

    const items = container.querySelectorAll("[role='listitem']");
    expect(items.length).toBeGreaterThan(0);

    // Ensure no listbox/option roles are used (not appropriate for link lists)
    expect(container.querySelector("[role='listbox']")).toBeNull();
    expect(container.querySelector("[role='option']")).toBeNull();
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
