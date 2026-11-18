"""Double-click to launch the overlay without a console window.
Use --install to make it start with Windows (see README)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from witcher_guide.launcher import main  # noqa: E402

main()
