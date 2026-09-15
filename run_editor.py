from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))
from ffmq_editor.app import main

if __name__ == "__main__":
    main()
