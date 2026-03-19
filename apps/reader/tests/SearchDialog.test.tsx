import { render, fireEvent, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { PagefindResult } from "@/lib/pagefind";
import { SearchDialog } from "@/components/SearchDialog";

const mockSearch = vi.fn<(q: string) => Promise<PagefindResult[]>>();
vi.mock("@/lib/pagefind", () => ({
  search: (...args: unknown[]) => mockSearch(...(args as [string])),
}));

vi.mock("@/lib/a11y", () => ({
  trapFocus: vi.fn(() => vi.fn()),
}));

beforeEach(() => {
  mockSearch.mockReset();
  mockSearch.mockResolvedValue([]);
});

describe("SearchDialog", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <SearchDialog open={false} onClose={vi.fn()} />
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders dialog when open", () => {
    const { container } = render(
      <SearchDialog open={true} onClose={vi.fn()} />
    );
    const dialog = container.querySelector("dialog");
    expect(dialog).not.toBeNull();
    expect(dialog!.getAttribute("aria-label")).toBe("Search");
  });

  it("focuses input on open", () => {
    const { container } = render(
      <SearchDialog open={true} onClose={vi.fn()} />
    );
    const input = container.querySelector("input[type='search']");
    expect(input).not.toBeNull();
    expect(document.activeElement).toBe(input);
  });

  it("calls onClose when Escape is pressed", () => {
    const onClose = vi.fn();
    render(<SearchDialog open={true} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not call onClose on Escape when closed", () => {
    const onClose = vi.fn();
    render(<SearchDialog open={false} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when overlay is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <SearchDialog open={true} onClose={onClose} />
    );
    const overlay = container.querySelector(".search-overlay");
    fireEvent.click(overlay!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close when dialog body is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <SearchDialog open={true} onClose={onClose} />
    );
    const dialog = container.querySelector("dialog");
    fireEvent.click(dialog!);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when close button is clicked", () => {
    const onClose = vi.fn();
    const { container } = render(
      <SearchDialog open={true} onClose={onClose} />
    );
    const btn = container.querySelector("button[aria-label='Close search']");
    fireEvent.click(btn!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("clears query and results when dialog closes", async () => {
    const { container, rerender } = render(
      <SearchDialog open={true} onClose={vi.fn()} />
    );
    const input = container.querySelector("input")!;

    // Type a query
    await act(async () => {
      fireEvent.change(input, { target: { value: "titan" } });
    });
    expect(input.value).toBe("titan");

    // Close then reopen
    await act(async () => {
      rerender(<SearchDialog open={false} onClose={vi.fn()} />);
    });
    await act(async () => {
      rerender(<SearchDialog open={true} onClose={vi.fn()} />);
    });

    const newInput = container.querySelector("input")!;
    expect(newInput.value).toBe("");
  });

  it("shows loading state while searching", async () => {
    let resolveSearch!: (value: PagefindResult[]) => void;
    mockSearch.mockReturnValue(
      new Promise((resolve) => {
        resolveSearch = resolve;
      })
    );

    const { container } = render(
      <SearchDialog open={true} onClose={vi.fn()} />
    );
    const input = container.querySelector("input")!;

    await act(async () => {
      fireEvent.change(input, { target: { value: "titan" } });
    });

    expect(container.querySelector(".search-loading")).not.toBeNull();
    expect(container.textContent).toContain("Searching...");

    await act(async () => {
      resolveSearch([]);
    });

    expect(container.querySelector(".search-loading")).toBeNull();
  });

  it("shows empty state when no results found", async () => {
    mockSearch.mockResolvedValue([]);

    const { container } = render(
      <SearchDialog open={true} onClose={vi.fn()} />
    );
    const input = container.querySelector("input")!;

    await act(async () => {
      fireEvent.change(input, { target: { value: "nonexistent" } });
    });

    expect(container.querySelector(".search-empty")).not.toBeNull();
    expect(container.textContent).toContain("No results found.");
  });

  it("does not show empty state when query is blank", async () => {
    const { container } = render(
      <SearchDialog open={true} onClose={vi.fn()} />
    );
    const input = container.querySelector("input")!;

    await act(async () => {
      fireEvent.change(input, { target: { value: "" } });
    });

    expect(container.querySelector(".search-empty")).toBeNull();
    expect(mockSearch).not.toHaveBeenCalled();
  });

  it("renders search results", async () => {
    const results: PagefindResult[] = [
      { url: "/docs/core/page/1", excerpt: "The <mark>Titan</mark> rises" },
      { url: "/docs/core/page/2", excerpt: "An <mark>ancient</mark> story" },
    ];
    mockSearch.mockResolvedValue(results);

    const { container } = render(
      <SearchDialog open={true} onClose={vi.fn()} />
    );
    const input = container.querySelector("input")!;

    await act(async () => {
      fireEvent.change(input, { target: { value: "titan" } });
    });

    const links = container.querySelectorAll("a.search-result");
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute("href")).toBe("/docs/core/page/1");
    expect(links[1].getAttribute("href")).toBe("/docs/core/page/2");
    expect(links[0].textContent).toContain("Titan");
  });

  it("clears results when query is emptied", async () => {
    mockSearch.mockResolvedValue([
      { url: "/docs/core/page/1", excerpt: "result" },
    ]);

    const { container } = render(
      <SearchDialog open={true} onClose={vi.fn()} />
    );
    const input = container.querySelector("input")!;

    await act(async () => {
      fireEvent.change(input, { target: { value: "titan" } });
    });
    expect(container.querySelectorAll("a.search-result")).toHaveLength(1);

    await act(async () => {
      fireEvent.change(input, { target: { value: "" } });
    });
    expect(container.querySelectorAll("a.search-result")).toHaveLength(0);
    expect(container.querySelector(".search-empty")).toBeNull();
  });
});
