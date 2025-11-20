# 📡 API Documentation

Base URL: `http://localhost:8000`

## 🗂️ Notes

### List All Notes
```http
GET /api/notes
```
Returns all notes with their metadata and folder structure.

**Example:**
```bash
curl http://localhost:8000/api/notes
```

### Get Note Content
```http
GET /api/notes/{note_path}
```
Retrieve the content of a specific note.

**Example:**
```bash
curl http://localhost:8000/api/notes/folder/mynote.md
```

### Create/Update Note
```http
POST /api/notes/{note_path}
Content-Type: application/json

{
  "content": "# My Note\nNote content here..."
}
```

**Response:**
```json
{
  "success": true,
  "path": "test.md",
  "message": "Note created successfully",
  "content": "# My Note\nNote content here..."
}
```

**Note:** When creating a new note, the `on_note_create` hook is triggered, allowing plugins to modify the initial content. The response includes the potentially modified content.

**Linux/Mac:**
```bash
curl -X POST http://localhost:8000/api/notes/test.md \
  -H "Content-Type: application/json" \
  -d '{"content": "# Hello World"}'
```

**Windows PowerShell:**
```powershell
curl.exe -X POST http://localhost:8000/api/notes/test.md -H "Content-Type: application/json" -d "{\"content\": \"# Hello World\"}"
```

### Delete Note
```http
DELETE /api/notes/{note_path}
```

**Example:**
```bash
curl -X DELETE http://localhost:8000/api/notes/test.md
```

### Move Note
```http
POST /api/notes/move
Content-Type: application/json

{
  "oldPath": "note.md",
  "newPath": "folder/note.md"
}
```

## 🖼️ Images

### Get Image
```http
GET /api/images/{image_path}
```
Retrieve an image file with authentication protection.

**Example:**
```bash
curl http://localhost:8000/api/images/folder/_attachments/image-20240417093343.png
```

**Security Note:** This endpoint requires authentication and validates that:
- The image path is within the notes directory (prevents directory traversal)
- The file exists and is a valid image format
- The requesting user is authenticated (if auth is enabled)

### Upload Image
```http
POST /api/upload-image
Content-Type: multipart/form-data

file: <image file>
note_path: <path of note to attach to>
```

Upload an image file to the `_attachments` directory. Images are automatically organized per-folder and named with timestamps to prevent conflicts.

**Supported formats:** JPG, JPEG, PNG, GIF, WEBP  
**Maximum size:** 10MB

**Response:**
```json
{
  "success": true,
  "path": "folder/_attachments/image-20240417093343.png",
  "filename": "image-20240417093343.png",
  "message": "Image uploaded successfully"
}
```

**Example (using curl):**
```bash
curl -X POST http://localhost:8000/api/upload-image \
  -F "file=@/path/to/image.png" \
  -F "note_path=folder/mynote.md"
```

**Windows PowerShell:**
```powershell
curl.exe -X POST http://localhost:8000/api/upload-image -F "file=@C:\path\to\image.png" -F "note_path=folder/mynote.md"
```

**Notes:**
- Images are stored in `_attachments` folders relative to the note's location
- Filenames are automatically timestamped (e.g., `image-20240417093343.png`)
- Images appear in the sidebar navigation and can be viewed/deleted directly
- Drag & drop images into the editor automatically uploads and inserts markdown
- All image access requires authentication when security is enabled

## 📁 Folders

### Create Folder
```http
POST /api/folders
Content-Type: application/json

{
  "path": "Projects/2025"
}
```

### Delete Folder
```http
DELETE /api/folders/{folder_path}
```
Deletes a folder and all its contents.

**Example:**
```bash
curl -X DELETE http://localhost:8000/api/folders/Projects/Archive
```

### Move Folder
```http
POST /api/folders/move
Content-Type: application/json

{
  "oldPath": "OldFolder",
  "newPath": "NewFolder"
}
```

### Rename Folder
```http
POST /api/folders/rename
Content-Type: application/json

{
  "oldPath": "Projects",
  "newName": "Work"
}
```

## 🔍 Search

### Search Notes
```http
GET /api/search?q={query}
```

**Example:**
```bash
curl "http://localhost:8000/api/search?q=hello"
```

## 🎨 Themes

### List Themes
```http
GET /api/themes
```

### Get Theme CSS
```http
GET /api/themes/{theme_id}
```

**Example:**
```bash
curl http://localhost:8000/api/themes/dark
```

## 🔌 Plugins

Plugins can hook into various events in the application lifecycle.

### Available Plugin Hooks

| Hook | Triggered When | Can Modify Data |
|------|----------------|-----------------|
| `on_note_create` | New note is created | ✅ Yes (return modified content) |
| `on_note_save` | Note is being saved | ✅ Yes (return transformed content, or None) |
| `on_note_load` | Note is loaded | ✅ Yes (return transformed content, or None) |
| `on_note_delete` | Note is deleted | ❌ No |
| `on_search` | Search is performed | ❌ No |
| `on_app_startup` | App starts | ❌ No |

See [PLUGINS.md](PLUGINS.md) for full documentation on creating plugins.

### List Plugins
```http
GET /api/plugins
```

### Toggle Plugin
```http
POST /api/plugins/{plugin_name}/toggle
Content-Type: application/json

{
  "enabled": true
}
```

**Linux/Mac:**
```bash
curl -X POST http://localhost:8000/api/plugins/note_stats/toggle \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

**Windows PowerShell:**
```powershell
curl.exe -X POST http://localhost:8000/api/plugins/note_stats/toggle -H "Content-Type: application/json" -d "{\"enabled\": true}"
```

### Calculate Note Stats
```http
GET /api/plugins/note_stats/calculate?content={markdown_content}
```

## 🔗 Graph

### Get Note Graph
```http
GET /api/graph
```
Returns the relationship graph between notes (internal links).

## ⚙️ System

### Get Config
```http
GET /api/config
```
Returns application configuration.

### Health Check
```http
GET /health
```
Returns system health status.

### API Info
```http
GET /api
```
Self-documenting endpoint listing all available API routes.

---

## 📝 Response Format

All endpoints return JSON responses:

**Success:**
```json
{
  "success": true,
  "data": { ... }
}
```

**Error:**
```json
{
  "detail": "Error message"
}
```
---

💡 **Tip:** Use the `/api` endpoint to get a live, self-documented list of all available endpoints!

