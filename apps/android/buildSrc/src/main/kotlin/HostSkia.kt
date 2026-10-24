import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.file.ArchiveOperations
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.FileSystemOperations
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction

/** alphaSkia for the machine the unit tests run on: the same drawing code as the app's, from the same release. */
abstract class HostSkia @Inject constructor(private val archives: ArchiveOperations, private val files: FileSystemOperations) : DefaultTask() {
    @get:InputFiles abstract val jars: ConfigurableFileCollection
    @get:Input abstract val platform: Property<String>
    @get:OutputDirectory abstract val into: DirectoryProperty

    @TaskAction
    fun sync() {
        val folder = "native/${platform.get()}/*"
        files.sync {
            from(jars.map { archives.zipTree(it) }) {
                include(folder)
                eachFile { path = name }
                includeEmptyDirs = false
            }
            into(into)
        }
    }

    companion object {
        private val os = System.getProperty("os.name").lowercase().let { if ("mac" in it) "macos" else if ("win" in it) "windows" else "linux" }

        /** The machine's platform, as alphaSkia names its folders. */
        fun platform(): String = "$os-" + System.getProperty("os.arch").let { if (it == "aarch64" || it == "arm64") "arm64" else "x64" }

        /** Of alphaSkia's three desktop builds, the one for this machine. */
        fun <T> library(macos: T, windows: T, linux: T): T = when (os) { "macos" -> macos; "windows" -> windows; else -> linux }
    }
}
