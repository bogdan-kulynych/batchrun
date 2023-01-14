import pytest
import pathlib
import json
from click.testing import CliRunner

from argmapper import cli

runner = CliRunner()
fixtures_dir = pathlib.Path(__file__).parent.absolute() / "fixtures"


SWEEP_FIXTURES = ["normal"]
LAUNCH_FIXTURES = ["normal"]


@pytest.mark.parametrize(
    "grid_spec,expected_runfile",
    [
        (fixtures_dir / f"{fixture_name}.yml", fixtures_dir / f"{fixture_name}.runfile")
        for fixture_name in SWEEP_FIXTURES
    ],
)
def test_sweep(tmp_path_factory, grid_spec, expected_runfile):
    out_path = tmp_path_factory.mktemp("runs") / "runfile"
    args = f"{grid_spec} --out {out_path}"
    res = runner.invoke(cli.sweep, args)

    assert res.exit_code == 0
    expected_text_in_output = "Runfile generated" in res.output

    with open(expected_runfile) as f:
        expected_runfile_content = f.read()

    with open(out_path) as f:
        generated_runfile_content = f.read()

    assert generated_runfile_content == expected_runfile_content


def launch(runfile, accounting_dir):
    args = f"{runfile} --accounting_dir={str(accounting_dir)}"
    print(args)
    return runner.invoke(cli.launch, args)


@pytest.mark.parametrize(
    "spec_name",
    LAUNCH_FIXTURES,
)
def test_launch_custom_accounting_files(tmp_path_factory, spec_name):
    runfile = fixtures_dir / f"{spec_name}.runfile"
    accounting_dir = tmp_path_factory.mktemp("runs")

    res = launch(runfile, accounting_dir)
    assert res.exit_code == 0
    expected_text_in_output = "Starting sweep from runfile" in res.output

    logs_dir = accounting_dir / "logs"
    assert logs_dir.exists()

    state_db_path = accounting_dir / "metadata.json"
    assert state_db_path.exists()

    with open(runfile) as f:
        num_commands = len(f.readlines())
    assert len(list(logs_dir.iterdir())) == num_commands
