import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DiagramForgePage } from "./DiagramForgePage";

describe("DiagramForgePage", () => {
  it("presents the structured drawing truth boundary", () => {
    render(<DiagramForgePage />);

    expect(screen.getByRole("heading", { name: "图枢 DiagramForge" })).toBeInTheDocument();
    expect(screen.getByText("稳定局部修改")).toBeInTheDocument();
    expect(screen.getByText(/Headless 编译器、Draw.io Desktop 和 Live MCP/)).toBeInTheDocument();
    expect(screen.getByText("npm.cmd run drawio:plan")).toBeInTheDocument();
  });
});
