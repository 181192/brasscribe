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
        "Meter" to Meter.serializer(), "KeySig" to KeySig.serializer(), "Evidence" to Evidence.serializer(),
        "NoteEvidence" to NoteEvidence.serializer(), "ModelHeard" to ModelHeard.serializer(), "ModelInfo" to ModelInfo.serializer(),
        "RunUpdate" to RunUpdate.serializer(), "DeviceSelf" to DeviceSelf.serializer(), "RotateResponse" to RotateResponse.serializer(),
        "PairRequestCreate" to PairRequestCreate.serializer(), "PairRequestInfo" to PairRequestInfo.serializer(),
        "PairRequestResult" to PairRequestResult.serializer(),
    ) + tabModels

    @Test
    fun everySchemaOfTheTabIsModelled() {
        val spec = schemas.keys.filter { it.startsWith("Tab") || it in setOf("TuningFit", "ReferencePitch") }.toSet()
        assertEquals(spec, tabModels.keys)
    }

    private val tabModels: Map<String, KSerializer<*>> get() = mapOf(
        "Tab" to Tab.serializer(), "TabNote" to TabNote.serializer(), "TabPosition" to TabPosition.serializer(),
        "TabString" to TabString.serializer(), "TabTuning" to TabTuning.serializer(), "TabInstrument" to TabInstrument.serializer(),
        "TabViolation" to TabViolation.serializer(), "TuningFit" to TuningFit.serializer(), "TabKey" to TabKey.serializer(),
        "TabMeter" to TabMeter.serializer(), "ReferencePitch" to ReferencePitch.serializer(),
    )

    @Test
    fun everyOperationIsImplementedOrDeliberatelySkipped() {
        val ops = spec.getValue("paths").jsonObject.values.flatMap { path ->
            path.jsonObject.values.map { it.jsonObject.getValue("operationId").jsonPrimitive.content }
        }.toSet()
        assertEquals("operations not covered", emptySet<String>(), ops - EngineApi.OPERATIONS - EngineApi.NOT_USED)
        assertEquals("operations the spec no longer has", emptySet<String>(), EngineApi.OPERATIONS - ops)
        // NOT_USED may name computer-only operations the engine is adding (getStatus) before the spec has them.
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

        // The stand-in for a value this client does not know has no id: it is not a value of the API.
        fun <E> ids(values: List<E>) where E : Enum<E>, E : WireEnum = values.mapNotNull { it.id }.toSet()
        assertEquals(specEnum("JobCreate", "instrument"), ids(FrettedInstrument.entries))
        assertEquals(specEnum("JobCreate", "style"), ids(FingeringStyle.entries))
        assertEquals(specEnum("JobCreate", "recording"), ids(Recording.entries))
        assertEquals(specEnum("JobCreate", "octave"), ids(Octave.entries))
        assertEquals(specEnum("JobCreate", "layout"), ids(TabLayout.entries))
        assertEquals(specEnum("Tab", "style"), ids(FingeringStyle.entries))
        assertEquals(specEnum("Tab", "layout"), ids(TabLayout.entries))
        assertEquals(specEnum("Tab", "octave_source"), ids(OctaveSource.entries))
        assertEquals(specEnum("TabKey", "mode"), ids(KeyMode.entries))
    }

    /** The spec names the tunings in the option's description only: "bass-4: standard, eb-standard, ...; bass-5: ...". */
    @Test
    fun tuningsOfEachInstrumentMatchSpec() {
        val described = schemas.getValue("JobCreate").jsonObject.getValue("properties").jsonObject.getValue("tuning").jsonObject
            .getValue("description").jsonPrimitive.content
        val spec = Regex("(bass-\\d): ([a-z0-9-]+(?:, [a-z0-9-]+)*)").findAll(described)
            .associate { it.groupValues[1] to it.groupValues[2].split(", ") }
        assertEquals(spec, FrettedInstrument.entries.filter { it.id != null }.associate { it.id!! to it.tunings })
        assertTrue(FrettedInstrument.entries.all { it.id == null || it.tunings.first() == FrettedInstrument.STANDARD_TUNING })
        val capo = schemas.getValue("JobCreate").jsonObject.getValue("properties").jsonObject.getValue("capo").jsonObject
            .getValue("anyOf").jsonArray.first().jsonObject
        assertEquals(TabOptions.MAX_CAPO.toDouble(), capo.getValue("maximum").jsonPrimitive.content.toDouble(), 0.0)
    }

    @Test
    fun tabFieldsAreNullableAndOptionalAsInSpec() {
        val wrong = mutableListOf<String>()
        for ((name, serializer) in tabModels) {
            val schema = schemas.getValue(name).jsonObject
            val required = schema["required"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList()
            val d = serializer.descriptor
            for ((prop, s) in schema.getValue("properties").jsonObject) {
                val i = d.getElementIndex(prop)
                val nullable = s.jsonObject["anyOf"]?.jsonArray?.any { it.jsonObject["type"]?.jsonPrimitive?.content == "null" } ?: false
                if (d.getElementDescriptor(i).isNullable != nullable) wrong += "$name.$prop: nullable in the spec is $nullable"
                if (d.isElementOptional(i) != (prop !in required)) wrong += "$name.$prop: required in the spec is ${prop in required}"
            }
        }
        assertEquals(emptyList<String>(), wrong)
    }

    @Test
    fun tabOptionsAreTheSameInTheJsonBodyAndTheUploadForm() {
        val all = TabOptions(FrettedInstrument.BASS_5, "drop-a", 2, FingeringStyle.LEAD, Recording.SONG, Octave.UP, TabLayout.NOTATION)
        val form = all.formFields().toMap()
        val body = no.brasscribe.play.model.BrasscribeJson.encodeToJsonElement(JobCreate.serializer(), JobCreate.bassTab("a", all)).jsonObject
        assertEquals(setOf("instrument", "tuning", "capo", "style", "recording", "octave", "layout"), form.keys)
        assertEquals(form, form.keys.associateWith { body.getValue(it).jsonPrimitive.content })
        val upload = schemas.getValue("Body_createJobFromUpload").jsonObject.getValue("properties").jsonObject.keys
        assertEquals(emptySet<String>(), form.keys - upload)
    }

    @Test
    fun defaultProfileMatchesSpec() {
        val default = schemas.getValue("JobCreate").jsonObject.getValue("properties").jsonObject.getValue("profile")
            .jsonObject.getValue("default").jsonPrimitive.content
        assertEquals(default, JobCreate("x").profile)
        assertTrue(Profile.of(default) != null)
    }
}
