package no.brasscribe.play.engine

import java.net.URI
import java.net.URLDecoder

/**
 * The pairing payload the computer shows as a QR code:
 * `brasscribe://pair?v=1&id=<server id>&name=<server name>&h=<ip:port>,<ip:port>&code=<code>[&fp=<SPKI sha-256>]`.
 * Only `v` and `id` are required. Without [hosts] the engine is found by mDNS; without [code] the phone
 * asks the computer to allow it instead. A [fingerprint] means the engine must be reached over pinned TLS.
 */
data class PairLink(
    val serverId: String,
    /** Empty when the link has no name; show a generic name then, never the id. */
    val serverName: String,
    val hosts: List<String>,
    val code: String?,
    val fingerprint: String? = null,
) {
    /** Base URLs to try, in the order the computer listed them. */
    val urls: List<String> get() = hosts.map { "http://$it" }

    companion object {
        const val SCHEME = "brasscribe"

        /** Null for anything that is not a version 1 pairing link with a server id. Unknown keys are ignored. */
        fun parse(text: String): PairLink? {
            val uri = runCatching { URI(text.trim()) }.getOrNull() ?: return null
            if (!uri.scheme.equals(SCHEME, ignoreCase = true)) return null
            // brasscribe://pair?… puts "pair" in the authority; brasscribe:pair?… is opaque.
            val target = uri.authority ?: uri.schemeSpecificPart?.substringBefore('?')
            if (target != "pair") return null
            val query = uri.rawQuery ?: uri.rawSchemeSpecificPart?.substringAfter('?', "") ?: return null
            val params = query.split('&').filter { it.isNotEmpty() }.associate { pair ->
                decode(pair.substringBefore('=')) to decode(pair.substringAfter('=', ""))
            }
            if (params["v"] != "1") return null
            val id = params["id"]?.takeIf { it.isNotBlank() } ?: return null
            val code = params["code"]?.filter { !it.isWhitespace() }?.takeIf { it.isNotEmpty() }
            val hosts = params["h"].orEmpty().split(',').map { it.trim() }.filter(::validHost)
            return PairLink(id, params["name"].orEmpty().trim(), hosts, code, params["fp"]?.takeIf { it.isNotBlank() })
        }

        private fun decode(s: String): String = runCatching { URLDecoder.decode(s, Charsets.UTF_8) }.getOrDefault(s)

        /** `host:port` with a port, where an IPv6 host is in brackets (`[fd00::1]:8765`). */
        private fun validHost(h: String): Boolean {
            if (h.isEmpty() || h.any { it.isWhitespace() || it == '/' || it == '@' }) return false
            val port = if (h.startsWith("[")) {
                val close = h.indexOf(']')
                if (close < 2 || h.getOrNull(close + 1) != ':') return false
                h.substring(close + 2)
            } else {
                if (h.count { it == ':' } != 1) return false
                h.substringAfter(':')
            }
            return port.toIntOrNull()?.let { it in 1..65535 } == true
        }
    }
}
