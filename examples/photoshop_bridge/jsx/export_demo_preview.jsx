(function () {
    function fail(message, steps) {
        return JSON.stringify({
            ok: false,
            bridge: "photoshop",
            task: "export_demo_preview",
            exported_files: [],
            width: null,
            height: null,
            layer_count: 0,
            warnings: [message],
            next_steps: steps
        });
    }

    var config = STARBRIDGE_CONFIG || {};
    var demoFile = new File(config.demoPsdPath);
    var doc = null;

    if (app.documents.length > 0) {
        doc = app.activeDocument;
    } else if (demoFile.exists) {
        doc = app.open(demoFile);
    }

    if (!doc) {
        return fail(
            "No active demo document and no sandbox demo PSD was found.",
            ["Run create_demo_document.ps1 with ConfirmWrite before exporting."]
        );
    }

    var isDemo = doc.name === "starbridge_ps_demo.psd" || doc.name === "starbridge_ps_demo";
    try {
        isDemo = isDemo || (doc.fullName && doc.fullName.fsName === demoFile.fsName);
    } catch (ignoredPath) {
    }

    if (!isDemo) {
        return fail(
            "Refusing to export because the active document is not the StarBridge sandbox demo.",
            ["Activate starbridge_ps_demo.psd or create the sandbox demo document again."]
        );
    }

    var pngOptions = new PNGSaveOptions();
    doc.saveAs(new File(config.pngPath), pngOptions, true, Extension.LOWERCASE);

    var jpgOptions = new JPEGSaveOptions();
    jpgOptions.quality = 10;
    doc.saveAs(new File(config.jpgPath), jpgOptions, true, Extension.LOWERCASE);

    return JSON.stringify({
        ok: true,
        bridge: "photoshop",
        task: "export_demo_preview",
        exported_files: [
            config.pngPathRelative,
            config.jpgPathRelative
        ],
        width: Number(doc.width.value),
        height: Number(doc.height.value),
        layer_count: doc.layers.length,
        warnings: [],
        next_steps: ["Review the local sandbox previews and keep generated files out of Git."]
    });
}());
