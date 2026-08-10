# 🧩 Contributed Plugins

Plugins in this folder are **not loaded**. The loader only looks at `.py` files
sitting directly in `plugins/`, so everything here stays inert until you install
it yourself.

These come from the community rather than the core project. They are lightly
reviewed, maintained by whoever contributed them, and not covered by the
project's own testing. Read one before you run it.

## Installing one

Copy the file up one directory and restart:

```bash
cp plugins/contrib/<plugin>.py plugins/
docker-compose restart
```

On Docker, this assumes you've mounted the folder (uncomment `- ./plugins:/app/plugins`
in `docker-compose.yml`). Copying a file straight into a running container works
too, but it disappears the next time the container is recreated.

To remove a plugin, delete it from `plugins/` and restart. To leave it installed
but switch it off, toggle it in Settings → Plugins.

## Contributing one

The rules are in [CONTRIBUTING.md](../../CONTRIBUTING.md). In short: one
self-contained file, no new dependencies, no core changes, and a docstring at
the top of the file that tells someone what they're installing.

```python
"""
Plugin Name
One line on what it does.

Trigger: how a user sets it off (a search prefix, a hook, an endpoint)
Install: cp plugins/contrib/my_plugin.py plugins/
Author:  @your-github-handle
Caveats: anything known to be rough
"""
```

That docstring is the documentation, and this folder's file listing is the index.
Nothing shared needs editing when a plugin is added, so two people can contribute
in the same week without stepping on each other.

For the hooks themselves — what's available, plugin context, plugin-owned routes —
see [documentation/PLUGINS.md](../../documentation/PLUGINS.md).
