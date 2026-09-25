package no.brasscribe.play.engine

import kotlinx.serialization.KSerializer
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.descriptors.elementNames
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import no.brasscribe.play.model.Composition
import no.brasscribe.play.model.KeySig
import no.brasscribe.play.model.Meter
import no.brasscribe.play.model.Note
import no.brasscribe.play.model.Voice
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Compares the hand-written client with the engine's OpenAPI description (vendored as
 * engine-client/openapi.json, refreshed with `./gradlew :engine-client:syncOpenApi`). Fails when the
 * engine adds an operation, renames a property or adds an enum value this client does not know.
 */
class EngineContractTest {
    private val spec: JsonObject = Json.parseToJsonElement(File(System.getProperty("brasscribe.openapi")).readText()).jsonObject
    private val schemas = spec.getValue("components").jsonObject.getValue("schemas").jsonObject

    private val models: Map<String, KSerializer<*>> = mapOf(
        "Health" to Health.serializer(), "PairRequest" to PairRequest.serializer(), "PairResponse" to PairResponse.serializer(),
        "ProfileInfo" to ProfileInfo.serializer(), "AudioRef" to AudioRef.serializer(), "JobCreate" to JobCreate.serializer(),
        "Job" to Job.serializer(), "StageState" to StageState.serializer(), "Artifact" to Artifact.serializer(),
        "Composition" to Composition.serializer(), "Voice" to Voice.serializer(), "Note" to Note.serializer(),
        "Meter" to Meter.serializer(), "KeySig" to KeySig.serializer(),
    )

    @Test
    fun everyOperationIsImplementedOrDeliberatelySkipped() {
        val ops = spec.getValue("paths").jsonObject.values.flatMap { path ->
            path.jsonObject.values.map { it.jsonObject.getValue("operationId").jsonPrimitive.content }
        }.toSet()
        assertEquals("operations not covered", emptySet<String>(), ops - EngineApi.OPERATIONS - EngineApi.NOT_USED)
        assertEquals("operations the spec no longer has", emptySet<String>(), EngineApi.OPERATIONS - ops)
    }

    @Test
    fun everySchemaPropertyIsModelled() {
        val missing = mutableListOf<String>()
        for ((name, serializer) in models) {
            val props = schemas.getValue(name).jsonObject["properties"]?.jsonObject?.keys ?: emptySet()
            val known = serializer.descriptor.elementNames.toSet()
            (props - known).forEach { missing += "$name.$it" }
        }
        assertEquals("spec properties without a Kotlin field", emptyList<String>(), missing)
    }

    @Test
    fun requiredPropertiesAreNotOptionalInKotlin() {
        val wrong = mutableListOf<String>()
        for ((name, serializer) in models) {
            val required = schemas.getValue(name).jsonObject["required"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList()
            val d: SerialDescriptor = serializer.descriptor
            for (r in required) {
                val i = d.getElementIndex(r)
                if (i >= 0 && d.isElementOptional(i)) wrong += "$name.$r"
            }
        }
        assertEquals("required in the spec but defaulted in Kotlin", emptyList<String>(), wrong)
    }

    @Test
    fun eventPayloadMatchesSseSchema() {
        val sse = spec.getValue("paths").jsonObject.getValue("/v1/jobs/{job_id}/events").jsonObject.getValue("get").jsonObject
            .getValue("responses").jsonObject.getValue("200").jsonObject.getValue("content").jsonObject
            .getValue("text/event-stream").jsonObject.getValue("schema").jsonObject
        val props = sse.getValue("properties").jsonObject.keys
        assertEquals(emptySet<String>(), props - JobEvent.serializer().descriptor.elementNames.toSet())
    }

    @Test
    fun enumsMatch() {
        fun specEnum(schema: String, prop: String): Set<String> {
            val p = schemas.getValue(schema).jsonObject.getValue("properties").jsonObject.getValue(prop).jsonObject
            val direct = p["enum"]?.jsonArray?.map { it.jsonPrimitive.content }
            if (direct != null) return direct.toSet()
            return p.getValue("anyOf").jsonArray.flatMap { alt ->
                val o = alt.jsonObject
                o["enum"]?.jsonArray?.map { it.jsonPrimitive.content } ?: listOfNotNull(o["const"]?.jsonPrimitive?.content)
            }.toSet()
        }
        fun kotlinEnum(d: SerialDescriptor) = (0 until d.elementsCount).map { d.getElementName(it) }.toSet()
        assertEquals(specEnum("Job", "status"), kotlinEnum(JobStatus.serializer().descriptor))
        assertEquals(specEnum("StageState", "status"), kotlinEnum(StageStatus.serializer().descriptor))
        assertEquals(specEnum("Voice", "role"), kotlinEnum(no.brasscribe.play.model.VoiceRole.serializer().descriptor))
    }

    @Test
    fun defaultProfileMatchesSpec() {
        val default = schemas.getValue("JobCreate").jsonObject.getValue("properties").jsonObject.getValue("profile")
            .jsonObject.getValue("default").jsonPrimitive.content
        assertEquals(default, JobCreate("x").profile)
        assertTrue(Profile.of(default) != null)
    }
}
