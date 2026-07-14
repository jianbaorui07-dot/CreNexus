function loadHostModule() {
  for (const name of ["illustrator", "application"]) {
    try { const value = require(name); if (value) return value; } catch (_error) {}
  }
  return null;
}

function number(value, fallback = 0) { const result = Number(value); return Number.isFinite(result) ? result : fallback; }
function text(value, fallback = "") { return value === undefined || value === null ? fallback : String(value); }
function list(value) { try { return Array.from(value || []); } catch (_error) { return []; } }

export class IllustratorHostAdapter {
  constructor() {
    this.module = loadHostModule();
    this.app = this.module?.app || this.module?.application || globalThis.app || null;
    this.objectMap = new Map();
    this.sequence = 0;
  }

  hostInfo() {
    return {app: "Adobe Illustrator", version: text(this.app?.version, "unknown"), adapter: "custom_uxp_v2"};
  }

  activeDocument() { return this.app?.activeDocument || list(this.app?.documents)[0] || null; }

  pageItems(document) { return list(document?.pageItems || document?.items); }

  itemSummary(item, index) {
    const objectId = `item:${index + 1}`;
    this.objectMap.set(objectId, item);
    return {
      object_id: objectId,
      type: text(item?.typename || item?.constructor?.name, "PageItem"),
      selected: Boolean(item?.selected),
      locked: Boolean(item?.locked),
      hidden: Boolean(item?.hidden),
    };
  }

  state() {
    const document = this.activeDocument();
    this.objectMap.clear();
    this.sequence += 1;
    const capturedAt = new Date().toISOString();
    if (!document) return {type: "state", protocol_version: 2, sequence: this.sequence, host: this.hostInfo(), document: null, selection: [], layers: [], artboards: [], zoom: null, tool: null, captured_at: capturedAt};
    const items = this.pageItems(document).slice(0, 512).map((item, index) => this.itemSummary(item, index));
    const selectedIds = new Set(list(document.selection || this.app?.selection).map(item => item));
    const selection = items.filter((summary) => summary.selected || selectedIds.has(this.objectMap.get(summary.object_id))).slice(0, 256);
    const layers = list(document.layers).slice(0, 512).map((layer, index) => ({layer_id: `layer:${index + 1}`, visible: layer?.visible !== false, locked: Boolean(layer?.locked)}));
    const artboards = list(document.artboards).slice(0, 128).map((board, index) => ({artboard_id: `artboard:${index + 1}`, rect: list(board?.artboardRect || board?.rect).slice(0, 4).map(value => number(value))}));
    const view = list(document.views)[0] || document.activeView || null;
    return {
      type: "state", protocol_version: 2, sequence: this.sequence, host: this.hostInfo(),
      document: {page_items: this.pageItems(document).length, layer_count: layers.length, artboard_count: artboards.length, color_space: text(document.documentColorSpace || document.colorSpace)},
      selection, layers, artboards, zoom: view ? number(view.zoom, null) : null,
      tool: text(this.app?.currentTool, "") || null, captured_at: capturedAt,
    };
  }

  resolveItem(objectId) { const item = this.objectMap.get(String(objectId)); if (!item) throw new Error("object_id_not_found_refresh_state"); return item; }

  async execute(method, params) {
    if (method === "illustrator.get_state" || method === "illustrator.document_info") return this.state();
    const document = this.activeDocument();
    if (!document) throw new Error("active_document_required");
    if (method === "illustrator.select_object") {
      const item = this.resolveItem(params.object_id);
      try { document.selection = null; } catch (_error) {}
      item.selected = true; return {ok: true, object_id: params.object_id};
    }
    if (method === "illustrator.set_fill") {
      if (!/^#[0-9a-fA-F]{6}$/.test(String(params.color || ""))) throw new Error("color_must_be_hex_rgb");
      const item = this.resolveItem(params.object_id); item.filled = true;
      const hex = params.color.slice(1); const rgb = {red: parseInt(hex.slice(0,2),16), green: parseInt(hex.slice(2,4),16), blue: parseInt(hex.slice(4,6),16)};
      if (this.module?.RGBColor) { const color = new this.module.RGBColor(); Object.assign(color, rgb); item.fillColor = color; }
      else { item.fillColor = rgb; }
      return {ok: true, object_id: params.object_id, color: params.color};
    }
    if (method === "illustrator.move_object") {
      const item = this.resolveItem(params.object_id); const dx = number(params.dx); const dy = number(params.dy);
      if (Math.abs(dx) > 10000 || Math.abs(dy) > 10000) throw new Error("translation_out_of_range");
      if (typeof item.translate === "function") await item.translate(dx, dy); else { item.left = number(item.left) + dx; item.top = number(item.top) + dy; }
      return {ok: true, object_id: params.object_id, dx, dy};
    }
    if (method === "illustrator.create_path") {
      const points = params.points; if (!Array.isArray(points) || points.length < 2 || points.length > 512) throw new Error("points_count_out_of_range");
      const collection = document.pathItems; if (!collection?.add) throw new Error("host_path_api_unavailable");
      const path = await collection.add();
      if (typeof path.setEntirePath === "function") await path.setEntirePath(points); else path.pathPoints = points;
      path.closed = Boolean(params.closed); path.stroked = true; path.filled = false;
      return {ok: true, created_type: "PathItem"};
    }
    if (method === "illustrator.zoom_to_selection") {
      const view = list(document.views)[0] || document.activeView;
      if (typeof view?.fitSelection === "function") await view.fitSelection();
      else if (typeof this.app?.executeMenuCommand === "function") await this.app.executeMenuCommand("fitin");
      else throw new Error("host_zoom_api_unavailable");
      return {ok: true};
    }
    throw new Error("method_not_implemented");
  }
}
