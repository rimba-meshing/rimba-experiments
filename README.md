# RIMBA Experiments

Protocols and analysis tools for reproducing RIMBA measurements. The `rimba/`
submodule pins the exact source revision used by each experiment-repository
commit.

## Start here

Clone with the source submodule initialized:

```bash
git clone --recurse-submodules https://github.com/rimba-meshing/rimba-experiments.git
cd rimba-experiments
```

Read [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for software requirements,
dataset setup, and the run commands. The protocol and its measurement
definitions are in [protocols/paper_protocol.md](protocols/paper_protocol.md).

This repository contains experiment code and derived outputs only. Dataset
files are obtained separately and are not checked in.
