package no.kalli.scribe.play.ui

import no.kalli.scribe.play.R

import no.kalli.scribe.design.R as DesignR

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import no.kalli.scribe.design.ScribeSpace
import no.kalli.scribe.play.Page
import no.kalli.scribe.play.PageThumbnail
import no.kalli.scribe.play.PageThumbnails
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import no.kalli.scribe.design.ScribeTheme
import no.kalli.scribe.play.OnDeviceRouting
import no.kalli.scribe.play.PlayViewModel

/** The ways to bring pages of printed music in from the phone: its picker (several pictures, or a PDF), and its camera app. */
class PagePicker(val choose: () -> Unit, val photograph: () -> Unit)

/** What the picker offers: pictures and PDFs. */
val PAGE_TYPES = arrayOf("image/*", "application/pdf")

/**
 * The phone's own picker and camera app, through the platform's contracts: the pages chosen come in the order
 * they were picked, and a photo is written to a file of the app's own. The app declares the camera permission (it
 * reads the pairing code itself), and the phone then lets it open the camera app only once that is granted: it is
 * asked for when the first photo is taken.
 */
@Composable
fun rememberPagePicker(vm: PlayViewModel): PagePicker {
    val context = LocalContext.current
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris -> vm.addPages(uris) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { taken -> vm.photoTaken(taken) }
    fun openCamera() {
        val photo = FileProvider.getUriForFile(context, "${context.packageName}.exports", vm.photoFile())
        // A phone with no camera app: said, and choosing a picture is still there.
        runCatching { camera.launch(photo) }.onFailure { vm.photoTaken(false); vm.say(R.string.pages_no_camera) }
    }
    val allow = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        // Refused for good, the phone does not ask again: the pages' screen then has the way to its settings.
        val blocked = !granted && (context as? android.app.Activity)?.shouldShowRequestPermissionRationale(Manifest.permission.CAMERA) == false
        vm.cameraBlocked.value = blocked
        when {
            granted -> openCamera()
            blocked -> vm.showPages()
            else -> vm.say(R.string.pages_camera_needed)
        }
    }
    return remember(vm) {
        PagePicker({ pick.launch(PAGE_TYPES) }, {
            if (context.checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                vm.cameraBlocked.value = false
                openCamera()
            } else allow.launch(Manifest.permission.CAMERA)
        })
    }
}

/**
 * Printed music before it is sent: the two ways to add a page, then the pages in the order they are read, each with
 * a small picture of it and the ways to move it and to take it out, and one primary button that has the computer
 * read them. The computer reads them: a row under the pages
 * says it is there, and when it is not the band over the button says what is needed, with the way to connect; the
 * pages stay meanwhile.
 */
@Composable
fun PagesScreen(vm: PlayViewModel) {
    val status by vm.status.collectAsState()
    val pages by vm.pages.collectAsState()
    val busy by vm.busy.collectAsState()
    val connection by vm.connection.state.collectAsState()
    // The fixture engine of the UI tests is always there.
    val there = vm.container.usingFixture || OnDeviceRouting.computerThere(connection)
    val picker = rememberPagePicker(vm)
    val c = ScribeTheme.colors
    val headingFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { runCatching { headingFocus.requestFocus() } }

    PlayScaffold(
        title = null, onBack = vm::back, backLabel = stringResource(R.string.home), status = status,
        bottom = {
            // One line says what is still missing; the pages come first, since without one there is nothing to read.
            val missing = when {
                pages.isEmpty() -> R.string.pages_add_first
                !there -> R.string.pages_needs_computer
                else -> null
            }
            val why = missing?.let { stringResource(it) }
            if (why != null) Text(why, Modifier.testTag("pages-missing").semantics { liveRegion = LiveRegionMode.Polite },
                style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
            // The way to the computer is beside the reason, in view whatever the list's length: Connect or Pair this
            // phone again, as on Home.
            if (!there) ConnectionStatusRow(vm, Modifier.testTag("pages-connect"), brief = true)
            // The button says why it can't be pressed: "Read the notes, disabled" alone leaves that out.
            PrimaryButton(stringResource(R.string.pages_read), vm::readPages,
                Modifier.testTag("pages-read").then(if (why != null) Modifier.semantics { stateDescription = why } else Modifier),
                enabled = pages.isNotEmpty() && there && !busy)
        },
    ) {
        ScreenTitle(stringResource(R.string.pages_title), Modifier.focusRequester(headingFocus).focusable())
        Lead(stringResource(R.string.pages_lead))
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth(), color = c.brand, trackColor = c.border)
        // The ways to add a page come before the pages: with forty in hand they are still at the top, not under them.
        RowGroup {
            ListRow(stringResource(if (pages.isEmpty()) R.string.pages_choose else R.string.pages_choose_more), picker.choose,
                Modifier.testTag("pages-choose"), subtitle = stringResource(R.string.pages_choose_desc), icon = DesignR.drawable.ic_bc_import_file, enabled = !busy)
            RowDivider()
            ListRow(stringResource(if (pages.isEmpty()) R.string.pages_photo else R.string.pages_photo_more), picker.photograph,
                Modifier.testTag("pages-photo"), subtitle = stringResource(R.string.pages_photo_desc), icon = DesignR.drawable.ic_bc_take_photo, enabled = !busy)
        }
        // The camera was refused for good: the phone's settings for the app are where it is allowed.
        val cameraBlocked by vm.cameraBlocked.collectAsState()
        if (cameraBlocked) {
            val context = LocalContext.current
            InfoNote(stringResource(R.string.pages_camera_blocked), Modifier.testTag("pages-camera-blocked"))
            PlainButton(stringResource(R.string.pair_camera_settings), {
                runCatching {
                    context.startActivity(android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        android.net.Uri.fromParts("package", context.packageName, null)))
                }
            }, Modifier.testTag("pages-camera-settings"))
        }
        if (pages.isNotEmpty()) {
            SectionLabel(pluralStringResource(R.plurals.pages_count, pages.size, pages.size))
            // What the phone's picker hands back is in no promised order: the order here is the one that counts.
            if (pages.size > 1) Text(stringResource(R.string.pages_order_hint), Modifier.testTag("pages-order"),
                style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
            val thumbnails = remember { PageThumbnails() }
            RowGroup(Modifier.testTag("pages-list")) {
                pages.forEachIndexed { i, page ->
                    if (i > 0) RowDivider()
                    // (Keyed by the page: a row that moves keeps its picture and its place in the keyboard's round.)
                    androidx.compose.runtime.key(page.file.path) { PageRow(vm, page, i, pages.size, thumbnails) }
                }
            }
        }
        if (there) RowGroup(Modifier.testTag("pages-where")) {
            ListRow(stringResource(R.string.where_companion), null, subtitle = stringResource(R.string.pages_where_desc), icon = DesignR.drawable.ic_bc_computer)
        }
    }
}

/**
 * One page in hand: a small picture of it, its place and its name, and the ways to move it one place up or down and
 * to take it out. The three buttons are under the words where the row is narrow or the text large, so the name is
 * never squeezed to a column of letters.
 */
@Composable
private fun PageRow(vm: PlayViewModel, page: Page, index: Int, count: Int, thumbnails: PageThumbnails) {
    val c = ScribeTheme.colors
    // Read small and off the main thread, once: the row shows the icon until it is there, and after it when there is none.
    val thumbnail by produceState<PageThumbnail?>(null, page.file.path) { value = withContext(Dispatchers.IO) { thumbnails.of(page) } }
    val words = @Composable { modifier: Modifier ->
        Column(modifier) {
            Text(stringResource(R.string.pages_page, index + 1), style = MaterialTheme.typography.titleMedium, color = c.text)
            val pdfPages = thumbnail?.pages?.let { pluralStringResource(R.plurals.pages_count, it, it) }
            Text(listOfNotNull(page.name, pdfPages).joinToString(" · "), style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
        }
    }
    val picture = @Composable {
        Box(Modifier.size(width = 44.dp, height = 56.dp).background(c.secondary, MaterialTheme.shapes.small).border(1.dp, c.border, MaterialTheme.shapes.small)
            .clip(MaterialTheme.shapes.small).testTag("pages-picture-$index"), contentAlignment = Alignment.Center) {
            val bitmap = thumbnail?.picture
            // The words beside it say which page it is: the picture has no name of its own.
            if (bitmap != null) Image(bitmap.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop, alignment = Alignment.TopCenter)
            else BcIcon(DesignR.drawable.ic_bc_file, null)
        }
    }
    val buttons = @Composable {
        IconButton({ vm.movePage(page, up = true) }, Modifier.size(48.dp).testTag("pages-up-$index"), enabled = index > 0) {
            BcIcon(DesignR.drawable.ic_bc_open, stringResource(R.string.pages_move_up, index + 1), Modifier.rotate(-90f),
                tint = if (index > 0) c.text else c.textMuted)
        }
        IconButton({ vm.movePage(page, up = false) }, Modifier.size(48.dp).testTag("pages-down-$index"), enabled = index < count - 1) {
            BcIcon(DesignR.drawable.ic_bc_open, stringResource(R.string.pages_move_down, index + 1), Modifier.rotate(90f),
                tint = if (index < count - 1) c.text else c.textMuted)
        }
        IconButton({ vm.removePage(page) }, Modifier.size(48.dp).testTag("pages-remove-$index")) {
            BcIcon(DesignR.drawable.ic_bc_delete, stringResource(R.string.pages_remove, index + 1))
        }
    }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val stacked = maxWidth < 340.dp || largeText()
        Column(Modifier.fillMaxWidth().heightIn(min = 60.dp).padding(horizontal = ScribeSpace.s4, vertical = ScribeSpace.s2)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(ScribeSpace.s3)) {
                picture()
                words(Modifier.weight(1f))
                if (!stacked) buttons()
            }
            if (stacked) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) { buttons() }
        }
    }
}
