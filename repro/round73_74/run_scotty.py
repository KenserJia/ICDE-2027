"""Build the frozen Scotty source and run the registered-window adapter."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parent


def run(command: list[str], cwd: Path, log: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    if log is None:
        subprocess.run(command, cwd=cwd, check=True)
    else:
        with log.open("w", encoding="utf-8") as handle:
            subprocess.run(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT, check=True)


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("--profile",choices=("smoke","full"),default="smoke")
    args=parser.parse_args()
    for executable in ("java","javac","mvn"):
        if shutil.which(executable) is None:
            raise SystemExit(f"{executable} is required for the Scotty reproduction")
    archive=ROOT/"scotty-master.zip"
    if not archive.exists():
        raise SystemExit("missing frozen Scotty source archive; see THIRD_PARTY_NOTICES.md")
    work=ROOT/"scotty-work"
    if work.exists():
        raise SystemExit(f"refusing to overwrite {work}")
    with zipfile.ZipFile(archive) as package:
        package.extractall(work)
    source=next(path for path in work.iterdir() if path.is_dir())
    results=ROOT/"results";results.mkdir(exist_ok=True)
    run(["mvn","-pl","core,state,slicing","-am","test"],source,results/"scotty_tests.log")
    run(["mvn","-pl","core,state,slicing","-am","package","-DskipTests"],source,results/"scotty_build.log")
    classpath=os.pathsep.join(str(path) for path in (
        source/"core/target/classes",source/"state/target/classes",source/"slicing/target/classes"))
    adapter=ROOT/"scotty_adapter/ScottyAdapter.java"
    run(["javac","-cp",classpath,"-d",str(results),str(adapter)],ROOT)
    events,repeats,warmups=(100000,1,0) if args.profile=="smoke" else (1000000,5,2)
    command=["java","-cp",f"{results}{os.pathsep}{classpath}","ScottyAdapter",str(events),str(repeats),"all","all",str(warmups)]
    output=subprocess.run(command,cwd=ROOT,check=True,capture_output=True,text=True).stdout
    (results/"scotty.jsonl").write_text(output)
    rows=[json.loads(line) for line in output.splitlines() if line.strip()]
    print(json.dumps({"rows":len(rows),"wrong":sum(row["wrong"] for row in rows),"events":events},indent=2))


if __name__ == "__main__":
    main()
