from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))
from ffmq_editor.app import main

if __name__ == "__main__":
    if len(sys.argv)==4 and sys.argv[1]=='--self-test':
        from ffmq_editor.build_smoke import run
        raise SystemExit(run(sys.argv[2],sys.argv[3]))
    main()
