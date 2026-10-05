import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.scaffold_recipe import (
    RecipeSource,
    infer_build_settings,
    render_build_config,
    research_recipe,
    validate_name,
)


class ScaffoldRecipeTests(unittest.TestCase):
    def test_research_falls_back_to_conda_forge_staged_recipes(self):
        staged_source = RecipeSource(
            "https://example.test/staged", "build:\n  noarch: python"
        )

        class FakeGitHub:
            def get_recipe_file(self, owner, repo, path):
                if (owner, repo, path) == (
                    "conda-forge",
                    "staged-recipes",
                    "recipes/sample/meta.yaml",
                ):
                    return staged_source
                return None

        sources = research_recipe("sample", FakeGitHub())

        self.assertIs(sources["conda_forge"], staged_source)
        self.assertIsNone(sources["anaconda_recipes"])

    def test_validate_name_normalizes_and_rejects_path_traversal(self):
        self.assertEqual(validate_name("  My_Package "), "my_package")
        for name in ("../package", ".", "bad/name"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_name(name)

    def test_infers_noarch_and_gpu_from_upstream_recipe(self):
        sources = {
            "conda_forge": RecipeSource(
                "https://example.test/recipe", "build:\n  noarch: python\nrequirements:\n  run:\n    - cupy"
            ),
            "anaconda_recipes": None,
        }

        noarch, gpu, platforms = infer_build_settings(sources)

        self.assertTrue(noarch)
        self.assertTrue(gpu)
        self.assertEqual(platforms, ["linux-64"])

    def test_platform_recipe_honors_unconditional_platform_skip(self):
        sources = {
            "conda_forge": RecipeSource(
                "https://example.test/recipe", "build:\n  skip: true  # [win]"
            ),
            "anaconda_recipes": None,
        }

        noarch, gpu, platforms = infer_build_settings(sources)

        self.assertFalse(noarch)
        self.assertFalse(gpu)
        self.assertEqual(platforms, ["linux-64", "osx-arm64"])

    def test_renders_sources_and_platforms_as_yaml(self):
        sources = {
            "conda_forge": RecipeSource(
                "https://example.test/recipe", "package:\n  name: sample"
            ),
            "anaconda_recipes": None,
        }

        config = render_build_config(
            "sample", sources, noarch=False, gpu=False, platforms=["linux-64"]
        )

        self.assertIn('recipe: "sample"', config)
        self.assertIn('conda_forge: "https://example.test/recipe"', config)
        self.assertIn("anaconda_recipes: null", config)
        self.assertIn('  - "linux-64"', config)

    @unittest.skipUnless(shutil.which("ruby"), "Ruby is required to test build matrix discovery")
    def test_build_matrix_uses_platforms_from_build_config(self):
        script = Path(__file__).parents[1] / "scripts" / "build_matrix.rb"
        with tempfile.TemporaryDirectory() as temp_dir:
            recipe_dir = Path(temp_dir) / "sample"
            recipe_dir.mkdir()
            (recipe_dir / "build.yaml").write_text(
                'recipe: "sample"\nplatforms:\n  - "osx-arm64"\n'
                'channels:\n  - "conda-forge"\n',
                encoding="utf-8",
            )
            (recipe_dir / "meta.yaml").write_text("package:\n  name: sample\n", encoding="utf-8")
            output_path = Path(temp_dir) / "github-output"
            environment = os.environ | {
                "EVENT_NAME": "workflow_dispatch",
                "RECIPE_INPUT": "sample",
                "GITHUB_OUTPUT": str(output_path),
            }

            result = subprocess.run(
                ["ruby", str(script)],
                cwd=temp_dir,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            matrix_line = output_path.read_text(encoding="utf-8").strip().removeprefix("matrix=")
            matrix = json.loads(matrix_line)
            self.assertEqual(
                matrix["include"],
                [
                    {
                        "recipe": "sample",
                        "platform": "osx-arm64",
                        "runner": "macos-latest",
                        "channels": ["conda-forge"],
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
