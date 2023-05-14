# TreeLine

<img align="left" src="treeline-logo.png" width=100 alt="TreeLine Logo">
Finding slow input faster using Monte-Carlo Tree Search and application provided context-free grammar. 

Given some target application and grammar on how to generate inputs for it, TreeLine will generate
high-level inputs that exercise the target application's worst-execution case. TreeLine allows you to
specify the maximum length of the desired sample inputs (test cases). It also uses the grammar
provided to build a derivation tree that is sampled following the Monte-Carlo Tree Search technique.

## Related Publication(s):




## How _TreeLine_ Works:

The seed for _TreeLine_ is a context-free grammar.
You can either use a grammar sensitizers from seed inputs or provide grammar from the target application documentation.

The second phase is fully automated.
The algorithm will annotate the provided grammar with a cost for each production-rule.
The cost will be driving the derivation options based on the maximum budget you specified.
Derivations are represented as search tree.
This is the same tree used for balancing the search using MCTS. 
The algorithm will then go on generating inputs, collecting feedback, balancing the search in each iteration until the time is up.
There are many parameters we are balancing in each iteration such as the reward, the coverage, the path in the search tree. 
If the search stall according to different paramters, the algorihtm might even drop the search tree and starts with new one for faster and more effective results.

By the end of the search the algorithm will have generated many inputs one of which is maximizing the execution cost.

![TreeLine Overview](img/fig-overview.png)

## Usage:

- Build the Docker image:
```sh
docker build -t treeline-img:latest .
```

- Run a new container
```sh
docker run -p 2300:2300 --name treeline -it treeline-img /bin/bash
```
- From the container run the AFL listener for one of the target applications using the commands provided in their 
documentation ([wf](target_apps/word-frequency/README.md), [libxml](target_apps/libxml2/README.md), 
[graphviz](target_apps/graphviz/README.md), [flex](target_apps/flex/README.md)).
e.g. , 
```shell
afl-socket -i /home/treeline/target_apps/graphviz/inputs/ -o /home/results/graphviz-001 -p -N 500 -d dot
```

Run [mcts_expr](src/mcts_exper.py) with the configuration you want form your local machine or the `treeline` container itself. 
```shell
python3 treeline.py 
```

## Example Outputs:




## Dependencies:

All the dependencies are managed by the docker file provided. However, a major requirements for building and running
_Treeline_ is to build it on x86 processor. This is required for AFL's instrumentation to work. 

