# TreeLine

This is a trimmed copy of huge project from which TreeLine is a small part. We do our best to keep it contained and
easy to navigate. Before delivery, we tested running the code and it works as expected. However, you should note two
important things.
- (1) The code as it is require a careful handling to run. You have to establish a listener within docker after making
sure you compiled our version of afl-fuzz.c. The detials to do so are not easy to put in writing in a very short time.
However, for anyone familiar with Docker, you have to run a container, move afl-fuzz under the perffuzz repo, build,
then run afl as documented in PerfFuzz repo. Only then you can run the code here.
- (2) Note all strategies that implemented in this code are used in the paper. We carefully selected the configuration
to run the experiments as described in the paper. This is a research code that has many function implemented to explore
some ideas.

# Usage:
[TBA]

# Navigational Helper:
- The [src](src) directory is where all source code is stored.
  - The [gramm](src/gramm) directory is a package to read grammar files and return them as objects we can work with.
  - The [mcts](src/mcts) directory is a package where all the main MCTS algorithm lives.
  - The file [epsilonStrategy](src/epsilonStrategy.py), [targetAppConnect](src/targetAppConnect.py), and [utilities](src/utilities.py) are helper files for non-core functions.
  - The file [mcts_exper](src/mcts_exper.py) is the file used to run an experiment.
- The [docker_image](docker_image) directory is the docker image file and all update AFL file live. 
- The [target_apps](target_apps) directory is where all the benchmarks we used, grammars, seed inputs are stored.
