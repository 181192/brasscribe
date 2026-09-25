// Datasets and models: licences, sizes, hashes, presence and the device each adapter uses.
import { api } from "../api/client";
import { clear, errorNotice, fmt, h, loading, pill, table } from "../ui/dom";

export function registryView(root: HTMLElement): void {
  const models = h("div", {}, loading());
  const data = h("div", {}, loading());
  clear(root, h("h1", {}, "Datasets and models"),
    h("section", { "aria-labelledby": "ad-h" }, h("h2", { id: "ad-h" }, "Adapters and model weights"), models),
    h("section", { "aria-labelledby": "ds-h" }, h("h2", { id: "ds-h" }, "Datasets"), data));

  api.adapters().then((list) => clear(models,
    table("Adapters", ["Adapter", "Version", "Device", "Heavy", "Licence", "Fingerprint"], list.map((a) => [
      h("span", { class: "mono" }, a.name), a.version ?? "–", a.device, a.heavy ? "yes (GPU mutex)" : "no", a.licence ?? "not stated", h("span", { class: "mono small" }, fmt.hash(a.fingerprint)),
    ])),
    table("Model files", ["Adapter", "File", "Size", "SHA-256", "Revision", "Licence", "Present"], list.flatMap((a) => a.models.map((m) => [
      h("span", { class: "mono" }, a.name), h("span", { class: "mono small" }, m.name), fmt.bytes(m.bytes), h("span", { class: "mono small" }, fmt.hash(m.sha256)),
      m.revision ?? "–", m.licence ?? "not stated", pill(m.present ? "ok" : "missing"),
    ]))))).catch((e) => clear(models, errorNotice(e)));

  api.datasets().then((list) => clear(data,
    table("Datasets", ["Dataset", "Path", "Items", "Files", "Size", "Licence", "Source", "Cached model outputs", "Present"], list.map((d) => [
      h("span", { class: "mono" }, d.name), h("span", { class: "mono small" }, d.path), String(d.items), String(d.files), fmt.bytes(d.bytes),
      d.licence ?? "not stated", d.source_url ? h("a", { href: d.source_url }, "source") : "–",
      d.cached_outputs.length ? d.cached_outputs.join(", ") : "–", pill(d.present ? "ok" : "missing"),
    ])),
    list.some((d) => d.download) ? h("section", {}, h("h3", {}, "Download help"),
      list.filter((d) => d.download).map((d) => h("div", {}, h("h4", { class: "mono" }, d.name), h("pre", { class: "json", tabindex: 0 }, d.download!)))) : null,
  )).catch((e) => clear(data, errorNotice(e)));
}
