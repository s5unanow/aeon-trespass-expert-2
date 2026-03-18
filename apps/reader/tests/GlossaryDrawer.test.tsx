import { render, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BundleGlossaryEntry } from "@aeon-reader/contracts";
import { GlossaryDrawer } from "@/components/GlossaryDrawer";

vi.mock("@/lib/a11y", () => ({
  trapFocus: vi.fn(() => vi.fn()),
}));

const entries: BundleGlossaryEntry[] = [
  {
    term_id: "titan",
    en_canonical: "Titan",
    ru_preferred: "Титан",
    definition_ru: "Древнее существо огромной силы.",
    definition_en: "An ancient being of great power.",
  },
  {
    term_id: "argonaut",
    en_canonical: "Argonaut",
    ru_preferred: "Аргонавт",
    definition_ru: "",
    definition_en: null,
  },
];

describe("GlossaryDrawer", () => {
  it("renders nothing when no term is active", () => {
    const { container } = render(<GlossaryDrawer entries={entries} />);
    expect(container.innerHTML).toBe("");
  });

  it("opens when a glossary ref is clicked", () => {
    const { container } = render(
      <div>
        <span className="inline-glossary-ref" data-term-id="titan">
          Титан
        </span>
        <GlossaryDrawer entries={entries} />
      </div>
    );

    const ref = container.querySelector(".inline-glossary-ref")!;
    fireEvent.click(ref);

    const drawer = container.querySelector(".glossary-drawer");
    expect(drawer).not.toBeNull();
    expect(drawer!.getAttribute("role")).toBe("dialog");
    expect(drawer!.getAttribute("aria-modal")).toBe("true");
  });

  it("shows term details when opened", () => {
    const { container } = render(
      <div>
        <span className="inline-glossary-ref" data-term-id="titan">
          Титан
        </span>
        <GlossaryDrawer entries={entries} />
      </div>
    );

    fireEvent.click(container.querySelector(".inline-glossary-ref")!);

    expect(container.textContent).toContain("Титан");
    expect(container.textContent).toContain("Titan");
    expect(container.textContent).toContain("Древнее существо огромной силы.");
    expect(container.textContent).toContain("An ancient being of great power.");
  });

  it("closes when close button is clicked", () => {
    const { container } = render(
      <div>
        <span className="inline-glossary-ref" data-term-id="titan">
          Титан
        </span>
        <GlossaryDrawer entries={entries} />
      </div>
    );

    fireEvent.click(container.querySelector(".inline-glossary-ref")!);
    expect(container.querySelector(".glossary-drawer")).not.toBeNull();

    fireEvent.click(container.querySelector(".glossary-drawer-close")!);
    expect(container.querySelector(".glossary-drawer")).toBeNull();
  });

  it("closes when backdrop is clicked", () => {
    const { container } = render(
      <div>
        <span className="inline-glossary-ref" data-term-id="titan">
          Титан
        </span>
        <GlossaryDrawer entries={entries} />
      </div>
    );

    fireEvent.click(container.querySelector(".inline-glossary-ref")!);
    expect(container.querySelector(".glossary-drawer")).not.toBeNull();

    fireEvent.click(container.querySelector(".glossary-backdrop")!);
    expect(container.querySelector(".glossary-drawer")).toBeNull();
  });

  it("does not show missing definitions", () => {
    const { container } = render(
      <div>
        <span className="inline-glossary-ref" data-term-id="argonaut">
          Аргонавт
        </span>
        <GlossaryDrawer entries={entries} />
      </div>
    );

    fireEvent.click(container.querySelector(".inline-glossary-ref")!);

    expect(container.textContent).toContain("Аргонавт");
    expect(container.textContent).toContain("Argonaut");
    // No definitions should be shown
    expect(container.querySelector(".glossary-drawer-definition")).toBeNull();
  });
});
