import Foundation

/// The three downloads a full-band score needs (docs/plan/apps-plan.md §7). None of them ship with the app:
/// each comes from where its makers publish it, and this computer fetches it.
public enum ModelComponent: String, CaseIterable, Sendable, Codable, Comparable {
    /// BS-RoFormer SW: lifts the soloist out of the band (the `separator` adapter). No stated licence.
    case soloistSeparator
    /// Mega-53: splits the band into its instruments (the `mega53` adapter). No stated licence.
    case instrumentSeparator
    /// MuScriptor medium: writes down the notes. CC BY-NC 4.0, gated on Hugging Face.
    case bandWriter

    public static func < (a: Self, b: Self) -> Bool {
        allCases.firstIndex(of: a)! < allCases.firstIndex(of: b)!
    }

    /// Where the component's files go.
    public enum Home: Sendable, Equatable {
        /// `<models>/<folder>`, the folder the engine reads through BRASSCRIBE_MODELS.
        case models(folder: String)
        /// The Hugging Face hub cache, laid out as `huggingface_hub` lays it out, so the adapter's
        /// `hf_hub_download` finds it without fetching again.
        case hub(repo: String, revision: String)
    }

    public var home: Home {
        switch self {
        case .soloistSeparator: .models(folder: "separator")
        case .instrumentSeparator: .models(folder: "mega53")
        case .bandWriter: .hub(repo: ModelCatalog.muscriptorRepo, revision: ModelCatalog.muscriptorRevision)
        }
    }

    /// Needs the user's own Hugging Face key, and the licence accepted on the model page.
    public var needsHuggingFaceKey: Bool { self == .bandWriter }

    public var files: [ModelFile] { ModelCatalog.files(for: self) }
    public var totalBytes: Int64 { files.reduce(0) { $0 + $1.size } }

    /// The page people read before they download: the licence (or its absence) is stated there.
    public var page: URL {
        switch self {
        case .soloistSeparator: URL(string: "https://github.com/nomadkaraoke/python-audio-separator")!
        case .instrumentSeparator: URL(string: "https://github.com/ZFTurbo/Music-Source-Separation-Training")!
        case .bandWriter: URL(string: "https://huggingface.co/\(ModelCatalog.muscriptorRepo)")!
        }
    }
}

/// One file of a component, from its original release URL. Never re-hosted by us.
public struct ModelFile: Sendable, Equatable {
    /// File name in the component's folder (or snapshot).
    public var name: String
    public var url: URL
    /// Bytes upstream publishes; 0 when upstream changes the file (then no size or checksum check).
    public var size: Int64
    /// SHA-256 upstream publishes (GitHub release asset digest, Hugging Face X-Linked-Etag), lower-case hex.
    public var sha256: String?
    /// Git blob id of a small (non-LFS) Hugging Face file: its name in the hub cache's blobs folder.
    public var gitBlob: String?

    public init(name: String, url: URL, size: Int64, sha256: String? = nil, gitBlob: String? = nil) {
        self.name = name; self.url = url; self.size = size; self.sha256 = sha256; self.gitBlob = gitBlob
    }

    /// Name under `blobs/` in the hub cache: the SHA-256 for LFS files, the git blob id otherwise.
    public var blobName: String? { sha256 ?? gitBlob }
}

/// Upstream release URLs, sizes and checksums, as the adapters in ml/adapters expect them:
/// run_adapter.py's `separator` (audio-separator, `--model_file_dir <models>/separator`, BS-Roformer-SW.ckpt),
/// `mega53` (`<models>/mega53`, MSST v1.0.21 assets) and `muscriptor` (`hf://MuScriptor/muscriptor-medium`).
public enum ModelCatalog {
    public static let muscriptorRepo = "MuScriptor/muscriptor-medium"
    /// The revision the checksums below belong to.
    public static let muscriptorRevision = "f32236969308476e01fd3aae67357de5feb05a2d"
    public static let huggingFaceHost = "huggingface.co"

    static let separatorRelease = "https://github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs"
    static let mega53Release = "https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21"
    static let hfResolve = "https://huggingface.co/\(muscriptorRepo)/resolve/\(muscriptorRevision)"

    public static func files(for component: ModelComponent) -> [ModelFile] {
        switch component {
        case .soloistSeparator:
            [ModelFile(name: "BS-Roformer-SW.ckpt", url: URL(string: "\(separatorRelease)/BS-Roformer-SW.ckpt")!,
                       size: 699_412_152, sha256: "24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e"),
             ModelFile(name: "BS-Roformer-SW.yaml", url: URL(string: "\(separatorRelease)/BS-Roformer-SW.yaml")!,
                       size: 4_653, sha256: "b558996f1e25eb48798bd6502505a5de94c4f966d6edfb1a0420f06cc40b501a"),
             // audio-separator reads its model list from here before every run; with it in place it needs no
             // network. Upstream edits it, so no size or checksum.
             ModelFile(name: "download_checks.json",
                       url: URL(string: "https://raw.githubusercontent.com/TRvlvr/application_data/main/filelists/download_checks.json")!,
                       size: 0)]
        case .instrumentSeparator:
            [ModelFile(name: "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt",
                       url: URL(string: "\(mega53Release)/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt")!,
                       size: 1_368_919_887, sha256: "c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f"),
             ModelFile(name: "mvsep_mega_model_bs_roformer_53_stems.yaml",
                       url: URL(string: "\(mega53Release)/mvsep_mega_model_bs_roformer_53_stems.yaml")!,
                       size: 4_184, sha256: "7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103")]
        case .bandWriter:
            [ModelFile(name: "model.safetensors", url: URL(string: "\(hfResolve)/model.safetensors")!,
                       size: 1_228_144_472, sha256: "ac80adbdf85d87231735fd948af7013441c0afced316c4e9067fd5d8a7fb97ec"),
             ModelFile(name: "config.json", url: URL(string: "\(hfResolve)/config.json")!,
                       size: 126, gitBlob: "3862558703a8c30630ff1149b58e2f070179c774")]
        }
    }

    /// The hub cache: HF_HUB_CACHE, else HF_HOME/hub, else ~/.cache/huggingface/hub (as huggingface_hub and the
    /// engine's adapters.py resolve it).
    public static func hubCache(environment: [String: String], home: URL = FileManager.default.homeDirectoryForCurrentUser) -> URL {
        if let dir = environment["HF_HUB_CACHE"], !dir.isEmpty {
            return URL(fileURLWithPath: (dir as NSString).expandingTildeInPath, isDirectory: true)
        }
        if let hf = environment["HF_HOME"], !hf.isEmpty {
            return URL(fileURLWithPath: (hf as NSString).expandingTildeInPath, isDirectory: true).appending(path: "hub")
        }
        return home.appending(path: ".cache/huggingface/hub", directoryHint: .isDirectory)
    }

    /// `models--MuScriptor--muscriptor-medium` in the hub cache.
    public static func hubRepoFolder(_ repo: String, hub: URL) -> URL {
        hub.appending(path: "models--" + repo.replacingOccurrences(of: "/", with: "--"), directoryHint: .isDirectory)
    }
}
