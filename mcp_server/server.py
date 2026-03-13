"""
MCP Server implementation for NoteDiscovery.

Implements the Model Context Protocol (MCP) over stdio,
enabling AI assistants to interact with NoteDiscovery notes.

This implementation uses only Python stdlib for minimal dependencies.
"""

import json
import sys
import traceback
from typing import Any, Optional

from .config import load_config, MCPConfig
from .client import NoteDiscoveryClient, APIResponse
from .tools import TOOLS, get_tool_names


# MCP Protocol version
MCP_VERSION = "2024-11-05"

# Server info
SERVER_INFO = {
    "name": "notediscovery-mcp",
    "version": "1.0.0",
}


class MCPServer:
    """
    MCP Server that bridges AI assistants with NoteDiscovery.
    
    Implements the MCP protocol over stdio (JSON-RPC 2.0).
    """
    
    def __init__(self, config: MCPConfig) -> None:
        """
        Initialize the MCP server.
        
        Args:
            config: MCP configuration
        """
        self.config = config
        self.client = NoteDiscoveryClient(config)
        self._initialized = False
    
    def _log(self, message: str) -> None:
        """Log message to stderr (not stdout which is for MCP protocol)."""
        print(f"[notediscovery-mcp] {message}", file=sys.stderr)
    
    def _send_response(self, id: Any, result: Any = None, error: Optional[dict] = None) -> None:
        """
        Send a JSON-RPC response.
        
        Args:
            id: Request ID
            result: Result data (for success)
            error: Error object (for failure)
        """
        response: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": id,
        }
        
        if error is not None:
            response["error"] = error
        else:
            response["result"] = result
        
        # Write to stdout with newline
        print(json.dumps(response), flush=True)
    
    def _send_notification(self, method: str, params: Optional[dict] = None) -> None:
        """
        Send a JSON-RPC notification (no response expected).
        
        Args:
            method: Notification method
            params: Optional parameters
        """
        notification: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params
        
        print(json.dumps(notification), flush=True)
    
    def _error(self, code: int, message: str, data: Any = None) -> dict:
        """Create a JSON-RPC error object."""
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return error
    
    # =========================================================================
    # MCP Protocol Handlers
    # =========================================================================
    
    def handle_initialize(self, params: dict) -> dict:
        """Handle initialize request."""
        self._initialized = True
        self._log(f"Initialized with client: {params.get('clientInfo', {}).get('name', 'unknown')}")
        
        return {
            "protocolVersion": MCP_VERSION,
            "serverInfo": SERVER_INFO,
            "capabilities": {
                "tools": {},  # We support tools
            },
        }
    
    def handle_initialized(self, params: dict) -> None:
        """Handle initialized notification."""
        self._log(f"Connected to NoteDiscovery at {self.config.base_url}")
    
    def handle_list_tools(self, params: dict) -> dict:
        """Handle tools/list request."""
        return {"tools": TOOLS}
    
    def handle_call_tool(self, params: dict) -> dict:
        """
        Handle tools/call request.
        
        Dispatches to the appropriate tool handler based on tool name.
        """
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        self._log(f"Calling tool: {name}")
        
        # Dispatch to tool handler
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Unknown tool: {name}. Available tools: {', '.join(get_tool_names())}",
                }],
                "isError": True,
            }
        
        try:
            result = handler(arguments)
            return {
                "content": [{
                    "type": "text",
                    "text": result,
                }],
            }
        except Exception as e:
            self._log(f"Tool error: {e}")
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error executing {name}: {str(e)}",
                }],
                "isError": True,
            }
    
    # =========================================================================
    # Tool Implementations
    # =========================================================================
    
    def _format_response(self, response: APIResponse) -> str:
        """Format API response as readable text."""
        if not response.success:
            return f"Error: {response.error}"
        
        if response.data is None:
            return "Success (no data)"
        
        # Pretty print JSON
        return json.dumps(response.data, indent=2, ensure_ascii=False)
    
    def _tool_search_notes(self, args: dict) -> str:
        """Search notes by query."""
        query = args.get("query", "")
        if not query:
            return "Error: query is required"
        
        response = self.client.search(query)
        
        if not response.success:
            return f"Search failed: {response.error}"
        
        data = response.data or {}
        results = data.get("results", [])
        
        if not results:
            return f"No notes found matching '{query}'"
        
        # Format search results
        output = [f"Found {len(results)} result(s) for '{query}':\n"]
        for i, result in enumerate(results[:20], 1):  # Limit to 20 results
            path = result.get("path", "unknown")
            snippet = result.get("snippet", "")
            output.append(f"{i}. **{path}**")
            if snippet:
                output.append(f"   {snippet[:200]}...")
            output.append("")
        
        if len(results) > 20:
            output.append(f"... and {len(results) - 20} more results")
        
        return "\n".join(output)
    
    def _tool_list_notes(self, args: dict) -> str:
        """List all notes."""
        response = self.client.list_notes()
        
        if not response.success:
            return f"Failed to list notes: {response.error}"
        
        data = response.data or {}
        notes = data.get("notes", [])
        folders = data.get("folders", [])
        
        output = [f"Found {len(notes)} note(s) in {len(folders)} folder(s):\n"]
        
        # Group notes by folder
        notes_by_folder: dict[str, list] = {}
        for note in notes:
            path = note.get("path", "")
            folder = "/".join(path.split("/")[:-1]) or "(root)"
            if folder not in notes_by_folder:
                notes_by_folder[folder] = []
            notes_by_folder[folder].append(note)
        
        for folder in sorted(notes_by_folder.keys()):
            output.append(f"📁 {folder}/")
            for note in notes_by_folder[folder]:
                name = note.get("name", "unknown")
                modified = note.get("modified", "")
                output.append(f"   📝 {name} (modified: {modified})")
            output.append("")
        
        return "\n".join(output)
    
    def _tool_get_note(self, args: dict) -> str:
        """Get note content."""
        path = args.get("path", "")
        if not path:
            return "Error: path is required"
        
        response = self.client.get_note(path)
        
        if not response.success:
            return f"Failed to get note: {response.error}"
        
        data = response.data or {}
        content = data.get("content", "")
        metadata = data.get("metadata", {})
        
        output = [f"# {path}\n"]
        if metadata:
            output.append(f"Modified: {metadata.get('modified', 'unknown')}")
            output.append(f"Size: {metadata.get('size', 0)} bytes\n")
        output.append("---\n")
        output.append(content)
        
        return "\n".join(output)
    
    def _tool_list_tags(self, args: dict) -> str:
        """List all tags."""
        response = self.client.list_tags()
        
        if not response.success:
            return f"Failed to list tags: {response.error}"
        
        data = response.data or {}
        tags = data.get("tags", {})
        
        if not tags:
            return "No tags found in any notes."
        
        output = [f"Found {len(tags)} tag(s):\n"]
        # tags is a dict: {"tag_name": count, ...}
        for name, count in sorted(tags.items(), key=lambda x: x[1], reverse=True):
            output.append(f"  #{name} ({count} note{'s' if count != 1 else ''})")
        
        return "\n".join(output)
    
    def _tool_get_notes_by_tag(self, args: dict) -> str:
        """Get notes with a specific tag."""
        tag = args.get("tag", "")
        if not tag:
            return "Error: tag is required"
        
        response = self.client.get_notes_by_tag(tag)
        
        if not response.success:
            return f"Failed to get notes by tag: {response.error}"
        
        data = response.data or {}
        notes = data.get("notes", [])
        
        if not notes:
            return f"No notes found with tag '#{tag}'"
        
        output = [f"Notes with tag #{tag}:\n"]
        for note in notes:
            path = note.get("path", "unknown")
            output.append(f"  📝 {path}")
        
        return "\n".join(output)
    
    def _tool_get_graph(self, args: dict) -> str:
        """Get knowledge graph data."""
        response = self.client.get_graph()
        
        if not response.success:
            return f"Failed to get graph: {response.error}"
        
        data = response.data or {}
        nodes = data.get("nodes", [])
        links = data.get("links", [])
        
        output = [f"Knowledge Graph: {len(nodes)} nodes, {len(links)} connections\n"]
        
        # Find most connected notes
        connection_count: dict[str, int] = {}
        for link in links:
            source = link.get("source", "")
            target = link.get("target", "")
            connection_count[source] = connection_count.get(source, 0) + 1
            connection_count[target] = connection_count.get(target, 0) + 1
        
        if connection_count:
            output.append("Most connected notes:")
            sorted_notes = sorted(connection_count.items(), key=lambda x: x[1], reverse=True)[:10]
            for note, count in sorted_notes:
                output.append(f"  {note}: {count} connections")
        
        return "\n".join(output)
    
    def _tool_create_note(self, args: dict) -> str:
        """Create or update a note."""
        path = args.get("path", "")
        content = args.get("content", "")
        
        if not path:
            return "Error: path is required"
        if not content:
            return "Error: content is required"
        
        response = self.client.create_note(path, content)
        
        if not response.success:
            return f"Failed to create note: {response.error}"
        
        return f"✅ Note created/updated: {path}"
    
    def _tool_delete_note(self, args: dict) -> str:
        """Delete a note."""
        path = args.get("path", "")
        if not path:
            return "Error: path is required"
        
        response = self.client.delete_note(path)
        
        if not response.success:
            return f"Failed to delete note: {response.error}"
        
        return f"🗑️ Note deleted: {path}"
    
    def _tool_create_folder(self, args: dict) -> str:
        """Create a folder."""
        path = args.get("path", "")
        if not path:
            return "Error: path is required"
        
        response = self.client.create_folder(path)
        
        if not response.success:
            return f"Failed to create folder: {response.error}"
        
        return f"📁 Folder created: {path}"
    
    def _tool_list_templates(self, args: dict) -> str:
        """List templates."""
        response = self.client.list_templates()
        
        if not response.success:
            return f"Failed to list templates: {response.error}"
        
        data = response.data or {}
        templates = data.get("templates", [])
        
        if not templates:
            return "No templates available."
        
        output = ["Available templates:\n"]
        for template in templates:
            name = template.get("name", "unknown")
            output.append(f"  📄 {name}")
        
        return "\n".join(output)
    
    def _tool_get_template(self, args: dict) -> str:
        """Get template content."""
        name = args.get("name", "")
        if not name:
            return "Error: name is required"
        
        response = self.client.get_template(name)
        
        if not response.success:
            return f"Failed to get template: {response.error}"
        
        data = response.data or {}
        content = data.get("content", "")
        
        return f"Template: {name}\n---\n{content}"
    
    def _tool_health_check(self, args: dict) -> str:
        """Check server health."""
        response = self.client.health_check()
        
        if not response.success:
            return f"❌ NoteDiscovery is not reachable: {response.error}"
        
        return f"✅ NoteDiscovery is healthy at {self.config.base_url}"
    
    # =========================================================================
    # Main Loop
    # =========================================================================
    
    def handle_request(self, request: dict) -> None:
        """
        Handle a single JSON-RPC request.
        
        Args:
            request: Parsed JSON-RPC request
        """
        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})
        
        try:
            # Route to handler
            if method == "initialize":
                result = self.handle_initialize(params)
                self._send_response(request_id, result)
            
            elif method == "notifications/initialized":
                self.handle_initialized(params)
                # Notifications don't get responses
            
            elif method == "tools/list":
                result = self.handle_list_tools(params)
                self._send_response(request_id, result)
            
            elif method == "tools/call":
                result = self.handle_call_tool(params)
                self._send_response(request_id, result)
            
            elif method == "ping":
                self._send_response(request_id, {})
            
            else:
                # Unknown method
                if request_id is not None:
                    self._send_response(
                        request_id,
                        error=self._error(-32601, f"Method not found: {method}")
                    )
        
        except Exception as e:
            self._log(f"Error handling {method}: {e}")
            traceback.print_exc(file=sys.stderr)
            if request_id is not None:
                self._send_response(
                    request_id,
                    error=self._error(-32603, f"Internal error: {str(e)}")
                )
    
    def run(self) -> None:
        """
        Run the MCP server, reading requests from stdin.
        
        This is the main event loop that processes JSON-RPC messages.
        """
        self._log("Starting MCP server...")
        self._log(f"NoteDiscovery URL: {self.config.base_url}")
        
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            try:
                request = json.loads(line)
                self.handle_request(request)
            except json.JSONDecodeError as e:
                self._log(f"Invalid JSON: {e}")
                # Send parse error
                self._send_response(
                    None,
                    error=self._error(-32700, f"Parse error: {str(e)}")
                )
        
        self._log("Server shutting down")


def main() -> None:
    """
    Main entry point for the MCP server.
    
    Loads configuration from environment variables and starts the server.
    """
    try:
        config = load_config()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    
    server = MCPServer(config)
    
    try:
        server.run()
    except KeyboardInterrupt:
        print("\n[notediscovery-mcp] Interrupted", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"[notediscovery-mcp] Fatal error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
