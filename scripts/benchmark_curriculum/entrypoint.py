"""File entry point for isolated workers whose cwd is outside the repository."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.benchmark_curriculum.cli import main

if __name__ == "__main__":
    main()
