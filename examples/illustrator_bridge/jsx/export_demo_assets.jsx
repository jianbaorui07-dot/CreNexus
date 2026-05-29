(function () {
    function fail(message, steps) {
        return JSON.stringify({
            ok: false,
            bridge: "illustrator",
            task: "export_demo_assets",
            exported_files: [],
            svg_path: STARBRIDGE_CONFIG.svgPathRelative,
            png_path: STARBRIDGE_CONFIG.pngPathRelative,
            pdf_path: STARBRIDGE_CONFIG.pdfPathRelative,
            warnings: [message],
            next_steps: steps
        });
    }

    var config = STARBRIDGE_CONFIG || {};
    var demoFile = new File(config.demoAiPath);
    var doc = null;

    if (app.documents.length > 0) {
        doc = app.activeDocument;
    } else if (demoFile.exists) {
        doc = app.open(demoFile);
    }

    if (!doc) {
        return fail(
            "No active demo document and no sandbox demo AI file was found.",
            ["Run create_demo_artboard.ps1 with ConfirmWrite before exporting."]
        );
    }

    var isDemo = doc.name === "starbridge_ai_demo.ai";
    try {
        isDemo = isDemo || (doc.fullName && doc.fullName.fsName === demoFile.fsName);
    } catch (ignoredPath) {
    }

    if (!isDemo) {
        return fail(
            "Refusing to export because the active document is not the StarBridge sandbox demo.",
            ["Activate starbridge_ai_demo.ai or create the sandbox demo document again."]
        );
    }

    var svgOptions = new ExportOptionsSVG();
    svgOptions.embedRasterImages = false;
    svgOptions.fontType = SVGFontType.OUTLINEFONT;
    doc.exportFile(new File(config.svgPath), ExportType.SVG, svgOptions);

    var pngOptions = new ExportOptionsPNG24();
    pngOptions.antiAliasing = true;
    pngOptions.transparency = false;
    pngOptions.artBoardClipping = true;
    pngOptions.horizontalScale = 100;
    pngOptions.verticalScale = 100;
    doc.exportFile(new File(config.pngPath), ExportType.PNG24, pngOptions);

    var pdfOptions = new PDFSaveOptions();
    pdfOptions.preserveEditability = false;
    doc.saveAs(new File(config.pdfPath), pdfOptions);

    return JSON.stringify({
        ok: true,
        bridge: "illustrator",
        task: "export_demo_assets",
        exported_files: [
            config.svgPathRelative,
            config.pngPathRelative,
            config.pdfPathRelative
        ],
        svg_path: config.svgPathRelative,
        png_path: config.pngPathRelative,
        pdf_path: config.pdfPathRelative,
        warnings: [],
        next_steps: ["Review the local sandbox exports and keep generated files out of Git."]
    });
}());
