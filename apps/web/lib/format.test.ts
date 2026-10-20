import { expect, test } from "bun:test";
import { ago, clock, km, levelColor, minutes, plural } from "./format";

test("clock shows IST whatever the machine's zone", () => {
  expect(clock("2015-12-01T18:30:00Z")).toBe("00:00");
  expect(clock("2015-12-01T09:02:00Z")).toBe("14:32");
  expect(clock(null)).toBe("--:--");
  expect(clock("not a date")).toBe("--:--");
});

test("ago reads against the disaster's clock", () => {
  const now = Date.parse("2015-12-02T12:00:00Z");
  expect(ago("2015-12-02T11:59:40Z", now)).toBe("now");
  expect(ago("2015-12-02T11:48:00Z", now)).toBe("12m");
  expect(ago("2015-12-02T09:55:00Z", now)).toBe("2h 05m");
  expect(ago("2015-11-28T12:00:00Z", now)).toBe("4d");
  expect(ago("2015-12-02T12:05:00Z", now)).toBe("now");
});

test("durations and distances", () => {
  expect(minutes(20)).toBe("1 min");
  expect(minutes(3900)).toBe("1 h 5 min");
  expect(km(640)).toBe("640 m");
  expect(km(12_340)).toBe("12.3 km");
  expect(plural(1, "person", "people")).toBe("1 person");
  expect(plural(6, "team")).toBe("6 teams");
});

test("unknown levels fall back to the closed colour", () => {
  expect(levelColor("critical")).toBe("var(--critical)");
  expect(levelColor("nonsense")).toBe("var(--closed)");
});
