"""CLI del pipeline: tareas de extraccion, modelado y loop programado."""

from __future__ import annotations

import argparse
import logging
import time

from pipeline.config import load_config

log = logging.getLogger("pipeline")


def run_all(cfg) -> dict:
    from agrodb import get_conn
    from pipeline import extract_prices, extract_siap, extract_weather
    from pipeline import models, reference

    results = {}
    conn = get_conn("production.db", cfg.db_dir)
    results["reference"] = {"crops": reference.seed_crops(conn)}
    conn.close()
    results["siap"] = extract_siap.run(cfg)
    results["prices"] = extract_prices.run(cfg)
    results["weather"] = extract_weather.run(cfg)
    results["model"] = models.predict_all(cfg)
    return results


def run_task(cfg, task: str) -> dict:
    if task == "all":
        return run_all(cfg)
    if task == "reference":
        from agrodb import get_conn
        from pipeline import reference
        conn = get_conn("production.db", cfg.db_dir)
        n = reference.seed_crops(conn)
        conn.close()
        return {"crops": n}
    if task == "siap":
        from pipeline import extract_siap
        return extract_siap.run(cfg)
    if task == "prices":
        from pipeline import extract_prices
        return extract_prices.run(cfg)
    if task == "weather":
        from pipeline import extract_weather
        return extract_weather.run(cfg)
    if task == "model":
        from pipeline import models
        return models.predict_all(cfg)
    raise ValueError(f"Tarea desconocida: {task}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agro-pipeline")
    parser.add_argument(
        "task",
        nargs="?",
        default="all",
        choices=["all", "reference", "siap", "prices", "weather", "model"],
        help="Tarea a ejecutar (default: all)",
    )
    parser.add_argument("--loop", action="store_true",
                        help="Repetir en intervalo PIPELINE_INTERVAL_HOURS")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = load_config()
    if args.loop:
        interval = cfg.pipeline_interval_hours * 3600
        if interval <= 0:
            parser.error("--loop requiere PIPELINE_INTERVAL_HOURS > 0")
        while True:
            try:
                run_task(cfg, args.task)
            except Exception:
                log.exception("Fallo en la corrida del pipeline")
            log.info("Proxima corrida en %s h", cfg.pipeline_interval_hours)
            time.sleep(interval)
    else:
        results = run_task(cfg, args.task)
        log.info("Resultado: %s", results)


if __name__ == "__main__":
    main()
