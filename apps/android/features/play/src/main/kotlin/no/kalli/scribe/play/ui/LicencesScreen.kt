package no.kalli.scribe.play.ui

import no.kalli.scribe.play.R

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.play.PlayViewModel

/** The app's file of third-party licences in its assets, written by scripts/licences.py (licences/README.md). */
const val LICENCES_ASSET = "licences/third-party.txt"

/** A line of its own between two parts of the file. */
private val RULE = Regex("=+")

/**
 * The file as the paragraphs it is shown in: its first line is the screen's title and is left out, a rule is
 * null (drawn as a divider), and the line after a rule is that part's heading.
 */
fun licenceParagraphs(text: String): List<LicencePart> {
    val parts = mutableListOf<LicencePart>()
    var afterRule = false
    text.trim().split(Regex("\\n\\s*\\n")).drop(1).forEach { paragraph ->
        if (RULE.matches(paragraph.trim())) {
            parts += LicencePart(null, heading = false)
            afterRule = true
        } else if (afterRule) {
            // "Name\nAddress\nLicence: …": the name is the heading, the rest is read after it.
            val lines = paragraph.trim().lines()
            parts += LicencePart(lines.first(), heading = true)
            if (lines.size > 1) parts += LicencePart(lines.drop(1).joinToString("\n"), heading = false)
            afterRule = false
        } else {
            parts += LicencePart(paragraph.trim(), heading = paragraph.trim() == "Contents")
        }
    }
    return parts
}

data class LicencePart(val text: String?, val heading: Boolean)

/**
 * What the app ships of others' work, each with its licence and notice, and every licence's text. Reached from
 * About. A long text: only the paragraphs on screen are laid out.
 */
@Composable
fun LicencesScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val assets = LocalContext.current.assets
    val parts = remember { licenceParagraphs(assets.open(LICENCES_ASSET).bufferedReader().use { it.readText() }) }
    PlayScaffold(title = null, onBack = vm::back, backLabel = stringResource(R.string.back), status = status, scroll = false) {
        SelectionContainer {
            LazyColumn(Modifier.fillMaxSize().testTag("licences"), contentPadding = PaddingValues(bottom = ScribeSpace.s5),
                verticalArrangement = Arrangement.spacedBy(ScribeSpace.s3)) {
                item { ScreenTitle(stringResource(R.string.licences_title)) }
                items(parts) { part ->
                    when {
                        part.text == null -> HorizontalDivider(thickness = 1.dp, color = ScribeTheme.colors.border)
                        part.heading -> Text(part.text, style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.semantics { heading() })
                        else -> Text(part.text, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }
    }
}
