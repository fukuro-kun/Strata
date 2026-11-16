"""Fork-CI-Guard: jeder Job der importierten Upstream-Workflows muss
`github.repository == 'Niko1221/Strata'` als Bedingung tragen, damit auf dem
Forgejo/GitHub-Mirror (anderer Repositoryname) alle Jobs inert skippen.
Statisch geprueft: Job-Namen und exakte `if:`-Texte sind als Erwartung
hier fixiert (Snapshot der Erst-Uebernahme; Aenderungen an Bedingungen
fueren bewusst zum Test-Update)."""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
GUARD = "github.repository == 'Niko1221/Strata'"

# job name -> exact expected `if:` text (upstream condition preserved in parentheses)
EXPECTED = {
    "backends.yml": {
        "cuda": GUARD,
        "hip": GUARD,
        "sycl": GUARD,
        "metal": GUARD,
    },
    "check.yml": {
        "linux": GUARD,
        "windows": GUARD,
        "macos": GUARD,
    },
    "docker-images.yml": {
        "plan": GUARD,
        "image": GUARD,
    },
    "docs.yml": {
        "docs": GUARD,
    },
    "intake.yml": {
        "check": GUARD + " && (github.event_name == 'issues' || "
                         "github.event_name == 'pull_request_target')",
        "sweep": GUARD + " && (github.event_name == 'schedule' || "
                         "github.event_name == 'workflow_dispatch')",
    },
    "metal-build.yml": {
        "metal-link": GUARD,
    },
    "reopen.yml": {
        "reopen": GUARD + " && (startsWith(github.event.comment.body, '/reopen') && "
                          "github.event.comment.user.type != 'Bot')",
    },
    "scripts-test.yml": {
        "node-test": GUARD,
    },
    "snapshot.yml": {
        "snapshot": GUARD,
    },
    "terminal-minimal-server.yml": {
        "fake-engine": GUARD,
    },
    "terminal-portable-monitor.yml": {
        "client": GUARD,
    },
    "title-area.yml": {
        "title": GUARD,
    },
}


class ForkWorkflowGuard(unittest.TestCase):
    def test_all_expected_workflows_present(self):
        found = {p.name for p in WORKFLOWS.glob("*.yml")}
        self.assertEqual(set(EXPECTED), found)

    def test_every_job_guards_repository(self):
        for fname, jobs in EXPECTED.items():
            with self.subTest(workflow=fname):
                doc = yaml.load((WORKFLOWS / fname).read_text(encoding="utf-8"),
                                Loader=yaml.BaseLoader)
                got = doc["jobs"]
                self.assertEqual(set(jobs), set(got),
                                 f"{fname}: job set changed - review the guard on the new jobs")
                for name, want in jobs.items():
                    with self.subTest(workflow=fname, job=name):
                        self.assertEqual(want, got[name].get("if"),
                                         f"{fname}:{name} lost or changed its fork guard")

    def test_only_workflow_dispatch_triggers(self):
        # Fork decision: no automatic CI on our remotes - every workflow is
        # manual-only (upstream reference). Any new .yml/.yaml file lands here
        # untested and fails until reviewed.
        files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
        self.assertEqual(sorted(EXPECTED), [f.name for f in files],
                         "workflow file set changed - review the new/removed files")
        for f in files:
            with self.subTest(workflow=f.name):
                doc = yaml.load(f.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
                self.assertEqual({"workflow_dispatch"}, set(doc["on"] or {}),
                                 f"{f.name} has automatic triggers - fork policy is manual-only")

    def test_docker_dispatch_inputs_unchanged(self):
        # docker-images keeps its upstream manual inputs verbatim.
        doc = yaml.load((WORKFLOWS / "docker-images.yml").read_text(encoding="utf-8"),
                        Loader=yaml.BaseLoader)
        want = {
            "release_tag": {"description": "Release tag whose engine packages go into the "
                                          "images (for example v0.2.7)",
                            "required": "true", "type": "string"},
            "flavors": {"description": "Flavors to build, comma separated (empty: every "
                                       "flavor the release has a package for)",
                        "required": "false", "default": "", "type": "string"},
            "push": {"description": "Push the images to ghcr.io (off: build only, "
                                    "nothing is published)",
                     "required": "true", "default": "false", "type": "boolean"},
            "latest": {"description": "Also move the latest-<flavor> tags (turn off for "
                                      "a pre-release or a test)",
                       "required": "true", "default": "true", "type": "boolean"},
            "source_ref": {"description": "Git ref of the Dockerfile and the Terminal "
                                          "sources (empty: the release tag)",
                           "required": "false", "default": "", "type": "string"},
        }
        self.assertEqual(want, doc["on"]["workflow_dispatch"]["inputs"])

    def test_guard_names_upstream_not_fork(self):
        # The guard must name the upstream repository: on our mirror
        # (a different repository name) every job is inert.
        self.assertIn("Niko1221/Strata", GUARD)


if __name__ == "__main__":
    unittest.main()
