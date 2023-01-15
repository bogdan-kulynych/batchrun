import sys
import yaml

from dataclasses import dataclass


SPEC_ERROR_MARKER = "Spec error"


@dataclass
class GridSpec:
    """Parsed grid specification."""

    program: str
    parameters: dict


def parse_spec(spec_path):
    """
    Parse grid specification from a YAML file.
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

    spec = GridSpec(program=program, parameters={})
    for parameter_name, parameter_section in parameters_spec.items():
        parameter_values = parameter_section.get("values")
        parameter_value = parameter_section.get("value")
        if parameter_values:
            spec.parameters[parameter_name] = parameter_values
        elif parameter_value:
            spec.parameters[parameter_name] = [parameter_value]

    return spec
