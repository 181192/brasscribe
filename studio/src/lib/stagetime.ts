// A stage's time, split into waiting for the GPU (another job held it) and running, when it waited.
import { t } from "../i18n";
import { fmt, h } from "../ui/dom";

export interface StageTiming {
  seconds?: number | null;
  queue_wait_s?: number | null;
  run_s?: number | null;
}

/** Waits shorter than this are not worth a mention. */
export const WAIT_SHOWN_S = 0.5;

/** "2.1 s", or "waited 6 min 14 s · ran 2.1 s" (in the order they happened) when the stage queued for the GPU. */
export function stageTime(s: StageTiming | null | undefined): string {
  if (!s) return fmt.seconds(undefined);
  const wait = s.queue_wait_s ?? 0;
  if (wait < WAIT_SHOWN_S) return fmt.seconds(s.run_s ?? s.seconds);
  const ran = s.run_s ?? Math.max(0, (s.seconds ?? 0) - wait);
  return t("run.waitedRan", { ran: fmt.seconds(ran), waited: fmt.seconds(wait) });
}

/** Id of the explanation of a wait in the stage panel, which the selected stage's node is described by. */
export const WAIT_NOTE_ID = "stage-wait-note";

/** Why a stage that waited took longer than it ran, for the stage panel; null when it did not wait. */
export function stageTimeTip(s: StageTiming | null | undefined): string | null {
  const wait = s?.queue_wait_s ?? 0;
  if (!s || wait < WAIT_SHOWN_S) return null;
  const ran = s.run_s ?? Math.max(0, (s.seconds ?? 0) - wait);
  return t("run.waitedTip", { ran: fmt.seconds(ran), waited: fmt.seconds(wait) });
}

/** The stage panel's explanation of a wait (id WAIT_NOTE_ID), or null when the stage did not wait. */
export function waitNote(s: StageTiming | null | undefined): HTMLParagraphElement | null {
  const tip = stageTimeTip(s);
  return tip ? h("p", { id: WAIT_NOTE_ID, class: "small" }, tip) : null;
}
