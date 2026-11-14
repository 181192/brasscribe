import groovy.json.JsonSlurper
import java.security.MessageDigest
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ListProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

/**
 * Fails a release build when an on-device model it bundles is missing from models/converted or is not the file the
 * pin (convert/on-device-models.json) names, by size and sha256. Without the models the app quietly sends every solo
 * to the computer, so a release must not be built without them; `python3 convert/models_pack.py fetch` gets them.
 * `allowMissing` (-Pbrasscribe.allowNoModels, any value but `false`) lets a local try-out build without them; it is
 * refused on CI. Debug builds are not checked.
 * The task has no outputs, so it runs on every release build: hashing the files is quick.
 */
abstract class VerifyModelAssets : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val pin: RegularFileProperty

    /** models/converted: each pinned file is in its `into` folder there. */
    @get:Internal
    abstract val converted: DirectoryProperty

    /** File names from the pin that the app bundles. */
    @get:Input
    abstract val models: ListProperty<String>

    @get:Input
    abstract val allowMissing: Property<Boolean>

    /** On CI (the CI variable is set) the escape is refused: a release built there is one that gets published. */
    @get:Input
    abstract val onCi: Property<Boolean>

    @TaskAction
    fun verify() {
        check(!(allowMissing.get() && onCi.get())) { "-Pbrasscribe.allowNoModels is for a local try-out; CI builds releases with the models" }
        @Suppress("UNCHECKED_CAST")
        val files = (JsonSlurper().parse(pin.get().asFile) as Map<String, Any>)["files"] as Map<String, Map<String, Any>>
        val wrong = models.get().mapNotNull { name ->
            val want = files[name] ?: return@mapNotNull "$name is not in ${pin.get().asFile.name}"
            val file = converted.get().asFile.resolve("${want["into"]}/$name")
            when {
                !file.isFile -> "missing $file"
                file.length() != (want["size"] as Number).toLong() || sha256(file) != want["sha256"] ->
                    "$file is not the pinned file (${pin.get().asFile.name})"
                else -> null
            }
        }
        if (wrong.isEmpty()) return
        val message = wrong.joinToString("\n") + "\nRun `python3 convert/models_pack.py fetch ${models.get().joinToString(" ")}` " +
            "from the repository root, or build with -Pbrasscribe.allowNoModels to try a release build without them."
        if (allowMissing.get()) logger.warn("Building a release without its on-device models (-Pbrasscribe.allowNoModels):\n$message")
        else throw IllegalStateException("A release build needs the on-device models:\n$message")
    }

    private fun sha256(file: java.io.File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(1 shl 16)
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                digest.update(buffer, 0, n)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
