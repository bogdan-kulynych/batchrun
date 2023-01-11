#!/usr/bin/python3
import os
import sys
import stat
import json
import pathlib
import hashlib
import itertools
import subprocess

from typing import Optional

try:
    import click
    import yaml
except ImportError as e:
    sys.exit(f"Environment is not configured properly: {e}")


PROGRAM_NAME = "gridrun"
SPEC_ERROR_MARKER = "Spec error"
RUN_CMD_TEMPLATE = "{runner} run {spec_name} '{program}' args='{args}'"
SWEEP_CMD_TEMPLATE = (
    "cat {runfile}"
    ' | while read line; do echo "${{line}} --log_dir={log_dir} --mode={mode}"; done'
    " | parallel --bar -j {n_jobs} {parallel_args}"
)
DEFAULT_LOG_DIR = pathlib.Path("logs")
RUNFILE_TEMPLATE = "{spec_name}.runfile"


def prepare_as_filename(s):
    """
    >>> prepare_as_filename("python experiments/run.py")
    'python__experiments__run__py'
    """
    return s.replace("/", "__").replace(" ", "__").replace(".", "__").replace("=", "_")


def get_config_summary(kwargs):
    """
    >>> get_config_summary({"alpha": 1, "beta": "val"})
    'alpha_1__beta_val'
    """
    pair_strs = [f"{k}={v}" for k, v in kwargs.items()]
    return prepare_as_filename("__".join(pair_strs))


def get_cmd_arg_str(kwargs):
    """
    >>> get_cmd_arg_str({"alpha": 1, "beta": "val"})
    '--alpha=1 --beta=val'
    """
    return " ".join(f"--{k}={v}" for k, v in kwargs.items())


def generate_commands(spec_name, program, config):
    commands = []
    for parameter_values in itertools.product(*config.values()):
        args = json.dumps(dict(zip(config.keys(), parameter_values)))
        program_escaped = program.replace('"', '\\"')
        commands.append(
            RUN_CMD_TEMPLATE.format(
                runner=__file__,
                spec_name=spec_name,
                program=program_escaped,
                args=args,
            )
        )

    return commands


def parse_spec(spec_path):
    """
    Parse specification from a YAML file.
    """
    with open(spec_path, "r") as f:
        spec = yaml.safe_load(f)

    try:
        program = spec["program"]
    except KeyError:
        sys.exit(f"{SPEC_ERROR_MARKER}: executable not specified.")

    try:
        parameters_spec = spec["parameters"]
    except KeyError:
        sys.exit(f"{SPEC_ERROR_MARKER}: parameters not specified.")
    config = {}
    for parameter_name, parameter_section in parameters_spec.items():
        parameter_values = parameter_section.get("values")
        parameter_value = parameter_section.get("value")
        if parameter_values:
            config[parameter_name] = parameter_values
        elif parameter_value:
            config[parameter_name] = [parameter_value]

    return program, config


def create_runfile(spec_path, runfile):
    spec_path = pathlib.Path(spec_path)
    spec_name = spec_path.stem

    program, config = parse_spec(spec_path)
    commands = generate_commands(spec_name, program, config)

    runfile = runfile or RUNFILE_TEMPLATE.format(spec_name=spec_name)
    with open(runfile, "w+") as f:
        f.write("\n".join(commands) + "\n")


@click.group()
def cli():
    pass


@cli.command()
@click.argument("spec", type=click.Path(exists=True))
@click.option(
    "--runfile",
    help="Location for the generated runfile.",
    type=click.Path(exists=False),
    default=None,
)
def init(
    spec,
    runfile,
):
    """
    Initialize a sweep over script parameters in parallel.

    The command generates a runfile containing the commands which are to be
    executed in parallel. Then, it runs each command from the runfile using GNU parallel.

    The command requires a specification YAML file for the search in a format compatible with
    Weights and Biases sweep config.
    """
    create_runfile(spec, runfile)


@cli.command()
@click.argument(
    "config_path",
    type=click.Path(exists=False),
)
@click.option(
    "--mode",
    type=click.Choice(["resume", "overwrite"]),
    help="How to deal with previous runs.",
    default="resume",
)
@click.option(
    "--log_dir",
    help="Location for logs.",
    type=click.Path(exists=False),
    default=DEFAULT_LOG_DIR,
)
@click.option(
    "-j",
    "--n_jobs",
    help="Number of parallel jobs. By default, executes sequentially.",
    default=1,
)
@click.option(
    "--parallel_args", help="Arguments to pass to GNU parallel.", default=None
)
@click.option(
    "--silent", help="Whether to output messages.", default=False, is_flag=True
)
def sweep(config_path, mode, log_dir, n_jobs, parallel_args, silent):
    """
    Launch a sweep over a grid for different parameter values.

    The commands takes as input a CONFIG_PATH, which is the location of the spec file or the runfile.
    If it is the spec, it first generates a runfile containing the commands which are to be
    executed in parallel. Then, it runs each command from the runfile using GNU parallel.
    """
    config_path = pathlib.Path(config_path)
    config_ext = config_path.suffix

    # Assuming the config path is the spec.
    if config_ext.lower() in [".yml", ".yaml"]:
        spec_name = config_path.stem
        runfile = RUNFILE_TEMPLATE.format(spec_name=spec_name)
        if not silent:
            print(f"Using spec: {config_path}")
            print(f"Generating runfile: {runfile}")
        create_runfile(config_path, runfile=runfile)

    else:
        runfile = config_path

    # Otherwise, assuming the config path is the runfile.
    parallel_args = parallel_args or ""
    parallel_cmd = SWEEP_CMD_TEMPLATE.format(
        runfile=runfile,
        n_jobs=n_jobs,
        parallel_args=parallel_args,
        log_dir=log_dir,
        mode=mode,
    )

    if not silent:
        print(f"Starting sweep from runfile: {runfile}")
        print(f"Logging to: {log_dir}")
        print(f"Mode: {mode}")
        print(f"Executing: {parallel_cmd}")

    subprocess.call(
        [parallel_cmd],
        shell=True,
    )


@cli.command()
@click.argument("spec_name")
@click.argument("cmd")
@click.option(
    "--args",
    help="JSON dictionary of arguments passed to the command.",
    type=str,
    default="{}",
)
@click.option(
    "--log_dir",
    help="Directory to write logs.",
    type=click.Path(exists=False),
    default=DEFAULT_LOG_DIR,
)
@click.option(
    "--mode",
    type=click.Choice(["resume", "overwrite"]),
    help="How to deal with previous runs.",
    default="resume",
)
def run(spec_name, cmd, args, log_dir, mode):
    """
    Run command and write logs.
    """
    kwargs = json.loads(args)
    arg_str = get_cmd_arg_str(kwargs)
    RUN_LOG_DIR = pathlib.Path(log_dir) / spec_name / get_config_summary(kwargs)
    pathlib.Path.mkdir(RUN_LOG_DIR, parents=True, exist_ok=True)
    status_sentinel_path = RUN_LOG_DIR / "status.txt"

    if not status_sentinel_path.exists() or mode == "overwrite":
        with open(RUN_LOG_DIR / "out.log", "w+") as stdout, open(
            RUN_LOG_DIR / "err.log", "w+"
        ) as stderr:
            retcode = subprocess.call(
                [f"{cmd} {arg_str}"], shell=True, stdout=stdout, stderr=stderr
            )
        with open(status_sentinel_path, "w+") as f:
            f.writelines(f"{retcode}\n")

        sys.exit(retcode)


if __name__ == "__main__":
    cli()
