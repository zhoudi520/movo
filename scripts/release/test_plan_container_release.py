#!/usr/bin/env python3

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from plan_container_release import IMAGES, build_plan, select_images


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ContainerReleasePlanTests(unittest.TestCase):
    def suffixes(self, images):
        return [image.suffix for image in images]

    def test_documentation_change_reuses_every_image(self):
        changed, unchanged = select_images(["README.md"])
        self.assertEqual([], changed)
        self.assertEqual(len(IMAGES), len(unchanged))

    def test_frontend_change_only_rebuilds_its_image(self):
        changed, _ = select_images(["apps/user-web/src/views/LoginView.vue"])
        self.assertEqual(["user-web"], self.suffixes(changed))

    def test_dsh_host_change_does_not_rebuild_chat_api(self):
        changed, _ = select_images(["services/chat-api/dsh/runtime-host/src/host.mjs"])
        self.assertEqual(["dsh-runtime-host"], self.suffixes(changed))

    def test_gateway_image_change_only_rebuilds_gateway(self):
        changed, _ = select_images(["deploy/docker/gateway.Dockerfile"])
        self.assertEqual(["gateway"], self.suffixes(changed))

    def test_chat_runtime_change_rebuilds_chat_api(self):
        changed, _ = select_images(["services/chat-api/app/runtime/runner.py"])
        self.assertEqual(["chat-api"], self.suffixes(changed))

    def test_release_workflow_change_reuses_every_image(self):
        changed, unchanged = select_images([".github/workflows/container-release.yml"])
        self.assertEqual([], changed)
        self.assertEqual(len(IMAGES), len(unchanged))

    def test_release_planner_change_reuses_every_image(self):
        changed, unchanged = select_images(["scripts/release/plan_container_release.py"])
        self.assertEqual([], changed)
        self.assertEqual(len(IMAGES), len(unchanged))

    def test_force_all_rebuilds_every_image(self):
        changed, unchanged = select_images([], force_all=True)
        self.assertEqual(len(IMAGES), len(changed))
        self.assertEqual([], unchanged)

    def test_plan_exposes_complete_image_inventory_for_promotion(self):
        plan = build_plan(None, "HEAD")
        self.assertEqual(len(IMAGES), len(plan["images"]))
        self.assertEqual(len(IMAGES), len(plan["changed"]))

    def test_private_repository_skips_unsupported_github_attestation(self):
        workflow = (REPOSITORY_ROOT / ".github/workflows/container-release.yml").read_text()
        self.assertIn(
            "if: ${{ github.event.repository.visibility == 'public' }}\n"
            "        uses: ./.github/actions/attest-image-with-retry",
            workflow,
        )

    def test_attestation_retries_without_weakening_the_scan_gate(self):
        workflow = (REPOSITORY_ROOT / ".github/workflows/container-release.yml").read_text()
        action = (
            REPOSITORY_ROOT / ".github/actions/attest-image-with-retry/action.yml"
        ).read_text()
        self.assertLess(
            workflow.index("- name: Scan candidate image"),
            workflow.index("- name: Attest public image provenance"),
        )
        self.assertEqual(3, action.count("uses: actions/attest-build-provenance@v3"))
        self.assertEqual(2, action.count("continue-on-error: true"))
        self.assertIn("steps.first.outcome == 'failure'", action)
        self.assertIn("steps.second.outcome == 'failure'", action)
        self.assertIn("- name: Attest image (attempt 3/3)", action)
        self.assertEqual(3, action.count("push-to-registry: true"))

    def test_release_scans_candidates_before_publishing_public_tags(self):
        workflow = (REPOSITORY_ROOT / ".github/workflows/container-release.yml").read_text()
        candidate = "type=raw,value=candidate-${{ github.sha }}"
        scan = "- name: Scan candidate image"
        promote = "run: bash scripts/release/promote_container_release.sh"
        self.assertIn(candidate, workflow)
        self.assertIn(scan, workflow)
        self.assertIn(promote, workflow)
        self.assertLess(workflow.index(candidate), workflow.index(scan))
        self.assertLess(workflow.index(scan), workflow.index(promote))
        self.assertNotIn("type=ref,event=tag", workflow)
        self.assertNotIn("type=raw,value=latest", workflow)
        self.assertIn("needs.publish-candidates.result == 'success'", workflow)
        self.assertIn("group: container-release-${{ github.repository }}", workflow)
        self.assertIn(
            "MOVO_SECURITY_REFRESH=${{ github.run_id }}-${{ github.run_attempt }}",
            workflow,
        )

    def test_document_parser_exceptions_are_scoped_and_expire(self):
        workflow = (REPOSITORY_ROOT / ".github/workflows/container-release.yml").read_text()
        ignore = (
            REPOSITORY_ROOT / ".github/security/document-parser.trivyignore.yaml"
        ).read_text()
        self.assertIn("if: matrix.suffix == 'document-parser'", workflow)
        self.assertIn("- name: Scan candidate image (release gate)", workflow)
        self.assertIn("exit-code: \"1\"", workflow)
        self.assertEqual(1, workflow.count("trivyignores:"))
        self.assertIn(
            "trivyignores: ${{ matrix.suffix == 'document-parser' && "
            "'.github/security/document-parser.trivyignore.yaml' || '' }}",
            workflow,
        )
        self.assertEqual(
            {"CVE-2026-105744", "CVE-2026-96748", "CVE-2026-96749"},
            set(re.findall(r"^  - id: (CVE-\d+-\d+)$", ignore, re.MULTILINE)),
        )
        self.assertEqual(3, ignore.count("expired_at: 2026-11-14"))
        self.assertIn("pkg:pypi/docling@2.94.0", ignore)
        self.assertIn("pkg:pypi/docling-slim@2.94.0", ignore)
        self.assertIn("pkg:pypi/pymongo@3.13.0", ignore)

    def test_release_diff_uses_last_successful_container_release(self):
        workflow = (REPOSITORY_ROOT / ".github/workflows/container-release.yml").read_text()
        self.assertIn("actions: read", workflow)
        self.assertIn("--workflow container-release.yml", workflow)
        self.assertIn("--status success", workflow)
        self.assertNotIn("git describe --tags", workflow)

    def test_debian_runtime_images_install_security_updates(self):
        dockerfiles = (
            "services/admin-api/Dockerfile",
            "services/chat-api/Dockerfile",
            "services/chat-api/dsh/runtime-host/Dockerfile",
            "services/document-parser/Dockerfile",
        )
        for dockerfile in dockerfiles:
            with self.subTest(dockerfile=dockerfile):
                contents = (REPOSITORY_ROOT / dockerfile).read_text()
                self.assertIn("ARG MOVO_SECURITY_REFRESH=local", contents)
                self.assertIn("apt-get upgrade -y", contents)

    def test_promotion_preflights_all_sources_before_tagging(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            call_log = temporary_path / "docker-calls.log"
            docker = temporary_path / "docker"
            docker.write_text(
                '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$DOCKER_CALL_LOG"\n'
            )
            docker.chmod(0o755)
            env = os.environ | {
                "ALL_IMAGES_JSON": json.dumps(
                    [{"suffix": "chat-api"}, {"suffix": "admin-api"}]
                ),
                "CHANGED_IMAGES_JSON": json.dumps([{"suffix": "chat-api"}]),
                "BASE_REF": "v0.1.12",
                "DOCKER_CALL_LOG": str(call_log),
                "GITHUB_REF_NAME": "v0.1.13",
                "GITHUB_REPOSITORY": "HiMOVO/MOVO",
                "GITHUB_SHA": "0123456789abcdef0123456789abcdef01234567",
                "PATH": f"{temporary_path}:{os.environ['PATH']}",
            }

            subprocess.run(
                ["bash", str(REPOSITORY_ROOT / "scripts/release/promote_container_release.sh")],
                check=True,
                env=env,
                stdout=subprocess.PIPE,
                text=True,
            )
            calls = call_log.read_text().splitlines()

        self.assertEqual(4, len(calls))
        self.assertTrue(all("imagetools inspect" in call for call in calls[:2]))
        self.assertTrue(all("imagetools create" in call for call in calls[2:]))
        self.assertIn("movo-chat-api:candidate-0123456789abcdef", calls[0])
        self.assertIn("movo-admin-api:v0.1.12", calls[1])
        self.assertTrue(all(":v0.1.13" in call for call in calls[2:]))
        self.assertTrue(all(":latest" in call for call in calls[2:]))


if __name__ == "__main__":
    unittest.main()
