// Datasets and models: licences, sizes, hashes, presence and the device each adapter uses.
import { api } from "../api/client";
import { t } from "../i18n";
import { clear, errorNotice, fmt, h, loading, pill, table } from "../ui/dom";

export function registryView(root: HTMLElement): void {
  const models = h("div", {}, loading());
  const data = h("div", {}, loading());
  clear(root, h("h1", {}, t("nav.registry")),
    h("section", { "aria-labelledby": "ad-h" }, h("h2", { id: "ad-h" }, t("reg.adapters")), models),
    h("section", { "aria-labelledby": "ds-h" }, h("h2", { id: "ds-h" }, t("reg.datasets")), data));

  api.adapters().then((list) => clear(models,
    table(t("reg.adapterTable"), [t("reg.col.adapter"), t("reg.col.version"), t("reg.col.device"), t("reg.col.heavy"), t("reg.col.licence"), t("reg.col.fingerprint")], list.map((a) => [
      h("span", { class: "mono" }, a.name), a.version ?? "–", a.device, a.heavy ? t("reg.heavyYes") : t("common.no"), a.licence ?? t("common.notStated"), h("span", { class: "mono small" }, fmt.hash(a.fingerprint)),
    ])),
    table(t("reg.models"), [t("reg.col.adapter"), t("reg.col.file"), t("reg.col.size"), "SHA-256", t("reg.col.revision"), t("reg.col.licence"), t("reg.col.present")], list.flatMap((a) => a.models.map((m) => [
      h("span", { class: "mono" }, a.name), h("span", { class: "mono small" }, m.name), fmt.bytes(m.bytes), h("span", { class: "mono small" }, fmt.hash(m.sha256)),
      m.revision ?? "–", m.licence ?? t("common.notStated"), pill(m.present ? "ok" : "missing"),
    ]))))).catch((e) => clear(models, errorNotice(e)));

  api.datasets().then((list) => clear(data,
    table(t("reg.datasets"), [t("reg.col.dataset"), t("reg.col.path"), t("reg.col.items"), t("reg.col.files"), t("reg.col.size"), t("reg.col.licence"), t("reg.col.source"), t("reg.col.cached"), t("reg.col.present")], list.map((d) => [
      h("span", { class: "mono" }, d.name), h("span", { class: "mono small" }, d.path), String(d.items), String(d.files), fmt.bytes(d.bytes),
      d.licence ?? t("common.notStated"), d.source_url ? h("a", { href: d.source_url }, t("common.source")) : "–",
      d.cached_outputs.length ? d.cached_outputs.join(", ") : "–", pill(d.present ? "ok" : "missing"),
    ])),
    list.some((d) => d.download) ? h("section", {}, h("h3", {}, t("reg.download")),
      list.filter((d) => d.download).map((d) => h("div", {}, h("h4", { class: "mono" }, d.name), h("pre", { class: "json", tabindex: 0 }, d.download!)))) : null,
  )).catch((e) => clear(data, errorNotice(e)));
}
