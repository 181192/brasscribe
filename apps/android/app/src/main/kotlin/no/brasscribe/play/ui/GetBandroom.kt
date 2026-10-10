package no.brasscribe.play.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import no.brasscribe.design.BrasscribeSpace
import no.brasscribe.design.BrasscribeTheme
import no.brasscribe.play.R

/** Where Brasscribe Bandroom, the program for the computer, is downloaded: always its latest release. */
const val BANDROOM_DOWNLOAD = "https://github.com/181192/brasscribe/releases/latest"

/**
 * Get Bandroom, on the pairing screen and in Help: what the program is called, the address to type on the computer
 * (the text can be selected and copied), and a button that opens it in the phone's browser. A phone with no browser
 * says so on the status line; the address is still there to type.
 */
@Composable
fun GetBandroom(onNoBrowser: () -> Unit, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val c = BrasscribeTheme.colors
    Column(modifier.testTag("get-bandroom"), verticalArrangement = Arrangement.spacedBy(BrasscribeSpace.s2)) {
        SubHeading(stringResource(R.string.bandroom_get_title))
        Text(stringResource(R.string.bandroom_get_text), style = MaterialTheme.typography.bodyLarge, color = c.textMuted)
        SelectionContainer {
            Text(BANDROOM_DOWNLOAD, style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.testTag("bandroom-address"))
        }
        OutlineButton(stringResource(R.string.bandroom_open), {
            runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(BANDROOM_DOWNLOAD)).addCategory(Intent.CATEGORY_BROWSABLE)) }
                .onFailure { onNoBrowser() }
        }, icon = R.drawable.ic_bc_open)
    }
}
