import org.gradle.api.DefaultTask
import org.gradle.api.artifacts.Configuration
import org.gradle.api.artifacts.component.ModuleComponentIdentifier
import org.gradle.api.artifacts.result.ResolvedDependencyResult
import org.gradle.api.provider.Provider
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ListProperty
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

/**
 * Fails when Google's ML Kit, Play services, Firebase or datatransport (Firelog) is in a variant: a component of
 * theirs in its merged manifest, or a library of theirs on its runtime classpath. The Play services code scanner
 * brought them in, and they logged ML Kit usage to Google and were handed the pairing code; the app reads the code
 * itself instead. A new dependency would bring them back.
 */
abstract class VerifyNoGoogleServices : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val mergedManifest: RegularFileProperty

    /** The variant's runtime classpath, as group:module. */
    @get:Input
    abstract val modules: ListProperty<String>

    @get:OutputFile
    abstract val report: RegularFileProperty

    @TaskAction
    fun verify() {
        val libraries = modules.get().filter { module -> GOOGLE.any { module.startsWith("$it:") || module.startsWith("$it.") } }
        check(libraries.isEmpty()) {
            "Google's services are on the runtime classpath: $libraries. Remove the dependency that brings them " +
                "(./gradlew :products:<app>:dependencies shows which)."
        }
        val manifest = mergedManifest.get().asFile.readText()
        val found = Regex("""android:(?:name|authorities)="([^"]*)"""").findAll(manifest).map { it.groupValues[1] }
            .filter { name -> GOOGLE.any { name.startsWith(it) } }.toList()
        check(found.isEmpty()) {
            "Components of Google's services are in ${mergedManifest.get().asFile}: $found. Remove the dependency that brings them."
        }
        report.get().asFile.writeText("no ML Kit, Play services, Firebase or datatransport component\n")
    }

    companion object {
        /** A variant's runtime classpath, as group:module. */
        fun modulesOf(runtime: Configuration): Provider<List<String>> =
            runtime.incoming.resolutionResult.rootComponent.map { root ->
                val seen = mutableSetOf(root.id)
                val queue = ArrayDeque(listOf(root))
                val found = sortedSetOf<String>()
                while (queue.isNotEmpty()) {
                    val component = queue.removeFirst()
                    (component.id as? ModuleComponentIdentifier)?.let { found += "${it.group}:${it.module}" }
                    component.dependencies.filterIsInstance<ResolvedDependencyResult>()
                        .map { it.selected }.filter { seen.add(it.id) }.forEach(queue::add)
                }
                found.toList()
            }

        val GOOGLE = listOf("com.google.mlkit", "com.google.android.datatransport", "com.google.android.gms", "com.google.firebase")
    }
}

