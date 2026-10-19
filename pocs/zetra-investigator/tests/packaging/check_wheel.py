"""Verify built wheel resources against their canonical source bytes."""

import argparse
import tomllib
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile


def check(wheel: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "src"
    resources = (
        Path("kubani_investigator/agents/investigator/agent.yaml"),
        Path("kubani_investigator/agents/investigator/instructions/base.md"),
    )
    project = tomllib.loads((source.parent / "pyproject.toml").read_text(encoding="utf-8"))
    expected = project["project"]["dependencies"]
    with ZipFile(wheel) as archive:
        for resource in resources:
            try:
                actual = archive.read(resource.as_posix())
            except KeyError as exc:
                raise ValueError(f"wheel is missing {resource}") from exc
            if actual != (source / resource).read_bytes():
                raise ValueError(f"wheel resource differs from source: {resource}")
        metadata_paths = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise ValueError("wheel must contain exactly one METADATA file")
        metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
        actual_requirements = metadata.get_all("Requires-Dist", [])
        normalize = lambda value: "".join(value.lower().split())
        if sorted(map(normalize, actual_requirements)) != sorted(map(normalize, expected)):
            raise ValueError("wheel dependency metadata differs from project dependencies")
    print(f"Verified packaged agent manifest and instructions: {wheel.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels", type=Path, nargs="+")
    args = parser.parse_args()
    for wheel in args.wheels:
        check(wheel)


if __name__ == "__main__":
    main()
