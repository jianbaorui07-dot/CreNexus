# StarBridge v0.1.0 draft release notes

## Summary

StarBridge v0.1.0 is a local-first MCP bridge for creative desktop software. This release focuses on safe probes, dry-run workflows, Action Plan recipes, and enhanced Photoshop tools (get_preview, get_state) for AI agents like Codex/Cursor/Claude.

## Highlights

* Local MCP stdio server
* Safe bridge registry with BaseBridge for modularity (adapters/bridges)
* 5+ core Photoshop recipes: remove_background, enhance_portrait, frequency_separation, color_grade, prepare_for_web (with steps, safety, action_plan support)
* Action Plan mode: plan-then-execute with repair for fewer LLM roundtrips
* Photoshop: ps.get_preview (base64 for vision), ps.get_state (lightweight snapshot), enhanced previews
* ruff lint/format in CI and pre-commit for long-term quality
* Improved release process: .github/workflows/release.yml, updated install-and-publish.md, CHANGELOG
* Guarded outputs under examples/output, EvidenceManifests, redaction
* Git ignored generated assets
* CI with Windows + Ubuntu, security/preflight checks

## How to verify

```powershell
python -m unittest discover -s tests
python scripts/security_check.py
python scripts/starbridge_preflight.py --markdown
npm.cmd run starbridge:tools:safe
npm.cmd run photoshop:recipe:plan -- --recipe_id remove_background --action_plan
# Test new tools
# Use ps.get_preview and ps.get_state in your MCP client
```

## Not included

* No private PSD / AI files
* No generated binary demo assets
* No customer material
* No Image Trace automation yet
