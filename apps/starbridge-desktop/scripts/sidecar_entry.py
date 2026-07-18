import sys

from starbridge_mcp.backend import main as backend_main
from starbridge_mcp.mcp_server import main as mcp_main

if __name__ == "__main__":
    if sys.argv[1:] == ["--mcp"]:
        mcp_main()
    else:
        backend_main()
