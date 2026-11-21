"""Fork-CI-Guard (Betriebsregel 2026-11-21): der Fork fuehrt KEINE CI aus.

Saemtliche `.github/workflows/*.yml|*.yaml` sind entfernt — kein Job darf
auf Forgejo, Mirror oder fremden Runnern automatisch starten (Nutzerwill:
nichts wird von einem System ausgefuehrt; Builds/Tests/Installationen
laufen manuell oder durch Agents).

Upstream bringt die Dateien bei jedem Merge erneut mit — der Sync-Schritt
loescht sie danach wieder (modify/delete-Konflikt -> delete). Dieser Test
haertet fail-closed: JEDE gefundene Workflow-Datei ist ein Verstoss, denn
upstream-Dateien kommen unguarded mit Push-/PR-/Cron-Triggern."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class ForkNoWorkflows(unittest.TestCase):
    def test_no_workflow_files(self):
        found = []
        if WORKFLOWS.is_dir():
            found = sorted(
                p.relative_to(ROOT).as_posix()
                for pat in ("*.yml", "*.yaml")
                for p in WORKFLOWS.glob(pat)
            )
        self.assertEqual(
            [], found,
            "Upstream-CI im Fork entfernen: `git rm` auf diese Dateien "
            "(Betriebsregel: keine automatischen Ablaeufe). Bei Merge-"
            "Konflikt modify/delete -> delete waehlen.",
        )


if __name__ == "__main__":
    unittest.main()
