package no.brasscribe.play

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Runs [work] on [worker] and shows what it reports where the caller is: [show] is called in the caller's
 * own context (the main thread, for the view model), never on the worker's thread. Only the latest report
 * is kept while the caller is busy, and nothing is shown once the work has ended, so a late report cannot
 * undo what the caller sets after it.
 */
internal suspend fun <P : Any, T> reportedHere(worker: CoroutineDispatcher, show: (P) -> Unit, work: (report: (P) -> Unit) -> T): T = coroutineScope {
    val latest = Channel<P>(Channel.CONFLATED)
    val shown = launch { for (p in latest) show(p) }
    try {
        withContext(worker) { work { latest.trySend(it) } }
    } finally {
        shown.cancel()
    }
}
