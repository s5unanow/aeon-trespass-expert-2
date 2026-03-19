import { render, fireEvent, act } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import type { BundleTextRun, BundleGlossaryRef } from "@aeon-reader/contracts";
import { LocaleProvider, useLocale, pickText } from "@/lib/locale";
import { InlineRenderer } from "@/components/InlineRenderer";
import { LocaleSwitcher } from "@/components/LocaleSwitcher";

// Clear localStorage between tests
beforeEach(() => {
  localStorage.clear();
});

describe("pickText", () => {
  it("returns ru_text in ru locale", () => {
    expect(pickText("Hello", "Привет", "ru")).toBe("Привет");
  });

  it("returns en text in en locale", () => {
    expect(pickText("Hello", "Привет", "en")).toBe("Hello");
  });

  it("falls back to en when ru_text is null in ru locale", () => {
    expect(pickText("Hello", null, "ru")).toBe("Hello");
  });

  it("falls back to en when ru_text is empty in ru locale", () => {
    expect(pickText("Hello", "", "ru")).toBe("Hello");
  });
});

describe("LocaleProvider", () => {
  it("defaults to ru locale", () => {
    let captured = "";
    function Probe() {
      const { locale } = useLocale();
      captured = locale;
      return null;
    }
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>
    );
    expect(captured).toBe("ru");
  });

  it("reads persisted locale from localStorage", () => {
    localStorage.setItem("aeon-reader-locale", "en");
    let captured = "";
    function Probe() {
      const { locale } = useLocale();
      captured = locale;
      return null;
    }
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>
    );
    // After useEffect runs
    expect(captured).toBe("en");
  });
});

describe("LocaleSwitcher", () => {
  it("renders EN/RU options", () => {
    const { getByRole } = render(
      <LocaleProvider>
        <LocaleSwitcher />
      </LocaleProvider>
    );
    const btn = getByRole("button");
    expect(btn.textContent).toContain("EN");
    expect(btn.textContent).toContain("RU");
  });

  it("toggles locale on click", () => {
    let captured = "";
    function Probe() {
      const { locale } = useLocale();
      captured = locale;
      return null;
    }
    const { getByRole } = render(
      <LocaleProvider>
        <LocaleSwitcher />
        <Probe />
      </LocaleProvider>
    );
    expect(captured).toBe("ru");

    act(() => {
      fireEvent.click(getByRole("button"));
    });
    expect(captured).toBe("en");

    act(() => {
      fireEvent.click(getByRole("button"));
    });
    expect(captured).toBe("ru");
  });

  it("persists locale to localStorage", () => {
    const { getByRole } = render(
      <LocaleProvider>
        <LocaleSwitcher />
      </LocaleProvider>
    );

    act(() => {
      fireEvent.click(getByRole("button"));
    });
    expect(localStorage.getItem("aeon-reader-locale")).toBe("en");
  });
});

describe("InlineRenderer with locale", () => {
  it("shows ru_text in ru locale (default)", () => {
    const node: BundleTextRun = {
      kind: "text",
      text: "Hello",
      ru_text: "Привет",
      bold: false,
      italic: false,
      monospace: false,
    };
    const { container } = render(
      <LocaleProvider>
        <InlineRenderer node={node} />
      </LocaleProvider>
    );
    expect(container.textContent).toBe("Привет");
  });

  it("shows en text when locale is set to en", () => {
    localStorage.setItem("aeon-reader-locale", "en");
    const node: BundleTextRun = {
      kind: "text",
      text: "Hello",
      ru_text: "Привет",
      bold: false,
      italic: false,
      monospace: false,
    };
    const { container } = render(
      <LocaleProvider>
        <InlineRenderer node={node} />
      </LocaleProvider>
    );
    expect(container.textContent).toBe("Hello");
  });

  it("shows en surface_form for glossary_ref in en locale", () => {
    localStorage.setItem("aeon-reader-locale", "en");
    const node: BundleGlossaryRef = {
      kind: "glossary_ref",
      term_id: "t-1",
      surface_form: "Titan",
      ru_surface_form: "Титан",
    };
    const { container } = render(
      <LocaleProvider>
        <InlineRenderer node={node} />
      </LocaleProvider>
    );
    expect(container.querySelector(".inline-glossary-ref")!.textContent).toBe(
      "Titan"
    );
  });

  it("shows ru surface_form for glossary_ref in ru locale", () => {
    const node: BundleGlossaryRef = {
      kind: "glossary_ref",
      term_id: "t-1",
      surface_form: "Titan",
      ru_surface_form: "Титан",
    };
    const { container } = render(
      <LocaleProvider>
        <InlineRenderer node={node} />
      </LocaleProvider>
    );
    expect(container.querySelector(".inline-glossary-ref")!.textContent).toBe(
      "Титан"
    );
  });
});
