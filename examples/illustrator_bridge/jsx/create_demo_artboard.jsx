(function () {
    function rgb(r, g, b) {
        var color = new RGBColor();
        color.red = r;
        color.green = g;
        color.blue = b;
        return color;
    }

    function makeText(layer, text, size, x, y, color) {
        var frame = layer.textFrames.add();
        frame.contents = text;
        frame.position = [x, y];
        frame.textRange.characterAttributes.size = size;
        try {
            frame.textRange.characterAttributes.textFont = app.textFonts.getByName("ArialMT");
        } catch (ignoredFont) {
        }
        frame.textRange.characterAttributes.fillColor = color;
        return frame;
    }

    var config = STARBRIDGE_CONFIG || {};
    var width = Number(config.width || 1080);
    var height = Number(config.height || 1080);

    var doc = app.documents.add(DocumentColorSpace.RGB, width, height);
    doc.rulerUnits = RulerUnits.Pixels;

    var foreground = doc.layers[0];
    foreground.name = "foreground";
    var background = doc.layers.add();
    background.name = "background";
    background.zOrder(ZOrderMethod.SENDTOBACK);

    var bgRect = background.pathItems.rectangle(height, 0, width, height);
    bgRect.filled = true;
    bgRect.fillColor = rgb(245, 247, 250);
    bgRect.stroked = false;

    var title = makeText(foreground, "StarBridge AI Demo", 72, 80, height - 160, rgb(28, 35, 49));
    title.name = "title_text";
    var subtitle = makeText(foreground, "Illustrator sandbox vector export", 34, 84, height - 220, rgb(76, 90, 112));
    subtitle.name = "subtitle_text";

    var circle = foreground.pathItems.ellipse(height - 340, 110, 240, 240);
    circle.name = "demo_circle";
    circle.filled = true;
    circle.fillColor = rgb(44, 123, 229);
    circle.stroked = false;

    var rect = foreground.pathItems.rectangle(height - 390, 410, 260, 180);
    rect.name = "demo_rectangle";
    rect.filled = true;
    rect.fillColor = rgb(246, 173, 85);
    rect.stroked = false;

    var line = foreground.pathItems.add();
    line.name = "demo_line";
    line.setEntirePath([[110, 360], [970, 360]]);
    line.filled = false;
    line.stroked = true;
    line.strokeWidth = 10;
    line.strokeColor = rgb(38, 166, 154);

    var path = foreground.pathItems.add();
    path.name = "demo_path";
    path.setEntirePath([[710, 650], [850, 820], [980, 610], [900, 500], [760, 540]]);
    path.closed = true;
    path.filled = true;
    path.fillColor = rgb(218, 83, 84);
    path.stroked = false;

    var accent = foreground.pathItems.rectangle(160, 84, width - 168, 24);
    accent.name = "demo_accent_bar";
    accent.filled = true;
    accent.fillColor = rgb(28, 35, 49);
    accent.stroked = false;

    doc.saveAs(new File(config.outputAiPath));

    return JSON.stringify({
        ok: true,
        bridge: "illustrator",
        task: "create_demo_artboard",
        dry_run: false,
        confirm_write: true,
        document: {
            name: "starbridge_ai_demo.ai",
            width: width,
            height: height,
            color_space: "RGB"
        },
        artboards: [{ index: 0, width: width, height: height }],
        layers: ["background", "foreground"],
        objects_created: [
            "background rectangle",
            "title text",
            "subtitle text",
            "circle",
            "rectangle",
            "line",
            "path",
            "accent bar"
        ],
        output_ai_path: config.outputAiPathRelative,
        warnings: [],
        next_steps: ["Export SVG, PNG, and PDF proof from the sandbox demo document."]
    });
}());
