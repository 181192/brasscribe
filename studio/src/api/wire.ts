// The number Studio shares with the engine. The engine says its own in GET /v1/health; when the two differ
// Studio says which of them to update and asks that engine for its health only: the client (client.ts) refuses
// every other request before it is sent, and asks the health again when the page is looked at again, at a slow
// pace while it is, and after a request that did not get through.

/** The interface version this Studio is built for. */
export const INTERFACE_VERSION = 1;

/**
 * "update-studio": the engine's number is higher, so this page is the old one (the engine serves Studio, so a
 * page left open across an update, or one the browser kept, is reloaded). "update-engine": the engine's number is
 * lower, or it sends none (it is from before there was one).
 */
export type InterfaceMatch = "match" | "update-studio" | "update-engine";

/** `engine` is `interface_version` from the engine's health answer; anything that is no whole number counts as none. */
export function interfaceMatch(engine: unknown, studio: number = INTERFACE_VERSION): InterfaceMatch {
  if (typeof engine !== "number" || !Number.isInteger(engine) || engine < studio) return "update-engine";
  return engine > studio ? "update-studio" : "match";
}
