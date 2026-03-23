import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type {
  BundleBlock,
  BundleCalloutBlock,
  BundleCaptionBlock,
  BundleDividerBlock,
  BundleFigureBlock,
  BundleHeadingBlock,
  BundleListBlock,
  BundleListItemBlock,
  BundleParagraphBlock,
  BundleTableBlock,
  BundleTextRun,
} from "@aeon-reader/contracts";
import { BlockRenderer } from "@/components/BlockRenderer";

function textNode(text: string): BundleTextRun {
  return { kind: "text", text, ru_text: null, bold: false, italic: false, monospace: false };
}

describe("BlockRenderer", () => {
  describe("heading", () => {
    it("renders the correct heading level", () => {
      const block: BundleHeadingBlock = {
        kind: "heading",
        block_id: "h-1",
        level: 2,
        content: [textNode("Chapter Title")],
        anchor: "",
      };
      const { container } = render(<BlockRenderer block={block} />);
      const heading = container.querySelector("h2");
      expect(heading).not.toBeNull();
      expect(heading!.textContent).toContain("Chapter Title");
      expect(heading!.className).toBe("block-heading");
    });

    it("uses anchor as id when present", () => {
      const block: BundleHeadingBlock = {
        kind: "heading",
        block_id: "h-1",
        level: 1,
        content: [textNode("Title")],
        anchor: "my-anchor",
      };
      const { container } = render(<BlockRenderer block={block} />);
      expect(container.querySelector("#my-anchor")).not.toBeNull();
    });

    it("falls back to block_id when anchor is empty", () => {
      const block: BundleHeadingBlock = {
        kind: "heading",
        block_id: "h-1",
        level: 1,
        content: [textNode("Title")],
        anchor: "",
      };
      const { container } = render(<BlockRenderer block={block} />);
      expect(container.querySelector("#h-1")).not.toBeNull();
    });

    it("clamps level to h6 maximum", () => {
      const block: BundleHeadingBlock = {
        kind: "heading",
        block_id: "h-1",
        level: 9,
        content: [textNode("Deep")],
        anchor: "",
      };
      const { container } = render(<BlockRenderer block={block} />);
      expect(container.querySelector("h6")).not.toBeNull();
    });

    it("renders level 1 as h1", () => {
      const block: BundleHeadingBlock = {
        kind: "heading",
        block_id: "h-1",
        level: 1,
        content: [textNode("Top")],
        anchor: "",
      };
      const { container } = render(<BlockRenderer block={block} />);
      expect(container.querySelector("h1")).not.toBeNull();
    });
  });

  describe("paragraph", () => {
    it("renders a <p> with content", () => {
      const block: BundleParagraphBlock = {
        kind: "paragraph",
        block_id: "p-1",
        content: [textNode("Some text")],
      };
      const { container } = render(<BlockRenderer block={block} />);
      const p = container.querySelector("p#p-1");
      expect(p).not.toBeNull();
      expect(p!.className).toBe("block-paragraph");
      expect(p!.textContent).toContain("Some text");
    });
  });

  describe("list", () => {
    it("renders an ordered list as <ol>", () => {
      const block: BundleListBlock = {
        kind: "list",
        block_id: "ol-1",
        list_type: "ordered",
        items: [
          { kind: "list_item", block_id: "li-1", bullet: "1.", content: [textNode("First")] },
          { kind: "list_item", block_id: "li-2", bullet: "2.", content: [textNode("Second")] },
        ],
      };
      const { container } = render(<BlockRenderer block={block} />);
      const ol = container.querySelector("ol#ol-1");
      expect(ol).not.toBeNull();
      expect(ol!.className).toContain("block-list-ordered");
      expect(ol!.querySelectorAll("li").length).toBe(2);
    });

    it("renders an unordered list as <ul>", () => {
      const block: BundleListBlock = {
        kind: "list",
        block_id: "ul-1",
        list_type: "unordered",
        items: [
          { kind: "list_item", block_id: "li-1", bullet: "-", content: [textNode("Item")] },
        ],
      };
      const { container } = render(<BlockRenderer block={block} />);
      const ul = container.querySelector("ul#ul-1");
      expect(ul).not.toBeNull();
      expect(ul!.className).toContain("block-list-unordered");
    });

    it("assigns block_id to each list item", () => {
      const block: BundleListBlock = {
        kind: "list",
        block_id: "ul-1",
        list_type: "unordered",
        items: [
          { kind: "list_item", block_id: "li-abc", bullet: "-", content: [textNode("A")] },
        ],
      };
      const { container } = render(<BlockRenderer block={block} />);
      expect(container.querySelector("li#li-abc")).not.toBeNull();
    });
  });

  describe("list_item (standalone)", () => {
    it("renders a standalone list item as <div>", () => {
      const block: BundleListItemBlock = {
        kind: "list_item",
        block_id: "li-s-1",
        bullet: "-",
        content: [textNode("Standalone item")],
      };
      const { container } = render(<BlockRenderer block={block} />);
      const div = container.querySelector("div#li-s-1");
      expect(div).not.toBeNull();
      expect(div!.className).toBe("block-list-item-standalone");
    });
  });

  describe("figure", () => {
    it("renders a <figure> with lazy-loaded <img>", () => {
      const block: BundleFigureBlock = {
        kind: "figure",
        block_id: "fig-1",
        asset_ref: "/images/hero.png",
        alt_text: "Hero image",
        caption_block_id: null,
      };
      const { container } = render(<BlockRenderer block={block} />);
      const figure = container.querySelector("figure#fig-1");
      expect(figure).not.toBeNull();
      const img = figure!.querySelector("img");
      expect(img).not.toBeNull();
      expect(img!.getAttribute("src")).toBe("/images/hero.png");
      expect(img!.getAttribute("alt")).toBe("Hero image");
      expect(img!.getAttribute("loading")).toBe("lazy");
    });

    it("renders figure without img when asset_ref is empty", () => {
      const block: BundleFigureBlock = {
        kind: "figure",
        block_id: "fig-2",
        asset_ref: "",
        alt_text: "",
        caption_block_id: null,
      };
      const { container } = render(<BlockRenderer block={block} />);
      const figure = container.querySelector("figure#fig-2");
      expect(figure).not.toBeNull();
      expect(figure!.querySelector("img")).toBeNull();
    });
  });

  describe("caption", () => {
    it("renders a <figcaption>", () => {
      const block: BundleCaptionBlock = {
        kind: "caption",
        block_id: "cap-1",
        content: [textNode("Figure 1")],
        parent_block_id: null,
      };
      const { container } = render(<BlockRenderer block={block} />);
      const figcaption = container.querySelector("figcaption#cap-1");
      expect(figcaption).not.toBeNull();
      expect(figcaption!.className).toBe("block-caption");
      expect(figcaption!.textContent).toContain("Figure 1");
    });
  });

  describe("table", () => {
    it("renders a placeholder when cells are empty", () => {
      const block: BundleTableBlock = {
        kind: "table",
        block_id: "tbl-1",
        rows: 3,
        cols: 5,
        cells: [],
      };
      const { container } = render(<BlockRenderer block={block} />);
      const div = container.querySelector("div#tbl-1");
      expect(div).not.toBeNull();
      expect(div!.className).toBe("block-table-placeholder");
      expect(div!.textContent).toContain("3");
      expect(div!.textContent).toContain("5");
    });

    it("renders an actual table when cells are present", () => {
      const block: BundleTableBlock = {
        kind: "table",
        block_id: "tbl-2",
        rows: 2,
        cols: 2,
        cells: [
          { row: 0, col: 0, text: "Name", row_span: 1, col_span: 1 },
          { row: 0, col: 1, text: "Value", row_span: 1, col_span: 1 },
          { row: 1, col: 0, text: "HP", row_span: 1, col_span: 1 },
          { row: 1, col: 1, text: "10", row_span: 1, col_span: 1 },
        ],
      };
      const { container } = render(<BlockRenderer block={block} />);
      const table = container.querySelector("table.block-table");
      expect(table).not.toBeNull();
      const ths = table!.querySelectorAll("th");
      expect(ths).toHaveLength(2);
      expect(ths[0].textContent).toBe("Name");
      const tds = table!.querySelectorAll("td");
      expect(tds).toHaveLength(2);
      expect(tds[0].textContent).toBe("HP");
      expect(tds[1].textContent).toBe("10");
    });
  });

  describe("callout", () => {
    it.each(["note", "warning", "info", "tip"] as const)(
      "renders %s variant with correct class",
      (variant) => {
        const block: BundleCalloutBlock = {
          kind: "callout",
          block_id: `call-${variant}`,
          callout_type: variant,
          content: [textNode("Content")],
        };
        const { container } = render(<BlockRenderer block={block} />);
        const aside = container.querySelector(`aside#call-${variant}`);
        expect(aside).not.toBeNull();
        expect(aside!.getAttribute("role")).toBe("note");
        expect(aside!.className).toContain("block-callout");
        expect(aside!.className).toContain(`block-callout-${variant}`);
      },
    );
  });

  describe("divider", () => {
    it("renders an <hr>", () => {
      const block: BundleDividerBlock = {
        kind: "divider",
        block_id: "div-1",
      };
      const { container } = render(<BlockRenderer block={block} />);
      const hr = container.querySelector("hr#div-1");
      expect(hr).not.toBeNull();
      expect(hr!.className).toBe("block-divider");
    });
  });
});
