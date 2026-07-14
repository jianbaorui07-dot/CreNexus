(function () {
    var config = STARBRIDGE_CONFIG || {};
    var doc = null;
    var previousDialogs = app.displayDialogs;

    function closeWithoutSaving() {
        if (doc) {
            try {
                doc.close(SaveOptions.DONOTSAVECHANGES);
            } catch (ignoredClose) {
            }
            doc = null;
        }
        app.displayDialogs = previousDialogs;
    }

    function fail(message, steps) {
        closeWithoutSaving();
        return JSON.stringify({
            ok: false,
            bridge: "photoshop",
            action: "color_preprocess",
            verdict: "blocked",
            reference_id: config.referenceId,
            warnings: [message],
            next_steps: steps || ["Review the dry-run plan and retry in an authorized Photoshop session."]
        });
    }

    function pixels(value) {
        return Number(value.as("px"));
    }

    try {
        var inputFile = new File(config.inputPath);
        var outputFile = new File(config.outputPath);
        if (!inputFile.exists) {
            return fail("The sandbox source copy is unavailable.");
        }

        app.displayDialogs = DialogModes.NO;
        doc = app.open(inputFile);
        var sourceWidth = Math.max(1, pixels(doc.width));
        var sourceHeight = Math.max(1, pixels(doc.height));
        var sourceMode = String(doc.mode);
        var sourceBitDepth = Number(doc.bitsPerChannel);

        if (doc.mode !== DocumentMode.RGB) {
            doc.changeMode(ChangeMode.RGB);
        }

        var profileAction = "preserved";
        if (Boolean(config.normalizeSrgb)) {
            try {
                doc.convertProfile("sRGB IEC61966-2.1", Intent.PERCEPTUAL, true, true);
                profileAction = "converted_to_srgb";
            } catch (profileError) {
                return fail(
                    "Photoshop could not convert the sandbox copy to sRGB.",
                    ["Disable normalization only after manually confirming the source profile is safe for Illustrator."]
                );
            }
        }

        if (doc.bitsPerChannel !== BitsPerChannelType.EIGHT) {
            doc.bitsPerChannel = BitsPerChannelType.EIGHT;
        }

        var medianRadius = Number(config.medianRadius);
        if (medianRadius > 0) {
            doc.activeLayer.applyMedianNoise(medianRadius);
        }

        var currentWidth = Math.max(1, pixels(doc.width));
        var currentHeight = Math.max(1, pixels(doc.height));
        var longestEdge = Math.max(currentWidth, currentHeight);
        var maxDimension = Number(config.maxDimension);
        var resized = false;
        if (longestEdge > maxDimension) {
            var scale = maxDimension / longestEdge;
            var targetWidth = Math.max(1, Math.round(currentWidth * scale));
            var targetHeight = Math.max(1, Math.round(currentHeight * scale));
            doc.resizeImage(
                UnitValue(targetWidth, "px"),
                UnitValue(targetHeight, "px"),
                null,
                ResampleMethod.BICUBICSHARPER
            );
            resized = true;
        }

        var pngOptions = new PNGSaveOptions();
        pngOptions.interlaced = false;
        doc.saveAs(outputFile, pngOptions, true, Extension.LOWERCASE);
        if (!outputFile.exists) {
            return fail("Photoshop did not create the expected sandbox PNG.");
        }

        var result = {
            ok: true,
            bridge: "photoshop",
            action: "color_preprocess",
            verdict: "prepared",
            reference_id: config.referenceId,
            source_summary: {
                width: sourceWidth,
                height: sourceHeight,
                mode: sourceMode,
                bit_depth: sourceBitDepth
            },
            prepared_summary: {
                width: Math.max(1, pixels(doc.width)),
                height: Math.max(1, pixels(doc.height)),
                mode: "RGB",
                bit_depth: 8,
                alpha_preserved: true
            },
            operations: {
                profile_action: profileAction,
                resized: resized,
                median_radius: medianRadius,
                no_upscale: true
            },
            outputs: {
                source_copy: config.sourceCopyRelative,
                prepared_png: config.outputPathRelative
            },
            warnings: [],
            next_steps: [
                "Pass the prepared sandbox PNG to the fixed Illustrator color trace.",
                "Compare the Illustrator PNG against the original authorized reference."
            ]
        };
        closeWithoutSaving();
        return JSON.stringify(result);
    } catch (error) {
        return fail("Photoshop color preprocessing failed without exposing local file details.");
    }
}());
