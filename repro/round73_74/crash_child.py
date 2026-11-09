from __future__ import annotations

import argparse
from pathlib import Path

from durable_store import TwoSlotStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument("payload")
    parser.add_argument("generation", type=int)
    parser.add_argument("failpoint")
    args = parser.parse_args()
    payload = Path(args.payload).read_bytes()
    TwoSlotStore(args.directory).commit(payload, args.generation, args.failpoint)


if __name__ == "__main__":
    main()
