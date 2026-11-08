// The signed-in customer as the chat shows them (spec 009: name from the sign-in service).

export type User = { name: string; displayName: string };

/** "vinod.patil@example.com" → "Vinod"; "Alice Example" → "Alice". */
export function displayNameFor(name: string): string {
  const first = name.trim().split("@")[0].split(/[\s._-]+/).find(Boolean) ?? "";
  return first ? first[0].toUpperCase() + first.slice(1) : "there";
}

export function userFromName(name: string): User {
  return { name, displayName: displayNameFor(name) };
}
