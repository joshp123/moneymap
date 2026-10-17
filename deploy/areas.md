Written by AI on 2026.10.17 by model gpt-6.1-sol; release steps by model claude opus 5.5.

# Publish named areas

The builder writes `data/areas/`. The Worker serves these files from the same
R2 bucket as the tiles, under `areas/` keys. The page requests `/areas/...` on
its own origin. The files are not part of the Worker artifact or Git history.

After building and checking the data, deploy the updated Worker using the
existing workflow in [AGENTS.md](../AGENTS.md). Then preview the upload plan
and sync only the area files:

```sh
devenv shell -- node deploy/sync-tiles.mjs https://moneymap.jjpcodes.com areas --dry-run
devenv shell -- node deploy/sync-tiles.mjs https://moneymap.jjpcodes.com areas
```

Both commands read the upload credentials from hidden stdin. The default sync,
with no dataset names, now includes areas alongside layers and place names.
Deploy the updated Worker before the first area sync.

For an open, downloadable copy, publish each data build as a GitHub release
named after its build date. This is separate from serving the page; it does not
replace the R2 sync.

```sh
release_tag="areas-$(date +%Y-%m-%d)"
mkdir -p data/build/areas-release
tar -czf data/build/areas-release/moneymap-areas.tar.gz -C data areas
gh release create "$release_tag" data/build/areas-release/moneymap-areas.tar.gz --repo joshp123/moneymap \
  --target main --title "Named areas, $(date +%-d\ %B\ %Y)" --notes "Outlines and totals for the pick-an-area mode."
```

The archive includes the source and licence notices.
