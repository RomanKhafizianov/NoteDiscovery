# 📝 NoteDiscovery

> Your Self-Hosted Knowledge Base

## What is NoteDiscovery?

NoteDiscovery is a **lightweight, self-hosted note-taking application** that puts you in complete control of your knowledge base. Write, organize, and discover your notes with a beautiful, modern interface—all running on your own server.

![Note Discovery](screenshot.jpg)

## 🎯 Who is it for?

- **Privacy-conscious users** who want complete control over their data
- **Developers** who prefer markdown and local file storage
- **Knowledge workers** building a personal wiki or second brain
- **Teams** looking for a self-hosted alternative to commercial apps
- **Anyone** who values simplicity, speed, and ownership

## ✨ Why NoteDiscovery?

### vs. Commercial Apps (Notion, Evernote, Obsidian Sync)

| Feature | NoteDiscovery | Commercial Apps |
|---------|---------------|-----------------|
| **Cost** | 100% Free | $xxx/month/year |
| **Privacy** | Your server, your data | Their servers, their terms |
| **Speed** | Lightning fast | Depends on internet |
| **Offline** | Always works | Limited or requires sync |
| **Customization** | Full control | Limited options |
| **No Lock-in** | Plain markdown files | Proprietary formats |

### Key Benefits

- 🔒 **Total Privacy** - Your notes never leave your server
- 💰 **Zero Cost** - No subscriptions, no hidden fees
- 🚀 **Fast & Lightweight** - Instant search and navigation
- 🎨 **Beautiful Themes** - Multiple themes, easy to customize
- 🔌 **Extensible** - Plugin system for custom features
- 📱 **Responsive** - Works on desktop, tablet, and mobile
- 📂 **Simple Storage** - Plain markdown files in folders

## 🚀 Quick Start

### Running with Docker (Recommended)

Docker ensures consistent environment and easy deployment:

```bash
# Clone the repository
git clone https://github.com/gamosoft/notediscovery.git
cd notediscovery

# Start with Docker Compose
docker-compose up -d

# Access at http://localhost:8000

# View logs
docker-compose logs -f

# Stop the application
docker-compose down
```

**Requirements:**
- Docker
- Docker Compose

### Running Locally (Without Docker)

For development or if you prefer running directly:

```bash
# Clone the repository
git clone https://github.com/gamosoft/notediscovery.git
cd notediscovery

# Install dependencies
pip install -r requirements.txt

# Run the application
python run.py

# Access at http://localhost:8000
```

**Requirements:**
- Python 3.8 or higher
- pip (Python package manager)

**Dependencies installed:**
- FastAPI - Web framework
- Uvicorn - ASGI server
- PyYAML - Configuration handling
- aiofiles - Async file operations

## 📚 Documentation

Want to learn more? **The full documentation lives inside the app as interactive notes!**

Once you've started NoteDiscovery, you'll find comprehensive guides on:
- 🎨 **THEMES.md** - Theme customization and creating custom themes
- ✨ **FEATURES.md** - Complete feature list and keyboard shortcuts
- 🔌 **PLUGINS.md** - Plugin system and available plugins
- 🌐 **API.md** - REST API documentation and examples

**Can't wait to start the app?** Browse the documentation notes directly on GitHub in the [`data/notes/`](data/notes/) folder!

💡 **Tip:** These documentation files are regular markdown notes—edit them, add your own notes, or use them as templates. It's your knowledge base!

## 🔒 Security Considerations

NoteDiscovery is designed for **self-hosted, private use**. Please keep these security considerations in mind:

### Network Security
- ⚠️ **Do NOT expose directly to the internet** without additional security measures
- Run behind a reverse proxy (nginx, Caddy) with HTTPS and authentication if needed
- Keep it on your local network or use a VPN for remote access
- By default, the app listens on `0.0.0.0:8000` (all network interfaces)

### No Built-in Authentication
- The app has **no authentication by design** (single-user, self-hosted)
- Anyone with network access can read and modify your notes
- Use network-level security (firewall, VPN) for access control
- Consider adding authentication via reverse proxy if needed

### Data Privacy
- Your notes are stored as **plain text markdown files** in `data/notes/`
- No data is sent to external services
- Regular backups are recommended

### Best Practices
- Run on `localhost` or a private network only
- Use Docker for isolation and easier security management
- Keep your system and dependencies updated
- Review and audit any plugins you install
- Set appropriate file permissions on the `data/` directory

**TL;DR**: Perfect for personal use on your local machine or home network. Add a reverse proxy with authentication if exposing to wider networks.

## 💖 Support Development

If NoteDiscovery makes your life easier, consider buying me a coffee! Your support helps keep this project alive and growing.

**[☕ Buy Me a Coffee](https://paypal.me/gamosoft)**

Every contribution, no matter how small, is deeply appreciated and helps fund:
- 🛠️ New features and improvements
- 🐛 Bug fixes and maintenance
- 📚 Documentation and tutorials
- 🎨 Design enhancements

## 📄 License

MIT License - Free to use, modify, and distribute.

---

Made with ❤️ for the self-hosting community
