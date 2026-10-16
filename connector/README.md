# Caerness connector

A local MCP server so the Claude desktop app can play Caerness. Claude is the game master; the engine is memory and consequence.

1. Install requirements: `python -m pip install -r connector/requirements.txt` (Python 3.13).
2. Create a campaign and choose the protagonist:
   `python connector/setup_campaign.py --campaign main --actor "<full name>"`
   (campaigns are copies of `data/caerness.db` under `%LOCALAPPDATA%\Caerness\campaigns`).
3. Add this to `%APPDATA%\Claude\claude_desktop_config.json` (merge with any existing servers):
   ```json
   {"mcpServers": {"caerness": {
     "command": "C:\\Users\\NozzE\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
     "args": ["D:\\Code\\Caerness\\connector\\run_server.py"],
     "env": {"CAERNESS_CAMPAIGN": "main"}}}}
   ```
4. Restart the Claude desktop app.
5. In a new chat type `resume`.

Tools: `resume`, `scene`, `lookup`, `act`, `advance`, `note`. Mutating tools need a fresh `call_id`; reuse it only to retry the same call. Stdout is the protocol channel, so everything the engine prints is sent to stderr.

Note: the SDK pinned here is mcp 2.x, where `FastMCP` is named `MCPServer` (`mcp.server.mcpserver`).
