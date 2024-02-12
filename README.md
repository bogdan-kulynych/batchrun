# batchrun

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
batchrun launch runfile --n_jobs 2
```

Batchrun will run the commands in parallel with `n_jobs` workers and keep track of the jobs.
By default, it will write the logs of each command to `runs/runfile/logs/<hash of command>`, and keep the
metadata in `runs/runfile/metadata.json`. The metadata file contains the mapping from the commands
to their hashes, and status information about the jobs.

#### Resuming where we left and adding new jobs
In the case of shutdown, batchrun will by default resume the jobs which have not finished.
Similarly, if we add more jobs to the runlist, batchrun will only run the new ones. The way
batchrun tells if a job is new or not is by the command itself. If the command has changed in any
way, e.g., the order of arguments is different, batchrun will assume it's a new job.


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

we can generate a list of commands corresponding to all possible parameter value combinations:
```bash
python3 my_script.py --alpha=1 --beta=0.1 --gamma=100
python3 my_script.py --alpha=1 --beta=0.25 --gamma=100
python3 my_script.py --alpha=1 --beta=0.5 --gamma=100
python3 my_script.py --alpha=2 --beta=0.1 --gamma=100
...
```

by running the following command:

```shell
batchrun sweep gridspec.yml
```

The runfile containing the commands by default will be written to `gridspec.runfile`. You can then
launch the sweep using the `batchrun launch gridspec.runfile` as detailed before.
