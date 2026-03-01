import React from "react";
import { render, screen } from "@testing-library/react";
import SnakeGame from "../SnakeGame";

// Mock canvas 2d context (jsdom does not implement it)
beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = jest.fn(() => ({
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
    textAlign: "",
    font: "",
    textBaseline: "",
    fillText: jest.fn(),
    globalAlpha: 1,
    filter: jest.fn(),
  })) as unknown as typeof CanvasRenderingContext2D.prototype;
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
