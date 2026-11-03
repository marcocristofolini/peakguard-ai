"""CLI offline: python3 -m peakguard list|run|compare."""

import argparse
import json
from dataclasses import fields
from pathlib import Path

from .analysis import multi_seed, to_csv
from .scenarios import ALL_SCENARIOS, ARRIVALS, load_scenario
from .simulator import POLICIES, Config, compare, simulate


def main() -> None:
    parser = argparse.ArgumentParser(description="PeakGuard AI: simulação sintética offline, custos em BRL.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Lista os cenários sintéticos.")
    helps = {"run": "Executa uma política.", "compare": "Compara as duas políticas.",
             "multiseed": "Média e IC 95%% das métricas em várias seeds."}  # %% : argparse formata help com %
    for command, text in helps.items():
        sub = commands.add_parser(command, help=text)
        sub.add_argument("scenario", choices=ALL_SCENARIOS)
        sub.add_argument("--arrivals", choices=ARRIVALS, default="deterministic")
        if command == "multiseed":
            sub.add_argument("--seeds", type=int, default=20, help="número de seeds (0..n-1); padrão: 20")
            sub.add_argument("--csv", type=Path, help="Grava também a tabela em CSV.")
        else:
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
            result = ALL_SCENARIOS
        else:
            config = Config(**{field.name: getattr(args, field.name) for field in fields(Config)})
            if args.command == "multiseed":
                result = multi_seed(args.scenario, config, args.seeds, args.arrivals)
                if args.csv:
                    args.csv.write_text(to_csv(result), encoding="utf-8")
            else:
                scenario = load_scenario(args.scenario, args.seed, args.arrivals)
                result = simulate(scenario, args.policy, config) if args.command == "run" else compare(scenario, config)
        serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if getattr(args, "output", None):
            args.output.write_text(serialized, encoding="utf-8")
        print(serialized, end="")
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
