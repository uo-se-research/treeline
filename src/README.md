# Structure:

- [Analysis](analysis): 
- [mcts](mcts): is a package where all the main MCTS algorithm lives.
- [collect_cost](collect_costs.py) A script to collect the search result from the inputs files names then save it in
  csv format for analysis. 
- [pygramm](pygramm): a submodule to read grammar files and return them as objects we can work with.
- [treeline](treeline.py): is the file used to run an experiment.
- [helpers](helpers.py): Helper functions for different tasks (search, analysis, plot, etc).