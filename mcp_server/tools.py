"""
MCP Tool definitions for NoteDiscovery.

Defines all available tools, their schemas, and descriptions.
Following MCP specification for tool definitions.
"""

from typing import Any

# Tool definitions following MCP schema specification
TOOLS: list[dict[str, Any]] = [
    # =========================================================================
    # Search & Discovery
    # =========================================================================
    {
        "name": "search_notes",
        "description": "Search through all notes using full-text search. Returns matching notes with snippets showing where the match was found. Use this to find notes by content, keywords, or phrases.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Can be keywords, phrases, or natural language."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_notes",
        "description": "List all notes in the knowledge base with their metadata (title, path, last modified date, size). Use this to get an overview of available notes or find notes by browsing.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_note",
        "description": "Read the full content of a specific note by its path. Returns the complete markdown content along with metadata. Use this after finding a note via search or list to read its contents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the note (e.g., 'folder/note.md' or 'note.md')"
                }
            },
            "required": ["path"]
        }
    },
    
    # =========================================================================
    # Tags & Organization
    # =========================================================================
    {
        "name": "list_tags",
        "description": "List all tags used across notes with the count of notes for each tag. Use this to understand how notes are organized and find topics.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_notes_by_tag",
        "description": "Get all notes that have a specific tag. Use this to find related notes on a topic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag": {
                    "type": "string",
                    "description": "Tag name (without the # symbol)"
                }
            },
            "required": ["tag"]
        }
    },
    
    # =========================================================================
    # Knowledge Graph
    # =========================================================================
    {
        "name": "get_graph",
        "description": "Get the knowledge graph showing relationships between notes. Returns nodes (notes) and edges (links between them). Use this to understand how notes connect to each other.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    
    # =========================================================================
    # Note Management (Write Operations)
    # =========================================================================
    {
        "name": "create_note",
        "description": "Create a new note or update an existing one. The note will be saved as a markdown file. Use this to save new information or update existing notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path for the note (e.g., 'folder/new-note.md'). Include .md extension."
                },
                "content": {
                    "type": "string",
                    "description": "Markdown content for the note"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "delete_note",
        "description": "Delete a note permanently. Use with caution - this cannot be undone.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the note to delete"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "create_folder",
        "description": "Create a new folder for organizing notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path for the new folder (e.g., 'projects/2024')"
                }
            },
            "required": ["path"]
        }
    },
    
    # =========================================================================
    # Templates
    # =========================================================================
    {
        "name": "list_templates",
        "description": "List available note templates. Templates provide pre-formatted structures for common note types.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_template",
        "description": "Get the content of a specific template. Use this to see what a template contains before using it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Template name"
                }
            },
            "required": ["name"]
        }
    },
    
    # =========================================================================
    # System
    # =========================================================================
    {
        "name": "health_check",
        "description": "Check if NoteDiscovery server is running and healthy. Use this to verify connectivity.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]


def get_tool_names() -> list[str]:
    """Get list of all tool names."""
    return [tool["name"] for tool in TOOLS]


def get_tool_by_name(name: str) -> dict[str, Any] | None:
    """Get tool definition by name."""
    for tool in TOOLS:
        if tool["name"] == name:
            return tool
    return None
