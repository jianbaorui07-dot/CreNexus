import asyncio
import pathlib
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


WORKSPACE = pathlib.Path(__file__).resolve().parents[1]
SERVER_PATH = WORKSPACE / "cad-mcp-autocad" / "src" / "server.py"
OUTPUT_PATH = WORKSPACE / "output" / "codex_autocad_mcp_protocol_test.dwg"


async def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
        env={"PYTHONIOENCODING": "utf-8"},
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"tool_count={len(tools.tools)}")
            print("tools=" + ",".join(tool.name for tool in tools.tools))

            rectangle = await session.call_tool(
                "draw_rectangle",
                {
                    "corner1": [0, 0, 0],
                    "corner2": [80, 40, 0],
                    "layer": "CODEX_MCP_PROTOCOL",
                    "color": "4",
                    "lineweight": 25,
                },
            )
            text = await session.call_tool(
                "draw_text",
                {
                    "position": [0, 55, 0],
                    "text": "MCP protocol call OK",
                    "height": 6,
                    "layer": "CODEX_MCP_PROTOCOL",
                    "color": "3",
                },
            )
            saved = await session.call_tool("save_drawing", {"file_path": str(OUTPUT_PATH)})

            print(f"draw_rectangle={rectangle.content[0].text if rectangle.content else rectangle}")
            print(f"draw_text={text.content[0].text if text.content else text}")
            print(f"save_drawing={saved.content[0].text if saved.content else saved}")
            print(f"output={OUTPUT_PATH}")
            print(f"exists={OUTPUT_PATH.exists()}")
            print(f"size={OUTPUT_PATH.stat().st_size if OUTPUT_PATH.exists() else 0}")


if __name__ == "__main__":
    asyncio.run(main())
