/**
 * Test environment setup.
 *
 * jsdom 25 under vitest 2 does not expose `localStorage` on the test global
 * even with a real origin configured, so anything that reads or writes
 * storage sees `undefined`. The app itself never hits this — browsers always
 * provide Storage — but the key store and the preparedness state do, and
 * they need somewhere to write during a test. This is a minimal in-memory
 * Storage installed only when the environment did not provide one.
 */
class MemoryStorage implements Storage {
  private map = new Map<string, string>();
  get length(): number {
    return this.map.size;
  }
  clear(): void {
    this.map.clear();
  }
  getItem(key: string): string | null {
    return this.map.has(key) ? (this.map.get(key) as string) : null;
  }
  key(index: number): string | null {
    return Array.from(this.map.keys())[index] ?? null;
  }
  removeItem(key: string): void {
    this.map.delete(key);
  }
  setItem(key: string, value: string): void {
    this.map.set(key, String(value));
  }
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  if (typeof (globalThis as Record<string, unknown>)[name] === "undefined") {
    Object.defineProperty(globalThis, name, {
      value: new MemoryStorage(),
      configurable: true,
      writable: true,
    });
  }
}
