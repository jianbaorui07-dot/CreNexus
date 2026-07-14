(function () {
    var config = STARBRIDGE_CONFIG || {};
    var doc = null;

    function closeWithoutSaving() {
        if (!doc) {
            return;
        }
        try {
            doc.close(SaveOptions.DONOTSAVECHANGES);
        } catch (ignoredClose) {
        }
        doc = null;
    }

    function fail(message, steps) {
        closeWithoutSaving();
        return JSON.stringify({
            ok: false,
            bridge: "illustrator",
            task: "color_vectorize",
            verdict: "blocked",
            reference_id: config.referenceId,
            warnings: [message],
            next_steps: steps || ["Inspect the dry-run plan and retry in an authorized Illustrator session."]
        });
    }

    try {
        var inputFile = new File(config.inputPath);
        if (!inputFile.exists) {
            return fail("The explicitly supplied input file is unavailable.");
        }

        doc = app.documents.add(DocumentColorSpace.RGB);
        doc.rulerUnits = RulerUnits.Pixels;

        var sourceLayer = doc.layers[0];
        sourceLayer.name = "source_trace";
        var placed = doc.placedItems.add();
        placed.file = inputFile;
        app.redraw();

        var sourceWidth = Math.max(1, Number(placed.width));
        var sourceHeight = Math.max(1, Number(placed.height));
        doc.artboards[0].artboardRect = [0, sourceHeight, sourceWidth, 0];
        placed.position = [0, sourceHeight];

        var plugin = placed.trace();
        var tracing = plugin.tracing;
        var options = tracing.tracingOptions;
        options.tracingMode = TracingModeType.TRACINGMODECOLOR;
        options.fills = true;
        options.strokes = false;
        options.maxColors = Number(config.maxColors);
        options.pathFitting = Number(config.pathFitting);
        options.minArea = Number(config.minArea);
        options.preprocessBlur = Number(config.preprocessBlur);
        options.ignoreWhite = Boolean(config.ignoreWhite);
        options.outputToSwatches = Boolean(config.outputToSwatches);

        var redrawCount = 0;
        do {
            app.redraw();
            redrawCount += 1;
        } while (Number(tracing.anchorCount) === 0 && redrawCount < 8);

        var traceMetrics = {
            anchor_count: Number(tracing.anchorCount),
            path_count: Number(tracing.pathCount),
            area_count: Number(tracing.areaCount),
            used_color_count: Number(tracing.usedColorCount),
            image_resolution: Number(tracing.imageResolution),
            redraw_count: redrawCount
        };
        if (traceMetrics.anchor_count <= 0 || traceMetrics.path_count <= 0) {
            return fail(
                "Illustrator did not produce a completed vector trace.",
                ["Retry with a supported PNG/JPEG or adjust the trace settings after reviewing the dry-run plan."]
            );
        }

        var expanded = tracing.expandTracing(false);
        expanded.name = "starbridge_color_vector";
        app.redraw();

        var expandedPathCount = Number(expanded.pathItems.length);
        var openPathCount = 0;
        for (var pathIndex = 0; pathIndex < expanded.pathItems.length; pathIndex += 1) {
            if (!expanded.pathItems[pathIndex].closed) {
                openPathCount += 1;
            }
        }
        traceMetrics.expanded_path_count = expandedPathCount;
        traceMetrics.open_path_count = openPathCount;

        var remainingRasterCount = Number(doc.placedItems.length) + Number(doc.rasterItems.length);
        if (remainingRasterCount !== 0) {
            return fail(
                "Expanded output still contains raster artwork.",
                ["Do not deliver this result as an editable vector; inspect the local Illustrator trace."]
            );
        }

        var aiOptions = new IllustratorSaveOptions();
        aiOptions.pdfCompatible = true;
        doc.saveAs(new File(config.aiPath), aiOptions);

        var svgOptions = new ExportOptionsSVG();
        svgOptions.embedRasterImages = false;
        svgOptions.fontType = SVGFontType.OUTLINEFONT;
        doc.exportFile(new File(config.svgPath), ExportType.SVG, svgOptions);

        var pngOptions = new ExportOptionsPNG24();
        pngOptions.antiAliasing = true;
        pngOptions.transparency = true;
        pngOptions.artBoardClipping = true;
        pngOptions.horizontalScale = 100;
        pngOptions.verticalScale = 100;
        doc.exportFile(new File(config.pngPath), ExportType.PNG24, pngOptions);

        var result = {
            ok: true,
            bridge: "illustrator",
            task: "color_vectorize",
            verdict: "needs_visual_review",
            reference_id: config.referenceId,
            input_sha256: config.inputHash,
            source_summary: {
                width_points: sourceWidth,
                height_points: sourceHeight
            },
            trace_metrics: traceMetrics,
            embedded_raster_count: remainingRasterCount,
            topology_valid: openPathCount === 0,
            editable_vector_present: expandedPathCount > 0 && remainingRasterCount === 0,
            outputs: {
                illustrator_document: config.aiPathRelative,
                svg: config.svgPathRelative,
                preview_png: config.pngPathRelative
            },
            warnings: [
                "Files were generated locally, but color and silhouette comparison has not yet passed."
            ],
            next_steps: [
                "Compare the PNG preview with the authorized reference.",
                "Call illustrator.color_vectorize_compare with the sandbox PNG and trace evidence."
            ]
        };
        closeWithoutSaving();
        return JSON.stringify(result);
    } catch (error) {
        return fail("Illustrator color trace failed without exposing local file details.");
    }
}());
