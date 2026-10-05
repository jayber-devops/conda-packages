#!/usr/bin/env python3
"""Research upstream conda recipes and write a starter build configuration."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


PLATFORM_SELECTORS = {
    "linux-64": "linux",
    "win-64": "win",
    "osx-arm64": "osx",
}
RECIPE_PATHS = ("recipe/meta.yaml", "recipe/recipe.yaml")
GPU_PATTERN = re.compile(
    r"\b(?:cuda|cudatoolkit|pytorch-cuda|rocm|cupy|gpu|nvidia)\b", re.IGNORECASE
)


@dataclass(frozen=True)
class RecipeSource:
    url: str
    content: str


class GitHub:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def get_recipe_file(self, owner: str, repo: str, path: str) -> RecipeSource | None:
        api_url = (
            f"https://api.github.com/repos/{owner}/{repo}/contents/"
            f"{urllib.parse.quote(path, safe='/')}"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "conda-packages-recipe-scaffolder",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise RuntimeError(f"GitHub API request failed ({error.code}): {api_url}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Unable to reach GitHub API: {error.reason}") from error

        if result.get("type") != "file" or "content" not in result:
            return None
        content = base64.b64decode(result["content"]).decode("utf-8")
        return RecipeSource(url=result["html_url"], content=content)


def validate_name(name: str) -> str:
    normalized = name.strip().lower()
    if (
        normalized in {".", ".."}
        or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", normalized)
    ):
        raise ValueError("Recipe names must contain only letters, digits, '.', '_' or '-'.")
    return normalized


def research_recipe(name: str, github: GitHub) -> dict[str, RecipeSource | None]:
    slug = name.replace("_", "-")
    sources: dict[str, RecipeSource | None] = {
        "conda_forge": None,
        "anaconda_recipes": None,
    }
    for key, owner in (
        ("conda_forge", "conda-forge"),
        ("anaconda_recipes", "AnacondaRecipes"),
    ):
        repo = f"{slug}-feedstock"
        for path in RECIPE_PATHS:
            source = github.get_recipe_file(owner, repo, path)
            if source:
                sources[key] = source
                break

    if sources["anaconda_recipes"] is None:
        for path in (f"{name}/meta.yaml", f"{name}/recipe/meta.yaml"):
            source = github.get_recipe_file("ContinuumIO", "anaconda-recipes", path)
            if source:
                sources["anaconda_recipes"] = source
                break
    return sources


def infer_build_settings(
    sources: dict[str, RecipeSource | None],
) -> tuple[bool, bool, list[str]]:
    contents = [source.content for source in sources.values() if source]
    combined = "\n".join(contents)
    noarch = bool(
        re.search(r"^\s*noarch\s*:\s*(?:python|generic)\b", combined, re.MULTILINE)
    )
    gpu = bool(GPU_PATTERN.search(combined))

    platforms = list(PLATFORM_SELECTORS)
    if not noarch:
        for line in combined.splitlines():
            match = re.search(r"\bskip\s*:\s*true\b.*?#\s*\[([^\]]+)\]", line)
            if not match:
                continue
            selector = match.group(1).lower()
            for platform, selector_name in PLATFORM_SELECTORS.items():
                if re.search(rf"\b{selector_name}\b", selector) and not re.search(
                    rf"\bnot\s+{selector_name}\b", selector
                ):
                    if platform in platforms:
                        platforms.remove(platform)
    if noarch:
        platforms = ["linux-64"]
    return noarch, gpu, platforms


def yaml_scalar(value: str) -> str:
    return json.dumps(value)


def render_build_config(
    name: str,
    sources: dict[str, RecipeSource | None],
    noarch: bool,
    gpu: bool,
    platforms: list[str],
) -> str:
    lines = [
        "# Generated from upstream recipes; review the suggestions before building.",
        f"recipe: {yaml_scalar(name)}",
        "upstream:",
    ]
    for key, source in sources.items():
        lines.append(f"  {key}: {yaml_scalar(source.url) if source else 'null'}")
    lines.extend(
        [
            f"noarch: {'true' if noarch else 'false'}",
            f"gpu: {'true' if gpu else 'false'}",
            "platforms:",
        ]
    )
    lines.extend(f"  - {yaml_scalar(platform)}" for platform in platforms)
    lines.extend(
        [
            "channels:",
            '  - "conda-forge"',
            "",
        ]
    )
    return "\n".join(lines)


def scaffold(name: str, output_dir: Path, github: GitHub) -> Path:
    name = validate_name(name)
    sources = research_recipe(name, github)
    noarch, gpu, platforms = infer_build_settings(sources)
    destination = output_dir / name / "build.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_build_config(name, sources, noarch, gpu, platforms), encoding="utf-8"
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", help="Conda recipe name")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("."), help="Directory for the scaffold"
    )
    args = parser.parse_args()

    try:
        output = scaffold(args.recipe, args.output_dir, GitHub(os.environ.get("GITHUB_TOKEN")))
    except (RuntimeError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Generated {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
