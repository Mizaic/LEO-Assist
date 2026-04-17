import "@testing-library/jest-dom";
import React from "react";
import { TextEncoder, TextDecoder } from "util";

global.fetch = jest.fn();
if (typeof global.TextEncoder === "undefined") {
  global.TextEncoder = TextEncoder;
  global.TextDecoder = TextDecoder as typeof global.TextDecoder;
}

if (typeof (global as any).ResizeObserver === "undefined") {
  (global as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

jest.mock("react-virtuoso", () => {
  const Virtuoso = ({ data, itemContent, ...rest }: any) =>
    React.createElement(
      "div",
      { "data-testid": "virtuoso-list", style: rest.style },
      (data ?? []).map((item: any, index: number) =>
        React.createElement("div", { key: index }, itemContent(index, item))
      )
    );

  const TableVirtuoso = ({
    data,
    itemContent,
    fixedHeaderContent,
    components,
    ...rest
  }: any) => {
    const TableComp = components?.Table ?? "table";
    const THead = components?.TableHead ?? "thead";
    const TBody = components?.TableBody ?? "tbody";
    const TRow = components?.TableRow ?? "tr";

    return React.createElement(
      TableComp,
      { style: rest.style },
      fixedHeaderContent
        ? React.createElement(THead, null, fixedHeaderContent())
        : null,
      React.createElement(
        TBody,
        null,
        (data ?? []).map((item: any, index: number) =>
          React.createElement(
            TRow,
            { key: index, "data-index": index },
            itemContent(index, item)
          )
        )
      )
    );
  };

  return { Virtuoso, TableVirtuoso };
});

afterEach(() => {
  jest.restoreAllMocks();
  (global.fetch as jest.Mock).mockReset();
});
