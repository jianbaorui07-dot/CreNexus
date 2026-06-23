# Codex + Adobe AI / Creative Software Integration Map

This note collects practical reference cases for connecting Codex or other AI agents to Adobe creative tools. It is a research and architecture map for StarBridge, not a claim that every integration is production-ready in this repository.

## Reference Cases

| Reference | What it shows | Relevance to StarBridge |
| --- | --- | --- |
| [Adobe Illustrator official MCP / Codex support](https://helpx.adobe.com/in/illustrator/desktop/connect-with-other-apps-and-tools/connect-illustrator-to-ai-tools.html) | Adobe documents a direct Illustrator Beta MCP path for Claude Code, Codex, and other AI tools. | Most direct official route for Codex to control Illustrator through MCP. |
| [mikechambers/adb-mcp](https://github.com/mikechambers/adb-mcp) | MCP proof of concept for controlling Photoshop and Premiere through a Node proxy and Adobe UXP plugin. | Useful reference for the agent -> MCP -> proxy -> UXP -> Adobe app architecture. |
| [alisaitteke/photoshop-mcp](https://github.com/alisaitteke/photoshop-mcp) | Photoshop MCP server with a large set of Photoshop automation tools and local UI. | Shows how a desktop creative app can expose typed actions to agent clients. |
| [dcc-mcp/dcc-mcp-photoshop](https://github.com/dcc-mcp/dcc-mcp-photoshop) | More structured Photoshop MCP backend with a UXP bridge and broker. | Useful pattern for document inspection, layer operations, text, filters, and export tools. |
| [ghhutch/n8n-firefly-agent](https://github.com/ghhutch/n8n-firefly-agent) | n8n workflow with a chat agent, Ollama, and Adobe Firefly Services image generation. | Good example of an agentic creative-director workflow using Firefly API. |
| [ahmed-musallam/n8n-nodes-firefly-services](https://github.com/ahmed-musallam/n8n-nodes-firefly-services) | n8n nodes for Firefly Services, Photoshop API, audio/video APIs, generative fill, expand, and related operations. | Practical workflow automation bridge for Adobe hosted APIs. |
| [n8n Firefly marketing graphics workflow](https://n8n.io/workflows/13810-generate-marketing-graphics-with-adobe-firefly-slack-and-google-drive/) | Campaign brief -> Firefly API -> Google Drive -> Slack workflow. | Useful model for human-reviewed creative production workflows. |
| [Adobe App Builder MCP Server Template](https://github.com/adobe/generator-app-remote-mcp-server-generic) | Adobe official template for remote MCP servers on Adobe I/O Runtime. | Strong candidate for enterprise-grade Adobe MCP services. |

## Background References

- [Adobe Firefly API documentation](https://developer.adobe.com/firefly-services/docs/firefly-api/) covers the hosted Firefly service surface for generative creative workflows.
- [Adobe Firefly Creative Production](https://business.adobe.com/products/firefly-business/firefly-creative-production.html) describes Adobe's direction toward governed, repeatable, agentic production workflows.

## Three Integration Routes

### Route A: Codex / agent -> MCP -> Adobe desktop app

Use this route when the target output must stay editable in Illustrator, Photoshop, Premiere, or another local creative tool.

Recommended shape:

```text
Codex or other agent
  -> MCP client
  -> local or remote MCP server
  -> proxy / UXP / COM / ExtendScript layer
  -> Adobe desktop app
  -> verified export or screenshot evidence
```

Good first targets:

- Illustrator document metadata and artboard inspection.
- Illustrator vector path creation and export.
- Photoshop document and layer inspection.
- Photoshop safe sandbox edits and preview export.

### Route B: Codex -> workflow system -> Adobe Firefly API

Use this route when Firefly is a generation or concepting step rather than the final editable vector source.

Recommended shape:

```text
Codex
  -> n8n / workflow manifest / structured job
  -> Adobe Firefly Services API
  -> storage and review step
  -> optional Illustrator / Photoshop cleanup
```

This is the quickest way to ship a creative automation prototype. It is less suitable when exact CAD-like vector geometry is required.

### Route C: Enterprise Adobe service -> App Builder MCP -> Firefly / Photoshop APIs

Use this route when the integration needs governance, authentication, multi-user deployment, and a stable remote endpoint.

Recommended shape:

```text
Agent client
  -> remote MCP endpoint
  -> Adobe App Builder / Adobe I/O Runtime
  -> Adobe hosted APIs
  -> audited result handoff
```

## StarBridge Position

StarBridge should treat Adobe integrations as layered capabilities:

1. `stable`: local-safe status, probes, metadata-only inspection, dry-run plans.
2. `experimental`: sandbox file generation, local editable vector export, reviewed screenshot evidence.
3. `planned`: production desktop writes, Firefly job lifecycle, enterprise remote MCP deployment.

The repository should not include private user artwork, generated client outputs, local installation paths, tokens, Creative Cloud account data, or unreviewed real project exports.

## Near-Term Prototype Backlog

1. Add an Illustrator vector rebuild pipeline that can analyze a PDF-compatible `.ai` file locally.
2. Export structured line data, rebuilt SVG, and closed-contour simplifications without uploading source artwork.
3. Add an MCP wrapper only after the deterministic local scripts are stable.
4. Use Computer Use or Illustrator MCP for visual verification, not as the primary drawing engine.
5. Add Firefly/n8n examples only as workflow manifests unless API credentials and usage boundaries are explicitly configured.

