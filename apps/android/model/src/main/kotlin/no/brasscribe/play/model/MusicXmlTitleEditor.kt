package no.brasscribe.play.model

import java.io.StringReader
import java.io.StringWriter
import javax.xml.XMLConstants
import javax.xml.parsers.DocumentBuilderFactory
import javax.xml.transform.OutputKeys
import javax.xml.transform.TransformerFactory
import javax.xml.transform.dom.DOMSource
import javax.xml.transform.stream.StreamResult
import org.xml.sax.InputSource

object MusicXmlTitleEditor {
    fun replaceTitle(xml: String, title: String): String {
        val factory = DocumentBuilderFactory.newInstance().apply {
            isNamespaceAware = true
            setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
            setFeature("http://xml.org/sax/features/external-general-entities", false)
            setFeature("http://xml.org/sax/features/external-parameter-entities", false)
            setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "")
            setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "")
        }
        val document = factory.newDocumentBuilder().parse(InputSource(StringReader(xml)))
        val root = document.documentElement
        val work = root.childElements("work") ?: document.createElement("work").also { root.insertBefore(it, root.firstChild) }
        val workTitle = work.childElements("work-title") ?: document.createElement("work-title").also { work.insertBefore(it, work.firstChild) }
        workTitle.textContent = title
        val transformer = TransformerFactory.newInstance().newTransformer().apply {
            setOutputProperty(OutputKeys.ENCODING, "UTF-8")
            setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "no")
        }
        return StringWriter().also { transformer.transform(DOMSource(document), StreamResult(it)) }.toString()
    }

    private fun org.w3c.dom.Element.childElements(localName: String): org.w3c.dom.Element? {
        val nodes = childNodes
        for (i in 0 until nodes.length) {
            val node = nodes.item(i)
            if (node is org.w3c.dom.Element && (node.localName ?: node.nodeName) == localName) return node
        }
        return null
    }
}