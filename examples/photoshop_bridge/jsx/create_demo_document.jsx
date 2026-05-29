(function () {
    function rgb(r, g, b) {
        var color = new SolidColor();
        color.rgb.red = r;
        color.rgb.green = g;
        color.rgb.blue = b;
        return color;
    }

    function fillRect(doc, layerName, bounds, color) {
        var layer = doc.artLayers.add();
        layer.name = layerName;
        doc.activeLayer = layer;
        doc.selection.select(bounds);
        doc.selection.fill(color);
        doc.selection.deselect();
        return layer;
    }

    function textLayer(doc, layerName, text, size, x, y, color) {
        var layer = doc.artLayers.add();
        layer.name = layerName;
        layer.kind = LayerKind.TEXT;
        layer.textItem.contents = text;
        layer.textItem.size = size;
        layer.textItem.position = [x, y];
        layer.textItem.color = color;
        try {
            layer.textItem.font = "ArialMT";
        } catch (ignoredFont) {
        }
        return layer;
    }

    var config = STARBRIDGE_CONFIG || {};
    var width = Number(config.width || 1080);
    var height = Number(config.height || 1080);
    var dpi = Number(config.dpi || 72);

    var doc = app.documents.add(
        UnitValue(width, "px"),
        UnitValue(height, "px"),
        dpi,
        "starbridge_ps_demo",
        NewDocumentMode.RGB,
        DocumentFill.WHITE
    );

    fillRect(doc, "background", [[0, 0], [width, 0], [width, height], [0, height]], rgb(244, 246, 248));
    fillRect(doc, "color_block_left", [[80, 330], [500, 330], [500, 760], [80, 760]], rgb(47, 128, 237));
    fillRect(doc, "color_block_right", [[580, 330], [1000, 330], [1000, 760], [580, 760]], rgb(242, 153, 74));
    fillRect(doc, "color_block_footer", [[80, 820], [1000, 820], [1000, 900], [80, 900]], rgb(39, 174, 96));
    textLayer(doc, "title_text", "StarBridge PS Demo", 72, 80, 170, rgb(28, 35, 49));
    textLayer(doc, "subtitle_text", "Photoshop sandbox layer export", 34, 84, 230, rgb(80, 92, 112));

    var saveOptions = new PhotoshopSaveOptions();
    doc.saveAs(new File(config.outputPsdPath), saveOptions, true, Extension.LOWERCASE);

    return JSON.stringify({
        ok: true,
        bridge: "photoshop",
        task: "create_demo_document",
        dry_run: false,
        confirm_write: true,
        document: {
            name: "starbridge_ps_demo.psd",
            width: width,
            height: height,
            dpi: dpi,
            color_mode: "RGB"
        },
        layers_created: [
            "background",
            "color_block_left",
            "color_block_right",
            "color_block_footer",
            "title_text",
            "subtitle_text"
        ],
        output_psd_path: config.outputPsdPathRelative,
        warnings: [],
        next_steps: ["Export PNG and JPG previews from the sandbox PSD."]
    });
}());
