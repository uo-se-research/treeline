# TreeLine

<img align="left" src="treeline-logo.png" width=100 alt="TreeLine Logo">
Finding slow input faster using Monte-Carlo Tree Search and application provided context-free grammar. 

Given some target application and grammar on how to generate input for it, TreeLine will generate
high-level inputs that exercise the target application's worst-execution case. TreeLine allows you to
specify the maximum length of the desired sample inputs (test cases). TreeLine uses the grammar
provided to build a derivation tree that is sampled following the Monte-Carlo Tree Search technique.

## Usage:

- Build the Docker image:
```sh
docker build -t treeline:latest .
```

- Run a new container
```sh
docker run -p 2300:2300 --name icse -it treeline /bin/bash
```
- From the container run the AFL listener for one of the target applications using the commands provided in their 
documentation ([wf](target_apps/word-frequency/README.md), [libxml](target_apps/libxml2/README.md), 
[graphviz](target_apps/graphviz/README.md), [flex](target_apps/flex/README.md)).
e.g. , 
```shell
afl-treeline -i /home/treeline/target_apps/graphviz/inputs/ -o /home/results/graphviz-001 -p -N 500 -d dot
```

Run [mcts_expr](src/mcts_exper.py) with the configuration you want form your local machine or the `fse` container itself. 
```shell
python3 mcts_exper.py
```

## Navigational Helper:
- The [src](src) directory is where all source code is stored.
  - The [pygramm](src/pygramm) a submodule to read grammar files and return them as objects we can work with.
  - The [mcts](src/mcts) is a package where all the main MCTS algorithm lives.
  - The file [targetAppConnect](src/targetAppConnect.py), and [helpers](src/helpers.py) are helper files for non-core
  functions.
  - The file [mcts_exper](src/mcts_exper.py) is the file used to run an experiment.
- The [resources](resources) directory is dir where we keep some resources needed during building the docker container
and facilitating the runs.  
- The [target_apps](target_apps) directory is where all the benchmarks we used, grammars, seed inputs are stored.
