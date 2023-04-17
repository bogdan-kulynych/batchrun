#!/usr/bin/python3
import os
import sys
import json
import time
import shlex
import pathlib
import hashlib
import subprocess

from typing import Optional

import click
import joblib
import rich

from rich import print
from rich.panel import Panel
from rich.live import Live
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)

from .lib import parse_spec


DEFAULT_ACCOUNTING_DIR = pathlib.Path("runs")
DEFAULT_STATE_DB_FILENAME = "metadata.json"
DEFAULT_RUNFILE_TEMPLATE = "{spec_name}.runfile"
RUN_CMD_TEMPLATE = "{program} {args}"


def get_cmd_arg_str(kwargs):
    """
    >>> get_cmd_arg_str({"alpha": 1, "beta": "val"})
    '--alpha=1 --beta=val'
    """
    return " ".join(f"--{k}={v}" for k, v in kwargs.items())


def generate_commands(spec):
    commands = []
    for parameters in spec.expand():
        args = get_cmd_arg_str(parameters)
        program_escaped = spec.program.replace("'", "\\'")
        commands.append(
            RUN_CMD_TEMPLATE.format(
                program=program_escaped,
                args=args,
            )
        )

    return commands


def parse_args(cmd):
    """
    >>> parse_args("python3 script.py --alpha=1 --beta=beta_val --flag")
    {'alpha': '1', 'beta': 'beta_val', 'flag': True}
    """
    kwargs = {}
    lexer = shlex.shlex(cmd, posix=True)
    lexer.whitespace_split = True
    for token in lexer:
        if token.startswith("--"):
            key_value = token.split("=")
            key = key_value[0].lstrip("--")
            value = key_value[1] if len(key_value) > 1 else True
            kwargs[key] = value

    return kwargs


def cmd_hash(cmd):
    return hashlib.sha256(cmd.encode()).hexdigest()[:16]


def exec_job(command, stdout_path, stderr_path):
    parameters = parse_args(command)

    with open(stdout_path, "w+") as out, open(stderr_path, "w+") as err:
        start = time.time()
        retcode = subprocess.call(
            [command],
            shell=True,
            stdout=out,
            stderr=err,
        )
        end = time.time()

    return dict(
        start=start,
        runtime=end - start,
        status=retcode,
        command=command,
        parameters=parameters,
    )


def schedule_jobs(job_batch, log_dir, progress):
    for command in job_batch:
        h = cmd_hash(command)
        job_log_path = log_dir / h
        pathlib.Path.mkdir(job_log_path, parents=True, exist_ok=True)

        stdout_path = job_log_path / "out.log"
        stderr_path = job_log_path / "err.log"

        progress.log(f"{h}: {command}")
        progress.console.print(
            Panel(
                "\n".join(
                    [
                        f"tail -f {stdout_path}",
                        f"tail -f {stderr_path}",
                    ]
                ),
                title=h,
            )
        )
        yield joblib.delayed(exec_job)(command, stdout_path, stderr_path)


def batch(iterable, n=1):
    # https://stackoverflow.com/questions/8290397/how-to-split-an-iterable-in-constant-size-chunks
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx : min(ndx + n, l)]


@click.group()
def cli():
    pass


@cli.command()
@click.argument("spec", type=click.Path(exists=True))
@click.option(
    "--out",
    help="Location for the generated runfile.",
    type=click.Path(exists=False),
    default=None,
)
def sweep(spec, out):
    """
    Create a list of command line jobs sweeping an argument grid.

    The command generates a runfile containing the commands which are to be executed in parallel.
    It requires a SPEC file in YAML.
    """
    spec_path = pathlib.Path(spec)
    spec_name = spec_path.stem

    spec = parse_spec(spec_path)
    commands = generate_commands(spec)

    out = out or DEFAULT_RUNFILE_TEMPLATE.format(spec_name=spec_name)
    with open(out, "w+") as f:
        f.write("\n".join(commands) + "\n")

    print(f"Runfile generated: {out}")


@cli.command()
@click.argument(
    "runfile",
    type=click.Path(exists=True),
)
@click.option(
    "--mode",
    type=click.Choice(["resume", "overwrite", "retry_failed"]),
    help="How to deal with previous runs.",
    default="resume",
)
@click.option(
    "-j",
    "--n_jobs",
    help="Number of jobs to execute in parallel. By default is one.",
    type=int,
    default=1,
)
@click.option(
    "--accounting_dir",
    help="Location for run accounting. By default is {DEFAULT_ACCOUNTING_DIR}/<spec_name>",
    type=click.Path(exists=False),
    default=None,
)
@click.option(
    "--state_db_filename",
    help="Filename for the job state database.",
    type=str,
    default=DEFAULT_STATE_DB_FILENAME,
)
def launch(runfile, mode, n_jobs, accounting_dir, state_db_filename):
    """
    Launch, track, and resume command line jobs.

    The command takes as input a RUNFILE containing the commands which are to be executed in
    parallel, line by line. The stem of the RUNFILE is assumed to be the name of the launch
    by default.
    """
    runfile = pathlib.Path(runfile)
    runfile_ext = runfile.suffix
    spec_name = runfile.stem

    # If the runfile is YAML-formatted, assuming it is the grid specification by mistake.
    if runfile_ext.lower() in [".yml", ".yaml"]:
        raise ValueError(
            f"Have you provided the grid spec instead of the runfile? "
            f"Generate the runfile first using the sweep command."
        )

    if accounting_dir is None:
        base_accounting_dir = pathlib.Path.cwd() / DEFAULT_ACCOUNTING_DIR
        accounting_dir = base_accounting_dir / spec_name

    accounting_dir = pathlib.Path(accounting_dir)
    log_dir = accounting_dir / "logs"
    pathlib.Path.mkdir(accounting_dir, parents=True, exist_ok=True)

    # Load or initialize current state.
    state_db_path = accounting_dir / state_db_filename
    if state_db_path.exists():
        with open(state_db_path, "r") as f:
            state_db = json.load(f)
    else:
        state_db = {}

    # Load job list.
    with open(runfile, "r") as f:
        commands = [
            line.strip()
            for line in f.readlines()
            if line != "\n" and not line.startswith("#")
        ]

    print(f"Starting sweep from runfile: {runfile}")
    print(f"Accounting in directory: {accounting_dir}")
    print(f"Mode: {mode}")
    print(f"Number of parallel jobs: {n_jobs}")

    # Restore or initialize state.
    job_queue = []
    num_fails = 0
    num_skipped = 0

    if mode in ["resume", "retry_failed"]:
        for command in commands:
            h = cmd_hash(command)
            resuming = False
            if h in state_db:
                status = state_db[h].get("status")
                if status is not None:
                    if status == 0:
                        num_skipped += 1
                    if status != 0:
                        num_fails += 1
                        if mode == "resume":
                            num_skipped += 1
                        elif mode == "retry_failed":
                            job_queue.append(command)
            else:
                job_queue.append(command)

    elif mode == "overwrite":
        job_queue = commands
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Execute the jobs.
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        auto_refresh=True,
    )

    task_indicator = progress.add_task("", total=len(commands))
    progress.update(task_indicator, advance=num_skipped)

    with progress:
        with joblib.Parallel(n_jobs=n_jobs) as parallel:
            for job_batch in batch(job_queue, n_jobs):
                results = parallel(
                    delayed_job
                    for delayed_job in schedule_jobs(job_batch, log_dir, progress)
                )

                progress.update(task_indicator, advance=len(job_batch), refresh=True)
                for result in results:
                    h = cmd_hash(result["command"])
                    state_db[h] = result

                    retcode = result["status"]
                    if retcode != 0:
                        progress.log(f"[bold red]{h}: Failed")
                    else:
                        progress.log(f"[bold]{h}: Success")

                    if retcode != 0:
                        num_fails += 1

                with open(state_db_path, "w+") as f:
                    json.dump(state_db, f, indent=2)


if __name__ == "__main__":
    cli()
