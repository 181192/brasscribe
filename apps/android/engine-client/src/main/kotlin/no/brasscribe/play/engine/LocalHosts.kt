package no.brasscribe.play.engine

import java.net.Inet6Address
import java.net.InetAddress
import java.net.URI

/**
 * Which addresses count as "a computer on this network". The engine runs on the user's own computer
 * and is reached on the local network, so a pairing link names only such addresses: private IPv4
 * (RFC 1918), link-local, IPv6 unique-local and loopback, or a `.local` name. Nothing is looked up:
 * a host name other than `.local` or `localhost` is not local.
 */
object LocalHosts {
    /** The emulator's alias for the machine it runs on. */
    const val EMULATOR_HOST = "10.0.2.2"

    /** True for a host on the local network (see the class comment), in a URL's form (IPv6 with or without brackets). */
    fun isLocal(host: String): Boolean {
        val h = host.trim().removeSurrounding("[", "]").lowercase()
        if (h.isEmpty()) return false
        if (h == "localhost" || (h.endsWith(".local") && h.length > ".local".length && h.all { it.isLetterOrDigit() || it == '-' || it == '.' })) return true
        ipv4(h)?.let { a ->
            val (b0, b1) = a[0] to a[1]
            return b0 == 10 || b0 == 127 || (b0 == 172 && b1 in 16..31) || (b0 == 192 && b1 == 168) || (b0 == 169 && b1 == 254)
        }
        val v6 = ipv6(h) ?: return false
        return v6.isLoopbackAddress || v6.isLinkLocalAddress || (v6.address[0].toInt() and 0xFE) == 0xFC
    }

    /**
     * Hosts the engine trusts without pairing (it says `auth_required: false` to them): only this phone
     * itself and, on the emulator, the machine it runs on. Anything else must pair.
     */
    fun isTrusted(host: String): Boolean {
        val h = host.trim().removeSurrounding("[", "]").lowercase()
        if (h == "localhost" || h == EMULATOR_HOST) return true
        ipv4(h)?.let { return it[0] == 127 }
        return ipv6(h)?.isLoopbackAddress == true
    }

    /** The host of [url], or null when it has none. */
    fun hostOf(url: String?): String? =
        url?.let { runCatching { URI(it.trim()).host?.removeSurrounding("[", "]")?.lowercase() }.getOrNull() }?.takeIf { it.isNotEmpty() }

    private fun ipv4(h: String): IntArray? {
        val parts = h.split('.')
        if (parts.size != 4) return null
        val bytes = parts.map { p -> p.takeIf { it.isNotEmpty() && it.length <= 3 && it.all(Char::isDigit) }?.toInt()?.takeIf { it <= 255 } ?: return null }
        return bytes.toIntArray()
    }

    /** An IPv6 literal (never a name, so nothing is looked up). */
    private fun ipv6(h: String): Inet6Address? {
        if (':' !in h || h.any { !(it.isDigit() || it in 'a'..'f' || it == ':' || it == '.' || it == '%') }) return null
        return runCatching { InetAddress.getByName(h) as? Inet6Address }.getOrNull()
    }
}
