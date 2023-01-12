# argmapper

A simple workflow for launching, tracking, and resuming jobs with varying argument values and parameter sweeps.

## Quickstart

### Launch multiple jobs
Given a `runfile` containing a list of shell commands:

```bash
sleep 1; echo "First!"
sleep 1; echo "Second!"
sleep 1; echo "Third!"
```

we can launch them line by line as follows:

```shell
argmapper launch runfile --n_jobs 2
```

Argmapper will run the commands in parallel with `n_jobs` workers and keep track of the jobs.
By default, it will write the logs of each command to `runs/runfile/logs/<hash of command>`, and keep the
metadata in `runs/runfile/metadata.json`. The metadata file contains the mapping from the commands
to their hashes, and status information about the jobs.

#### Resuming where we left and adding new jobs
In the case of shutdown, argmapper will by default resume the jobs which have not finished.
Similarly, if we add more jobs to the runlist, argmapper will only run the new commands. The way
argmapper tells if a job has run or not is by the command itself. If it has changed in any way,
e.g., the order of arguments is changed, runfile will assume it's a new job and will re-run it.


### Create a parameter sweep
Given a specification of a parameter value grid `gridspec.yml`:

```yaml
program: python3 my_script.py
parameters:
  alpha:
    values:
      - 1
      - 2
      - 5
  beta:
    values: [0.1, 0.25, 0.5]
  gamma:
    value: 100
```

we can generate a runfile, a list of commands from this grid spec, which will look like this:
```bash
python3 my_script.py --alpha=1 --beta=0.1 --gamma=100
python3 my_script.py --alpha=1 --beta=0.25 --gamma=100
python3 my_script.py --alpha=1 --beta=0.5 --gamma=100
python3 my_script.py --alpha=2 --beta=0.1 --gamma=100
...
```

by running the following command:

```shell
argmapper sweep gridspec.yml
```

The runfile by default will be written to `gridspec.runfile`. You can then launch the sweep using
the `argmapper launch gridspec.runfile` as detailed before.
