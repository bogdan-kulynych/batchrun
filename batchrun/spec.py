import sys
import yaml
import itertools

from dataclasses import dataclass


SPEC_ERROR_MARKER = "Spec error"


@dataclass
class GridSpec:
    """Parsed grid specification."""

    program: str
    parameters: dict

    def expand(self) -> dict:
        """
        Iterate over the product of possible parameter values.
        """
        for parameter_values in itertools.product(*self.parameters.values()):
            yield dict(zip(self.parameters.keys(), parameter_values))


def parse_spec(spec_path: str) -> GridSpec:
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
        parameter_max = parameter_section.get("max")
        parameter_min = parameter_section.get("min")
        parameter_step = parameter_section.get("step")
        if parameter_values:
            spec.parameters[parameter_name] = parameter_values
        elif parameter_value:
            spec.parameters[parameter_name] = [parameter_value]
        elif parameter_max:
            if parameter_min is not None and parameter_step is not None:
                spec.parameters[parameter_name] = list(
                    range(parameter_min, parameter_max, parameter_step)
                )
            elif parameter_min is not None:
                spec.parameters[parameter_name] = list(
                    range(parameter_min, parameter_max)
                )
            else:
                spec.parameters[parameter_name] = list(range(parameter_max))

    return spec
