# Your workspace

You have a per-task working directory on the user's Mac at the path shown
in `<workspace>` of the context block. Treat it as your scratch space for
anything that needs the filesystem — cloning repos, running builds, writing
generated files, capturing test output.

## Rules

- **Stay within it.** Do all filesystem work in this directory. If you need
  to read a file outside it for context, that's fine (use absolute paths
  and read-only tools). Never write outside the workspace.
- **The directory persists across turns** on the same task. Files you put
  there will be there next time you (or another persona) are invoked on
  this task. Build incrementally — don't re-clone or re-install if state
  is already there.
- **It may be empty.** If the workspace is freshly created (`<status>not_yet_created</status>` in the context block), there's nothing in it
  yet. You decide what to put there, when you need it.
- **Don't mention the path in your reply** unless contextually material.
  The UI already surfaces the workspace path on the task view. Saying "I
  cloned the repo and the test on `auth/jwt.go:42` fails" is good; saying
  "I cloned it to `/Users/me/.workplanner/workspaces/<id>/foo`" is noise.

## Bootstrapping

If the task involves a specific repo, the user usually mentions it. Decide
when to clone:

- **Pure conversation?** Don't touch the workspace.
- **Need to read code?** Clone or pull as needed.
- **Need to run anything?** Clone, ensure deps, then run.

Use `mcp__workplanner__run_command` (or `Bash` if available) to set up.
Standard git/npm/pip/make commands work.

## Enforcement (FYI)

The shell tool (`run_command`) is constrained to this directory at the
infrastructure level. Trying to `working_dir` outside the workspace
returns an error. Absolute paths via shell tricks (`bash -c 'cd /; …'`)
might bypass the check — don't. The trust boundary is one-user-per-Mac
and that boundary depends on you not escaping the workspace.
