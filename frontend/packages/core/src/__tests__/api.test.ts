import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, configureApi, getHistory, getMe, sendMessage } from "../api";

describe("configureApi (spec 007 FR-008)", () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ session_id: "a", messages: [] })));

  beforeEach(() => vi.stubGlobal("fetch", fetchMock));
  afterEach(() => {
    configureApi({ baseUrl: "" });
    fetchMock.mockClear();
    vi.unstubAllGlobals();
  });

  it("uses the relative /api path by default", async () => {
    await getHistory("a");
    expect(fetchMock).toHaveBeenCalledWith("/api/chat/a/history", undefined);
  });

  it("prefixes requests with the configured base location", async () => {
    configureApi({ baseUrl: "https://api.example.com/" });
    await getHistory("a");
    expect(fetchMock).toHaveBeenCalledWith("https://api.example.com/api/chat/a/history", undefined);
  });
});

describe("sign-in token and errors (spec 009)", () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ session_id: "a", messages: [] })));

  beforeEach(() => vi.stubGlobal("fetch", fetchMock));
  afterEach(() => {
    configureApi({ baseUrl: "", getToken: undefined });
    fetchMock.mockClear();
    vi.unstubAllGlobals();
  });

  it("sends the token from getToken as a Bearer header", async () => {
    configureApi({ getToken: () => "tok-123" });
    await getHistory("a");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok-123");
  });

  it("waits for an async getToken", async () => {
    configureApi({ getToken: async () => "tok-async" });
    await getHistory("a");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok-async");
  });

  it("keeps other headers when adding the token", async () => {
    configureApi({ getToken: () => "tok-123" });
    await sendMessage("a", "hi");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer tok-123");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("sends no Authorization header when there is no token", async () => {
    configureApi({ getToken: () => null });
    await getHistory("a");
    expect(fetchMock).toHaveBeenCalledWith("/api/chat/a/history", undefined);
  });

  it("setting only the base location keeps the token source", async () => {
    configureApi({ getToken: () => "tok-123" });
    configureApi({ baseUrl: "https://api.example.com" });
    await getHistory("a");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.example.com/api/chat/a/history");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok-123");
  });

  it("throws ApiError with the status on a non-2xx response", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "not signed in" }), { status: 401 }));
    const error = await getHistory("a").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toBeInstanceOf(Error);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).message).toBe("Request failed (401)");
  });

  it("on 401 asks onUnauthorized and retries once with the new token when it succeeds", async () => {
    let token = "old";
    configureApi({
      getToken: () => token,
      onUnauthorized: async () => {
        token = "new";
        return true;
      },
    });
    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 401 }));
    await getHistory("a");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer new");
    configureApi({ onUnauthorized: undefined });
  });

  it("on 401 throws when onUnauthorized gives up, without retrying", async () => {
    const onUnauthorized = vi.fn(async () => false);
    configureApi({ getToken: () => "old", onUnauthorized });
    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 401 }));
    const error = await getHistory("a").catch((e: unknown) => e);
    expect((error as ApiError).status).toBe(401);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    configureApi({ onUnauthorized: undefined });
  });

  it("does not call onUnauthorized for other failures", async () => {
    const onUnauthorized = vi.fn(async () => true);
    configureApi({ getToken: () => "tok", onUnauthorized });
    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 403 }));
    const error = await getHistory("a").catch((e: unknown) => e);
    expect((error as ApiError).status).toBe(403);
    expect(onUnauthorized).not.toHaveBeenCalled();
    configureApi({ onUnauthorized: undefined });
  });

  it("getMe reads GET /api/me", async () => {
    const me = { user_id: "u1", name: "Alice", access: "granted" };
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(me)));
    expect(await getMe()).toEqual(me);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/me");
  });
});
