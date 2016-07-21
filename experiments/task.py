# -----------------------------------------------------------------------------
# Copyright (c) 2016, Nicolas P. Rougier, Meropi Topalidou
# Distributed under the (new) BSD License. See LICENSE.txt for more info.
# -----------------------------------------------------------------------------
"""
Generic bandit task using at most 4 cues at 4 different positions.

A task is made of n trials.
A trial is fully described by 4 arrays:

cog:   4 items, indicate which cues are present (A,B,C,D)
mot:   4 items, indicate where cues are present (1,2,3,4)
ass: 4x4 items, indicate the position of cues (A1, A2,..., D3, D4)
rew:   4 items, indicate the reward probability associated with each
                cue for this specific trial

Example
-------

A is in position 3, reward probablity is a
C is in position 2, reward probablity is c
B is not present, D is not present

cue :  [1, 0, 1, 0]
pos :  [0, 1, 1, 0]
rwd :  [a, b, c, d]
ass : [[0, 0, 0, 0],
       [0, 0, 0, 0],
       [0, 0, 1, 0],
       [1, 0, 0, 0]]

Usage
-----

task = Task(n=120)

for trial in task:
    choice = ...
    RT = ...
    reward, best = task.process(trial, choice, RT)
"""
import os
import json
import numpy as np


class Task(object):
    """ A two-armed bandit task """

    def __init__(self, filename="task-guthrie.json"):
        self.index       = None
        self.index_start = None
        self.index_stop  = None

        self.filename = filename
        with open(filename) as f:
            self.parameters = json.load(f)
        self.setup()


    def block(self,index):
        self.index_start = self.blocks[index][0]-1
        self.index_stop  = self.blocks[index][1]
        self.index = self.index_start
        return self

    def setup(self):

        _ = self.parameters

        blocks = []
        for name in _["session"]:
            blocks.append(_[name])

        # Get total number of trials
        n = 0
        self.blocks = []
        start,stop = 0, 0
        for block in blocks:
            start = stop
            stop += block["n_trial"]
            self.blocks.append((start,stop))
            n += block["n_trial"]

        # Build corresponding arrays
        self.trials = np.zeros(n, [("mot", float, 4),
                                   ("cog", float, 4),
                                   ("ass", float, (4,4)),
                                   ("rwd", float, 4),
                                   ("rnd", float, 1) ] )
        self.records  = np.zeros(n, [("choice",  float, 1),
                                     ("cue",     float, 1),
                                     ("best",    float, 1),
                                     ("valid",   float, 1),
                                     ("RT",      float, 1),
                                     ("reward",  float, 1),
                                     # These values must be collected from the model
                                     ("value", float, 4),
                                     ("CTX:cog -> CTX:ass", float, 4),
                                     ("CTX:cog -> STR:cog", float, 4)] )

        # We draw all random probabilities at once (faster)
        self.trials["rnd"] = np.random.uniform(0,1,n)

        # Build actual trials
        index = 0
        for block in blocks:
            indices = range(len(block["cue"]))
            n_cues = block.get("n_cue", 2) # defaults to 2 cues
            cue = np.array(block["cue"],float)
            P_cue = cue / np.sum(cue)
            pos = block["pos"]
            P_pos = pos / np.sum(pos)

            for i in range(block["n_trial"]):
                cues_idx = np.random.choice(indices, size=n_cues, replace=False, p=P_cue)
                pos_idx  = np.random.choice(indices, size=n_cues, replace=False, p=P_pos)

                trial = self.trials[index]
                trial["cog"][cues_idx] = 1
                trial["mot"][pos_idx]  = 1
                for c, p in zip(cues_idx, pos_idx):
                    trial["ass"][c,p] = 1
                trial["rwd"][...] = block["rwd"]
                index += 1

    def __iter__(self):
        if self.index_start is None:
            self.setup()
            self.index_start = -1
            self.index_stop  = len(self)
            self.index = self.index_start
        return self

    def __next__(self):
        self.index += 1
        if self.index < self.index_stop:
            return self.trials[self.index]

        self.index       = None
        self.index_start = None
        self.index_stop  = None
        raise StopIteration

    def __len__(self):
        return len(self.trials)

    def __getitem__(self, index):
        return self.trials[index]


    def process(self, trial, choice, RT=0.0, model=None, debug=False):
        """
        Process a (motor) choice and return the reward and whether this was the
        best choice for this trial.
        """

        # Do we have a choice at least ?
        if choice < 0:
            # No cue chosen
            cue = -1
            # Choice is not valid
            valid = False
            # Not the best move
            best = False
            # No choice, no reward
            reward = 0.0
        else:
            # Check if choice is valid
            valid = (trial["mot"][choice] == 1.0)
            # Get cue corresponding to motor choice
            cues = np.nonzero(trial["ass"][:,choice])[0]
            assert(len(cues) == 1)
            cue = cues[0]
            # Get whether this is the best choice
            present_rwd = trial["cog"]*trial["rwd"]
            best = max(present_rwd) == present_rwd[cue]
            # Get actual reward
            reward = trial["rnd"] < trial["rwd"][cue]

        # Record everything
        self.records[self.index]["choice"] = choice
        self.records[self.index]["cue"]    = cue
        self.records[self.index]["best"]   = best
        self.records[self.index]["valid"]  = valid
        self.records[self.index]["RT"]     = RT
        self.records[self.index]["reward"] = reward
        if model is not None:
            self.records[self.index]["value"] = model["value"]
            self.records[self.index]["CTX:cog -> CTX:ass"] = model["CTX:cog -> CTX:ass"].weights
            self.records[self.index]["CTX:cog -> STR:cog"] = model["CTX:cog -> STR:cog"].weights

        if debug:
            if best: s = " (+)"
            else:    s = " (-)"
            print("Trial %d%s" % ((self.index+1), s))
            P = self.records[:self.index+1]["best"]
            print("  Mean performance: %.3f" % np.array(P).mean())
            R = self.records[:self.index+1]["reward"]
            print("  Mean reward:      %.3f" % np.array(R).mean())

        return reward, cue, best


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    task = Task()

    for trial in task:
        # Best choice
        best_cue = np.argmax(trial["cog"]*trial["rwd"])
        choice = np.argmax(trial["ass"][best_cue])
        # Random choice
        # n = len(trial["mot"]) - 1 - np.random.randint(0,trial["mot"].sum()-1)
        # choice = np.argsort(trial["mot"])[n]
        # Process choice
        reward, cue, best = task.process(trial, choice, debug=True)
