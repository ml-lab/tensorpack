#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File: common.py
# Author: Yuxin Wu <ppwwyyxxc@gmail.com>
import random, time
import threading, multiprocessing
import numpy as np
from tqdm import tqdm
from six.moves import queue

from tensorpack import *
from tensorpack.predict import get_predict_func
from tensorpack.utils.concurrency import *
from tensorpack.utils.stat import  *
from tensorpack.callbacks import *

global get_player

def play_one_episode(player, func, verbose=False):
    # 0.01-greedy evaluation
    def f(s):
        spc = player.get_action_space()
        act = func([[s]])[0][0].argmax()
        if random.random() < 0.01:
            act = spc.sample()
        if verbose:
            print(act)
        return act
    return np.mean(player.play_one_episode(f))

def play_model(cfg):
    player = get_player(viz=0.01)
    predfunc = get_predict_func(cfg)
    while True:
        score = play_one_episode(player, predfunc)
        print("Total:", score)

def eval_with_funcs(predict_funcs, nr_eval):
    class Worker(StoppableThread):
        def __init__(self, func, queue):
            super(Worker, self).__init__()
            self.func = func
            self.q = queue
        def run(self):
            player = get_player()
            while not self.stopped():
                score = play_one_episode(player, self.func)
                self.queue_put_stoppable(self.q, score)

    q = queue.Queue(maxsize=2)
    threads = [Worker(f, q) for f in predict_funcs]

    for k in threads:
        k.start()
    stat = StatCounter()
    try:
        for _ in tqdm(range(nr_eval)):
            r = q.get()
            stat.feed(r)
    except:
        logger.exception("Eval")
    finally:
        logger.info("Waiting for all the workers to finish the last run...")
        for k in threads: k.stop()
        for k in threads: k.join()
        if stat.count > 0:
            return (stat.average, stat.max)
        return (0, 0)

def eval_model_multithread(cfg, nr_eval):
    func = get_predict_func(cfg)
    NR_PROC = min(multiprocessing.cpu_count() // 2, 8)
    mean, max = eval_with_funcs([func] * NR_PROC, nr_eval)
    logger.info("Average Score: {}; Max Score: {}".format(mean, max))

class Evaluator(Callback):
    def __init__(self, nr_eval, input_names, output_names):
        self.eval_episode = nr_eval
        self.input_names = input_names
        self.output_names = output_names

    def _before_train(self):
        NR_PROC = min(multiprocessing.cpu_count() // 2, 8)
        self.pred_funcs = [self.trainer.get_predict_func(
            self.input_names, self.output_names)] * NR_PROC

    def _trigger_epoch(self):
        t = time.time()
        mean, max = eval_with_funcs(self.pred_funcs, nr_eval=self.eval_episode)
        t = time.time() - t
        if t > 8 * 60:  # eval takes too long
            self.eval_episode = int(self.eval_episode * 0.89)
        self.trainer.write_scalar_summary('mean_score', mean)
        self.trainer.write_scalar_summary('max_score', max)
