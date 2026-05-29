(function () {
    function fail(message, steps) {
        return JSON.stringify({
            ok: false,
            bridge: "photoshop",
            task: "document_info",
            active_document: false,
            width: null,
            height: null,
            color_mode: null,
            layer_count: 0,
            path: null,
            warnings: [message],
            next_steps: steps
        });
    }

    if (app.documents.length === 0) {
        return fail(
            "No active Photoshop document is open.",
            [
                "Open a document manually if you need metadata for the current session.",
                "Run the sandbox demo command if you want to create a public test PSD."
            ]
        );
    }

    var doc = app.activeDocument;
    var hasFullName = false;
    try {
        hasFullName = !!doc.fullName;
    } catch (ignored) {
        hasFullName = false;
    }

    return JSON.stringify({
        ok: true,
        bridge: "photoshop",
        task: "document_info",
        active_document: doc.name,
        width: Number(doc.width.value),
        height: Number(doc.height.value),
        color_mode: String(doc.mode),
        layer_count: doc.layers.length,
        path: hasFullName ? "<REDACTED_PATH>" : null,
        warnings: [],
        next_steps: []
    });
}());
