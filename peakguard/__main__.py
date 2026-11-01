"""CLI offline: python3 -m peakguard list|run|compare."""

import argparse
import json
from dataclasses import fields
from pathlib import Path

from .scenarios import SCENARIOS, load_scenario
from .simulator import POLICIES, Config, compare, simulate


def main() -> None:
    parser = argparse.ArgumentParser(description="PeakGuard AI: simulação sintética offline, custos em BRL.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Lista os quatro cenários sintéticos.")
    for command in ("run", "compare"):
        sub = commands.add_parser(command, help="Executa uma política." if command == "run" else "Compara as duas políticas.")
        sub.add_argument("scenario", choices=SCENARIOS)
        sub.add_argument("--seed", type=int, default=42)
        sub.add_argument("--output", type=Path, help="Grava o mesmo JSON emitido em stdout; o diretório deve existir.")
        if command == "run":
            sub.add_argument("--policy", choices=POLICIES, default="reactive")
        for field in fields(Config):
            sub.add_argument("--" + field.name.replace("_", "-"), type=field.type, default=field.default,
                             help=f"{field.name}; padrão: {field.default}")
    args = parser.parse_args()
    try:
        if args.command == "list":
            result = SCENARIOS
        else:
            config = Config(**{field.name: getattr(args, field.name) for field in fields(Config)})
            scenario = load_scenario(args.scenario, args.seed)
            result = simulate(scenario, args.policy, config) if args.command == "run" else compare(scenario, config)
        serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if getattr(args, "output", None):
            args.output.write_text(serialized, encoding="utf-8")
        print(serialized, end="")
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
