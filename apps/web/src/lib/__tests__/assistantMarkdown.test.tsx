/**
 * The assistant's answer renderer.
 *
 * The safety property is the one worth a test: answers come from a
 * language model, so the renderer must build elements rather than inject
 * HTML. Everything else here is the formatting the assistant is actually
 * asked to produce.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "@/features/assistant/Markdown";

describe("Markdown", () => {
  it("renders paragraphs and joins wrapped lines", () => {
    const { container } = render(<Markdown text={"First line\nsecond line\n\nSecond para"} />);
    const paragraphs = container.querySelectorAll("p");
    expect(paragraphs).toHaveLength(2);
    expect(paragraphs[0].textContent).toBe("First line second line");
  });

  it("renders bullet and numbered lists", () => {
    const { container } = render(<Markdown text={"- one\n- two\n\n1. first\n2. second"} />);
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
  });

  it("renders bold and inline code as elements", () => {
    const { container } = render(<Markdown text="Risk is **High** per `wildfire_risk_v1`" />);
    expect(container.querySelector("strong")?.textContent).toBe("High");
    expect(container.querySelector("code")?.textContent).toBe("wildfire_risk_v1");
  });

  it("renders a table with its header row", () => {
    render(<Markdown text={"| Region | Risk |\n| --- | --- |\n| Kamloops | High |"} />);
    expect(screen.getByText("Region")).toBeDefined();
    expect(screen.getByText("Kamloops")).toBeDefined();
  });

  it("never injects raw HTML from the model", () => {
    const { container } = render(
      <Markdown text={'<img src=x onerror="alert(1)"> and <script>bad()</script>'} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>bad()</script>");
  });

  it("strips stray heading markers rather than printing them", () => {
    const { container } = render(<Markdown text="## Summary" />);
    expect(container.textContent).toBe("Summary");
  });

  it("renders an empty answer without crashing", () => {
    const { container } = render(<Markdown text="" />);
    expect(container.textContent).toBe("");
  });
});
