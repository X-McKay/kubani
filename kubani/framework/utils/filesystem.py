"""File system utilities.

Provides a concrete DefaultFileSystem implementation that can be used
across workflows. For testing, use the FileSystem protocol with mocks.
"""

import shutil
from pathlib import Path


class DefaultFileSystem:
    """Default filesystem implementation using standard library.

    Provides a concrete implementation of the FileSystem protocol
    for use in production code. For testing, inject a mock instead.

    Example:
        from kubani.framework.utils import DefaultFileSystem

        fs = DefaultFileSystem()
        content = fs.read("path/to/file.txt")
        fs.write("path/to/output.txt", "content")
    """

    def read(self, path: str) -> str:
        """Read file content as string."""
        return Path(path).read_text()

    def write(self, path: str, content: str) -> None:
        """Write content to file, creating parent directories if needed."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        return Path(path).exists()

    def mkdir(self, path: str) -> None:
        """Create directory and parents."""
        Path(path).mkdir(parents=True, exist_ok=True)

    def list_files(self, path: str, pattern: str = "*") -> list[str]:
        """List files matching glob pattern in path."""
        p = Path(path)
        if not p.exists():
            return []
        return [str(f) for f in p.glob(pattern)]

    def copy(self, src: str, dst: str) -> None:
        """Copy file from src to dst."""
        shutil.copy2(src, dst)

    def move(self, src: str, dst: str) -> None:
        """Move file or directory from src to dst."""
        shutil.move(src, dst)

    def list_dir(self, path: str) -> list[str]:
        """List directory contents (names only, not full paths)."""
        p = Path(path)
        if not p.exists():
            return []
        return [f.name for f in p.iterdir()]

    def delete(self, path: str) -> None:
        """Delete file or directory."""
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()


__all__ = ["DefaultFileSystem"]
