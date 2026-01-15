# 🔗 Public Sharing

Share notes publicly without requiring viewers to log in.

## How It Works

1. Open a note you want to share
2. Click the **Share** button in the toolbar
3. Click **Create Share Link**
4. Copy the generated URL and send it to anyone

The recipient can view the note in their browser - no account needed.

## Revoking Access

To stop sharing a note:
1. Open the note
2. Click the **Share** button
3. Click **Revoke Link**

The old URL will immediately stop working.

## Features

- **Theme preserved** - Shared notes display with the theme active when you created the link
- **Images embedded** - All images are included in the shared view
- **Code highlighting** - Syntax highlighting works in shared notes
- **Copy button** - Code blocks have a copy-to-clipboard button
- **MathJax & Mermaid** - Math equations and diagrams render correctly
- **No expiration** - Links work until you revoke them

## Visual Indicators

- A **share icon** appears next to shared notes in the sidebar
- The Share modal shows the current sharing status

## Technical Details

### Token Storage

Share tokens are stored in `.share-tokens.json` in your data folder:

```json
{
  "LRFEo86oSVeJ3Gju": {
    "path": "folder/note.md",
    "theme": "dracula",
    "created": "2026-01-15T10:30:00+00:00"
  }
}
```

Each note can have one share token. Creating a new link for an already-shared note returns the existing token.

### Security

- Tokens are random 16-character strings
- Only the exact token URL grants access
- Revoking deletes the token permanently
- Shared notes are read-only (viewers cannot edit)