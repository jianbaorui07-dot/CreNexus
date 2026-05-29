(function () {
    function fail(message, steps) {
        return JSON.stringify({
            ok: false,
            bridge: "illustrator",
            task: "document_info",
            active_document: false,
            warnings: [message],
            next_steps: steps
        });
    }

    if (app.documents.length === 0) {
        return fail(
            "No active Illustrator document is open.",
            [
                "Open a document manually if you need metadata for the current session.",
                "Run the sandbox demo command if you want to create a public test document."
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

    var activeIndex = 0;
    try {
        activeIndex = doc.artboards.getActiveArtboardIndex();
    } catch (ignoredIndex) {
        activeIndex = 0;
    }

    var rect = doc.artboards[activeIndex].artboardRect;
    var width = Math.abs(rect[2] - rect[0]);
    var height = Math.abs(rect[1] - rect[3]);

    return JSON.stringify({
        ok: true,
        bridge: "illustrator",
        task: "document_info",
        active_document: true,
        document: {
            name: doc.name,
            has_full_name: hasFullName,
            path: hasFullName ? "<REDACTED_PATH>" : null,
            color_space: String(doc.documentColorSpace)
        },
        artboards: {
            count: doc.artboards.length,
            active_index: activeIndex,
            width: width,
            height: height
        },
        layers_count: doc.layers.length,
        page_items_count: doc.pageItems.length,
        text_frames_count: doc.textFrames.length,
        warnings: [],
        next_steps: []
    });
}());
