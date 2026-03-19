import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type {
  BundleGlossaryRef,
  BundleInlineNode,
  BundleSymbolRef,
  BundleTextRun,
} from "@aeon-reader/contracts";
import { InlineRenderer, InlineList } from "@/components/InlineRenderer";

describe("InlineRenderer", () => {
  describe("text node", () => {
    it("renders plain text", () => {
      const node: BundleTextRun = {
        kind: "text",
        text: "Hello",
        ru_text: null,
        bold: false,
        italic: false,
        monospace: false,
      };
      const { container } = render(<InlineRenderer node={node} />);
      const span = container.querySelector(".inline-text");
      expect(span).not.toBeNull();
      expect(span!.textContent).toBe("Hello");
    });

    it("prefers ru_text over text", () => {
      const node: BundleTextRun = {
        kind: "text",
        text: "Hello",
        ru_text: "Привет",
        bold: false,
        italic: false,
        monospace: false,
      };
      const { container } = render(<InlineRenderer node={node} />);
      expect(container.textContent).toBe("Привет");
    });

    it("uses empty ru_text as-is (does not fall back to text)", () => {
      const node: BundleTextRun = {
        kind: "text",
        text: "English",
        ru_text: "",
        bold: false,
        italic: false,
        monospace: false,
      };
      const { container } = render(<InlineRenderer node={node} />);
      // Nullish coalescing: "" is not null, so it stays ""
      expect(container.querySelector(".inline-text")!.textContent).toBe("");
    });

    it("renders bold text with <strong>", () => {
      const node: BundleTextRun = {
        kind: "text",
        text: "Bold",
        ru_text: null,
        bold: true,
        italic: false,
        monospace: false,
      };
      const { container } = render(<InlineRenderer node={node} />);
      expect(container.querySelector("strong")).not.toBeNull();
      expect(container.querySelector("strong")!.textContent).toBe("Bold");
    });

    it("renders italic text with <em>", () => {
      const node: BundleTextRun = {
        kind: "text",
        text: "Italic",
        ru_text: null,
        bold: false,
        italic: true,
        monospace: false,
      };
      const { container } = render(<InlineRenderer node={node} />);
      expect(container.querySelector("em")).not.toBeNull();
    });

    it("renders monospace text with <code>", () => {
      const node: BundleTextRun = {
        kind: "text",
        text: "code()",
        ru_text: null,
        bold: false,
        italic: false,
        monospace: true,
      };
      const { container } = render(<InlineRenderer node={node} />);
      expect(container.querySelector("code")).not.toBeNull();
    });

    it("nests bold + italic + monospace", () => {
      const node: BundleTextRun = {
        kind: "text",
        text: "all",
        ru_text: null,
        bold: true,
        italic: true,
        monospace: true,
      };
      const { container } = render(<InlineRenderer node={node} />);
      // Application order: bold first, italic wraps it, monospace wraps that
      // Result: <code><em><strong>all</strong></em></code>
      const code = container.querySelector("code");
      expect(code).not.toBeNull();
      expect(code!.querySelector("em")).not.toBeNull();
      expect(code!.querySelector("em strong")).not.toBeNull();
    });
  });

  describe("symbol node", () => {
    it("renders text fallback when no svg_data", () => {
      const node: BundleSymbolRef = {
        kind: "symbol",
        symbol_id: "action-point",
        alt_text: "AP",
        label: "Action Point",
        svg_data: "",
      };
      const { container } = render(<InlineRenderer node={node} />);
      const symbol = container.querySelector(".inline-symbol");
      expect(symbol).not.toBeNull();
      expect(symbol!.getAttribute("data-symbol-id")).toBe("action-point");
      expect(symbol!.getAttribute("role")).toBe("img");
      expect(symbol!.getAttribute("aria-label")).toBe("AP");
      expect(symbol!.getAttribute("title")).toBe("AP");
      expect(symbol!.textContent).toBe("[AP]");
    });

    it("renders inline SVG when svg_data is provided", () => {
      const svgContent = '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6"/></svg>';
      const node: BundleSymbolRef = {
        kind: "symbol",
        symbol_id: "action-point",
        alt_text: "AP",
        label: "Action Point",
        svg_data: svgContent,
      };
      const { container } = render(<InlineRenderer node={node} />);
      const symbol = container.querySelector(".inline-symbol--svg");
      expect(symbol).not.toBeNull();
      expect(symbol!.getAttribute("data-symbol-id")).toBe("action-point");
      expect(symbol!.getAttribute("title")).toBe("AP");
      expect(symbol!.querySelector("svg")).not.toBeNull();
    });

    it("uses label as fallback when alt_text is empty", () => {
      const node: BundleSymbolRef = {
        kind: "symbol",
        symbol_id: "action-point",
        alt_text: "",
        label: "Action Point",
        svg_data: "",
      };
      const { container } = render(<InlineRenderer node={node} />);
      const symbol = container.querySelector(".inline-symbol");
      expect(symbol!.getAttribute("aria-label")).toBe("Action Point");
      expect(symbol!.textContent).toBe("[Action Point]");
    });

    it("uses symbolId as last-resort fallback", () => {
      const node: BundleSymbolRef = {
        kind: "symbol",
        symbol_id: "action-point",
        alt_text: "",
        label: "",
        svg_data: "",
      };
      const { container } = render(<InlineRenderer node={node} />);
      const symbol = container.querySelector(".inline-symbol");
      expect(symbol!.getAttribute("aria-label")).toBe("action-point");
      expect(symbol!.textContent).toBe("[action-point]");
    });
  });

  describe("glossary_ref node", () => {
    it("renders with ru_surface_form when available", () => {
      const node: BundleGlossaryRef = {
        kind: "glossary_ref",
        term_id: "term-1",
        surface_form: "Argonaut",
        ru_surface_form: "Аргонавт",
      };
      const { container } = render(<InlineRenderer node={node} />);
      const span = container.querySelector(".inline-glossary-ref");
      expect(span).not.toBeNull();
      expect(span!.getAttribute("data-term-id")).toBe("term-1");
      expect(span!.getAttribute("title")).toBe("Argonaut");
      expect(span!.textContent).toBe("Аргонавт");
    });

    it("falls back to surface_form when ru_surface_form is empty", () => {
      const node: BundleGlossaryRef = {
        kind: "glossary_ref",
        term_id: "term-2",
        surface_form: "Titan",
        ru_surface_form: "",
      };
      const { container } = render(<InlineRenderer node={node} />);
      expect(container.querySelector(".inline-glossary-ref")!.textContent).toBe("Titan");
    });
  });
});

describe("InlineList", () => {
  it("renders multiple nodes", () => {
    const nodes: BundleInlineNode[] = [
      { kind: "text", text: "Hello", ru_text: null, bold: false, italic: false, monospace: false },
      { kind: "text", text: "world", ru_text: null, bold: false, italic: false, monospace: false },
    ];
    const { container } = render(<InlineList nodes={nodes} />);
    expect(container.textContent).toContain("Hello");
    expect(container.textContent).toContain("world");
  });

  it("inserts space between adjacent text nodes without whitespace", () => {
    const nodes: BundleInlineNode[] = [
      { kind: "text", text: "Hello", ru_text: null, bold: false, italic: false, monospace: false },
      { kind: "text", text: "world", ru_text: null, bold: false, italic: false, monospace: false },
    ];
    const { container } = render(<InlineList nodes={nodes} />);
    expect(container.textContent).toBe("Hello world");
  });

  it("does not insert space when previous node ends with whitespace", () => {
    const nodes: BundleInlineNode[] = [
      { kind: "text", text: "Hello ", ru_text: null, bold: false, italic: false, monospace: false },
      { kind: "text", text: "world", ru_text: null, bold: false, italic: false, monospace: false },
    ];
    const { container } = render(<InlineList nodes={nodes} />);
    expect(container.textContent).toBe("Hello world");
  });

  it("does not insert space when current node starts with whitespace", () => {
    const nodes: BundleInlineNode[] = [
      { kind: "text", text: "Hello", ru_text: null, bold: false, italic: false, monospace: false },
      { kind: "text", text: " world", ru_text: null, bold: false, italic: false, monospace: false },
    ];
    const { container } = render(<InlineList nodes={nodes} />);
    expect(container.textContent).toBe("Hello world");
  });

  it("inserts space between text and glossary_ref nodes", () => {
    const nodes: BundleInlineNode[] = [
      { kind: "text", text: "The", ru_text: null, bold: false, italic: false, monospace: false },
      { kind: "glossary_ref", term_id: "t-1", surface_form: "Titan", ru_surface_form: "Титан" },
    ];
    const { container } = render(<InlineList nodes={nodes} />);
    expect(container.textContent).toBe("The Титан");
  });

  it("does not insert space adjacent to symbol nodes (empty nodeText)", () => {
    const nodes: BundleInlineNode[] = [
      { kind: "text", text: "Cost:", ru_text: null, bold: false, italic: false, monospace: false },
      { kind: "symbol", symbol_id: "ap", alt_text: "AP", label: "", svg_data: "" },
    ];
    const { container } = render(<InlineList nodes={nodes} />);
    // Symbol nodeText returns "" so no spacer is inserted
    expect(container.textContent).toBe("Cost:[AP]");
  });

  it("renders empty list without errors", () => {
    const { container } = render(<InlineList nodes={[]} />);
    expect(container.textContent).toBe("");
  });
});
