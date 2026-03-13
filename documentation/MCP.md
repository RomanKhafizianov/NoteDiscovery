# MCP Integration (AI Assistants)

NoteDiscovery includes a built-in **Model Context Protocol (MCP)** server that enables AI assistants like **Cursor**, **Claude Desktop**, and other MCP-compatible clients to interact with your notes.

## What is MCP?

MCP (Model Context Protocol) is an open standard that allows AI assistants to securely access external tools and data sources. With the NoteDiscovery MCP server, your AI assistant can:

- 🔍 **Search** through your notes
- 📖 **Read** note contents
- 🏷️ **Browse** by tags
- 📝 **Create** new notes
- 🔗 **Explore** the knowledge graph

## Quick Setup

### If You Use Docker

Add this to your `~/.cursor/mcp.json` (or Claude Desktop config):

```json
{
  "mcpServers": {
    "notediscovery": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "NOTEDISCOVERY_URL",
        "-e", "NOTEDISCOVERY_API_KEY",
        "ghcr.io/gamosoft/notediscovery:latest",
        "python", "-m", "mcp_server"
      ],
      "env": {
        "NOTEDISCOVERY_URL": "http://host.docker.internal:8000",
        "NOTEDISCOVERY_API_KEY": ""
      }
    }
  }
}
```

### If You Use Python

1. **Install NoteDiscovery** (if not already):
   ```bash
   pip install notediscovery
   # or from source:
   pip install .
   ```

2. **Add to your MCP config:**
   ```json
   {
     "mcpServers": {
       "notediscovery": {
         "command": "notediscovery-mcp",
         "env": {
           "NOTEDISCOVERY_URL": "http://localhost:8000",
           "NOTEDISCOVERY_API_KEY": ""
         }
       }
     }
   }
   ```

### Running from Source (No Install)

```json
{
  "mcpServers": {
    "notediscovery": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/NoteDiscovery",
      "env": {
        "PYTHONPATH": "/path/to/NoteDiscovery",
        "NOTEDISCOVERY_URL": "http://localhost:8000"
      }
    }
  }
}
```

> **Note:** The `PYTHONPATH` is required so Python can find the `mcp_server` module. On Windows, use backslashes: `"PYTHONPATH": "C:\\path\\to\\NoteDiscovery"`

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NOTEDISCOVERY_URL` | Yes | `http://localhost:8000` | URL where NoteDiscovery is running |
| `NOTEDISCOVERY_API_KEY` | If auth enabled | - | API key from `config.yaml` |
| `NOTEDISCOVERY_TIMEOUT` | No | `30` | Request timeout in seconds |
| `NOTEDISCOVERY_MAX_RETRIES` | No | `3` | Max retry attempts for failed requests |

### URL Configuration by Setup

| Your Setup | `NOTEDISCOVERY_URL` |
|------------|---------------------|
| Local Python (`run.py`) | `http://localhost:8000` |
| Docker with `-p 8000:8000` | `http://host.docker.internal:8000` |
| Docker with `-p 3000:8000` | `http://host.docker.internal:3000` |
| Remote server | `https://notes.example.com` |

## Available Tools

The MCP server provides these tools to AI assistants:

### Search & Discovery

| Tool | Description |
|------|-------------|
| `search_notes` | Full-text search across all notes |
| `list_notes` | List all notes with metadata |
| `get_note` | Read a specific note's content |

### Organization

| Tool | Description |
|------|-------------|
| `list_tags` | List all tags with note counts |
| `get_notes_by_tag` | Find notes with a specific tag |
| `get_graph` | Get knowledge graph data |

### Note Management

| Tool | Description |
|------|-------------|
| `create_note` | Create or update a note |
| `delete_note` | Delete a note |
| `create_folder` | Create a new folder |

### Templates

| Tool | Description |
|------|-------------|
| `list_templates` | List available templates |
| `get_template` | Get template content |

### System

| Tool | Description |
|------|-------------|
| `health_check` | Verify server connectivity |

## Usage Examples

Once configured, you can interact with your notes naturally:

> **User:** "What did I write about Kubernetes?"
> 
> **AI:** *Uses `search_notes` to find relevant notes, then `get_note` to read them*
> 
> "I found 3 notes about Kubernetes. In your 'devops/k8s-setup.md' note from last week, you documented..."

> **User:** "Create a new note summarizing our conversation"
> 
> **AI:** *Uses `create_note` to save the summary*
> 
> "Done! I've created 'meetings/ai-discussion-2024-03-13.md' with the summary."

> **User:** "Show me all notes tagged with #project"
> 
> **AI:** *Uses `get_notes_by_tag` to find them*
> 
> "You have 7 notes with the #project tag..."

## Authentication

If you have authentication enabled in NoteDiscovery:

1. Generate an API key in `config.yaml`:
   ```yaml
   authentication:
     enabled: true
     api_key: "your-secure-api-key-here"
   ```

2. Add the key to your MCP config:
   ```json
   "env": {
     "NOTEDISCOVERY_URL": "http://localhost:8000",
     "NOTEDISCOVERY_API_KEY": "your-secure-api-key-here"
   }
   ```

## Troubleshooting

### "Connection refused" error

- Ensure NoteDiscovery is running
- Check the `NOTEDISCOVERY_URL` is correct
- For Docker: use `host.docker.internal` instead of `localhost`

### "Not authenticated" error

- Check that your API key is correct
- Ensure the API key in MCP config matches `config.yaml`

### MCP server not starting

- Check Cursor/Claude Desktop logs for errors
- Try running manually: `python -m mcp_server`
- Verify Python 3.10+ is installed

### Verify connectivity manually

```bash
# Set environment variables
export NOTEDISCOVERY_URL=http://localhost:8000
export NOTEDISCOVERY_API_KEY=your-key

# Run the MCP server (Ctrl+C to stop)
python -m mcp_server
```

Then in another terminal:
```bash
# Test the health endpoint directly
curl http://localhost:8000/health
```

## Architecture

```
┌─────────────────┐     stdio (JSON-RPC)     ┌─────────────────┐
│   AI Assistant  │ ◄──────────────────────► │   MCP Server    │
│ (Cursor/Claude) │                          │ (notediscovery- │
└─────────────────┘                          │      mcp)       │
                                             └────────┬────────┘
                                                      │
                                                      │ HTTP/REST
                                                      ▼
                                             ┌─────────────────┐
                                             │  NoteDiscovery  │
                                             │     Server      │
                                             │  (port 8000)    │
                                             └─────────────────┘
                                                      │
                                                      ▼
                                             ┌─────────────────┐
                                             │   Your Notes    │
                                             │  (./data/*.md)  │
                                             └─────────────────┘
```

The MCP server is a **separate process** that:
1. Communicates with AI assistants via stdio (stdin/stdout)
2. Translates MCP requests into HTTP API calls
3. Returns results back to the AI assistant

Your notes stay local. The MCP server just provides a bridge for AI access.

## Privacy & Security

- **Notes stay local**: The MCP server only accesses notes through NoteDiscovery's API
- **No external calls**: No data is sent to external services
- **API key protected**: Use authentication to control access
- **Read what you allow**: AI can only access notes NoteDiscovery serves

## File Structure

```
NoteDiscovery/
├── mcp_server/
│   ├── __init__.py      # Package entry point
│   ├── __main__.py      # Module runner
│   ├── server.py        # MCP protocol implementation
│   ├── client.py        # HTTP client for NoteDiscovery API
│   ├── config.py        # Configuration management
│   └── tools.py         # Tool definitions
└── ...
```
