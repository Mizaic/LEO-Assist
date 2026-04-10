import React from "react";
import { render, screen } from "@testing-library/react";
import SnakeGame from "../SnakeGame";

// Mock canvas 2d context (jsdom does not implement it)
const origGetContext = HTMLCanvasElement.prototype.getContext;
beforeAll(() => {
  const mockCtx = {
    fillStyle: "",
    fillRect: jest.fn(),
    strokeStyle: "",
    lineWidth: 0,
    beginPath: jest.fn(),
    moveTo: jest.fn(),
    lineTo: jest.fn(),
    stroke: jest.fn(),
    save: jest.fn(),
    restore: jest.fn(),
    shadowColor: "",
    shadowBlur: 0,
    arc: jest.fn(),
    fill: jest.fn(),
    textAlign: "left" as CanvasTextAlign,
    font: "",
    textBaseline: "alphabetic" as CanvasTextBaseline,
    fillText: jest.fn(),
    globalAlpha: 1,
    filter: "none",
  };
  HTMLCanvasElement.prototype.getContext = function (
    this: HTMLCanvasElement,
    contextId: string,
    options?: CanvasRenderingContext2DSettings,
  ) {
    if (contextId === "2d") {
      return mockCtx as unknown as CanvasRenderingContext2D;
    }
    return origGetContext.call(this, contextId, options as never);
  } as typeof HTMLCanvasElement.prototype.getContext;
});

afterAll(() => {
  HTMLCanvasElement.prototype.getContext = origGetContext;
});

jest.mock("../Leaderboard", () => {
  return function MockLeaderboard() {
    return <div data-testid="leaderboard">Leaderboard</div>;
  };
});

describe("SnakeGame", () => {
  it("renders game HUD with score and level", () => {
    render(<SnakeGame />);
    expect(screen.getByText(/Score:/)).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText(/Lvl/)).toBeInTheDocument();
  });

  it("renders canvas for the game board", () => {
    render(<SnakeGame />);
    const canvas = document.querySelector("canvas");
    expect(canvas).toBeInTheDocument();
    expect(canvas).toHaveAttribute("width", "384");
    expect(canvas).toHaveAttribute("height", "384");
  });

  it("renders instructions when game is running", () => {
    render(<SnakeGame />);
    expect(screen.getByText(/Arrow keys \/ WASD/)).toBeInTheDocument();
  });

  it("renders Leaderboard component", () => {
    render(<SnakeGame />);
    expect(screen.getByTestId("leaderboard")).toBeInTheDocument();
  });
});
