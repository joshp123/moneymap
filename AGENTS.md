# AGENTS.md

Written by AI on 2026.10.16 by model claude opus 5.5.

DNS for `moneymap.jjpcodes.com` lives in `~/code/opentofu-infra/websites/jjpcodes.com/moneymap-sites.tf`.

Source repository: https://github.com/joshp123/moneymap, MIT licence. The page footer links to it, to `docs/methodology.md` and to the deployed commit.

## Build and deploy

The Site is a public ChatGPT Site. `.openai/hosting.json` holds its project ID and the `TILES` R2 binding. The Worker and the tiles deploy separately.

1. Build the layers and run the checks in [README.md](README.md). Review the results, then commit.
2. Deploy the Worker with the Sites skill's source workflow (`site-workflow.mjs`). Pass the commands `[["bash", "deploy/build.sh"], ["node", "deploy/validate-artifact.mjs"]]`, then save and deploy the version. Keep the audience public. `deploy/build.sh` copies `worker/index.js` to `dist/server/index.js` and `.openai/hosting.json` to `dist/.openai/hosting.json`, and stamps the footer with the commit.
3. Set the Site's `UPLOAD_TOKEN` runtime secret to a new random value with the Sites tools. Then sync the tiles, first with `--dry-run` to see the counts:

   ```sh
   devenv shell -- node deploy/sync-tiles.mjs https://moneymap.jjpcodes.com --dry-run
   devenv shell -- node deploy/sync-tiles.mjs https://moneymap.jjpcodes.com
   ```

   Each run asks for one JSON line on hidden stdin: `{"uploadToken": "..."}`. Keep credentials out of arguments, files, logs and replies. The sync uploads new and changed tiles and deletes remote tiles that are no longer in `data/layers/`. Rerun it after any failure. Live numbers can be mixed while it runs.
4. Check the live Site: `devenv shell -- python -m checks.circles --origin https://moneymap.jjpcodes.com`.

Deploy the Worker before syncing whenever the `/__upload/` endpoints change; the sync needs the deployed Worker's tile list.
