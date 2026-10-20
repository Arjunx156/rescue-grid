import { expect, test } from "bun:test";
import { KEYS, LANGS, t } from "./i18n";

const slots = (s: string) =>
  [...s.matchAll(/\{(\w+)\}/g)]
    .map((m) => m[1])
    .sort()
    .join();

// the compiler checks every key exists; only a test can check the {slots} survived translation
test("every translation keeps the English placeholders", () => {
  const broken = LANGS.flatMap(({ code }) =>
    KEYS.filter((key) => slots(t(code, key)) !== slots(t("en", key))).map((key) => `${code}.${key}`),
  );
  expect(broken).toEqual([]);
});

test("translations are actually translated", () => {
  for (const { code } of LANGS.filter((l) => l.code !== "en")) {
    const same = KEYS.filter((key) => t(code, key) === t("en", key));
    expect(same.length).toBeLessThan(KEYS.length / 10);
  }
});

test("variables are filled in", () => {
  expect(t("en", "stopOf", { i: 2, n: 5 })).toBe("Stop 2 of 5");
});
