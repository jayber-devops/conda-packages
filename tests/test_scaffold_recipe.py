import unittest

from scripts.scaffold_recipe import (
    RecipeSource,
    infer_build_settings,
    render_build_config,
    validate_name,
)


class ScaffoldRecipeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
