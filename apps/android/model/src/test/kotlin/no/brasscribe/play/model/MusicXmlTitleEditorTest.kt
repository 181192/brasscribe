package no.brasscribe.play.model

import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertEquals
import org.junit.Test
import org.xml.sax.InputSource
import java.io.StringReader

class MusicXmlTitleEditorTest {
    @Test
    fun replacesAndEscapesTheEmbeddedTitle() {
        val xml = """<score-partwise><work><work-title>Old</work-title></work><part-list/></score-partwise>"""

        val updated = MusicXmlTitleEditor.replaceTitle(xml, "New & improved")
        val document = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(InputSource(StringReader(updated)))

        assertEquals("New & improved", document.getElementsByTagName("work-title").item(0).textContent)
    }
}