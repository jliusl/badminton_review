import { describe, expect, it } from "vitest";
import { activeRallyAt } from "./score";
import type { Project, RallyEvent } from "../types";

const rally = (id: string, start: number, end: number) =>
  ({ id, start_time: start, end_time: end }) as RallyEvent;

describe("activeRallyAt", () => {
  const project = {
    timeline: [rally("05", 0, 5), rally("06", 5, 10)],
  } as Project;

  it("does not highlight the previous rally at a shared boundary", () => {
    expect(activeRallyAt(project, 4.999)?.id).toBe("05");
    expect(activeRallyAt(project, 5)?.id).toBe("06");
  });

  it("keeps the final rally active at its final endpoint", () => {
    expect(activeRallyAt(project, 10)?.id).toBe("06");
  });
});