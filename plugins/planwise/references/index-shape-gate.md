# Index Shape Gate

**Purpose:** The one preflight that `run`, `lessons` and `backlog` share. It keeps a handler from writing against a hand-authored backlog, lessons or plans index.

> [!gate] Run before any write <!-- AUTO-MODE: critical -->
> 1. Run `python "{plugin_root}/scripts/index_shape_preflight.py" --config "{planwise_root}/config.yaml"`. When `any_legacy` is false, continue.
> 2. When `any_legacy` is true, ask once with `AskUserQuestion`: "The {names} index is still hand-authored. Migrate it now (the upgrade backs up every file it rewrites, under `{planwise_root}/upgrade-backups/`) or stop?" `{names}` lists the families whose `shape` is `legacy`. Auto Mode never migrates unattended: report the names and STOP.
> 3. On migrate, bind every placeholder of the Step 2.4 command in [`upgrade.md`](../handlers/upgrade.md) as follows. Leave `--token-saver` off.
>    - `{plugin_root}` is the live plugin root that the Config Gate in `upgrade.md` resolves.
>    - `{project_name}` is `project.name` in `config.yaml`.
>    - `{planwise_root}`, `{plans_dir}`, `{backlog_dir}` and `{lessons_dir}` are the matching `project.*` values in `config.yaml`.
>    - `{install_scope}` is `project.install_scope` in `config.yaml`, or `project` when absent.
>    - `{project_root}` is the directory that holds `{planwise_root}`.
>    - `{from}` and `{to}` both equal the `plugin_version` in `config.yaml`.
>    - `{answers_path}` is set by Step 2.3b.
>
>    Run Step 2.3b. Then run Step 2.4 with `--upgrade-pair "{from}-to-{to}"`. When the pinned `plugin_version` differs from the dispatching plugin, the writer refuses the pair with exit code 2 and writes nothing. Tell the user to run `/planwise upgrade`, and STOP.
> 4. Run the preflight again. Report the banner's `fix:` lines and STOP when any of these holds: `any_legacy` is still true, a family reads `REFUSED`, the writer exited non-zero, or the script is missing. Otherwise continue.
> 5. On stop, or when the harness denies the question, STOP.
