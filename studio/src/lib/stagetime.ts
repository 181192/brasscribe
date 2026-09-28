// A stage's time, split into waiting for the GPU (another job held it) and running, when it waited.
import { t } from "../i18n";
import { fmt } from "../ui/dom";

export interface StageTiming {
  seconds?: number | null;
  queue_wait_s?: number | null;
  run_s?: number | null;
}

/** Waits shorter than this are not worth a mention. */
export const WAIT_SHOWN_S = 0.5;

/** "2.1 s", or "ran 2.1 s · waited 6 min 14 s" when the stage queued for the GPU. */
export function stageTime(s: StageTiming | null | undefined): string {
  if (!s) return fmt.seconds(undefined);
  const wait = s.queue_wait_s ?? 0;
  if (wait < WAIT_SHOWN_S) return fmt.seconds(s.run_s ?? s.seconds);
  const ran = s.run_s ?? Math.max(0, (s.seconds ?? 0) - wait);
  return t("run.ranWaited", { ran: fmt.seconds(ran), waited: fmt.seconds(wait) });
}

/** Tooltip for a stage that waited; null otherwise. */
export function stageTimeTip(s: StageTiming | null | undefined): string | null {
  const wait = s?.queue_wait_s ?? 0;
  if (!s || wait < WAIT_SHOWN_S) return null;
  const ran = s.run_s ?? Math.max(0, (s.seconds ?? 0) - wait);
  return t("run.waitedTip", { ran: fmt.seconds(ran), waited: fmt.seconds(wait) });
}
