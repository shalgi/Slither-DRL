'''
This code is based on the following guide (for DQN for pong) and it's code:
http://www.danielslater.net/2016/03/deep-q-learning-pong-with-tensorflow.html
'''

from utils.parameters_utils import *  #This line auto generated the parameters if they are not exist
from utils.plot_utils import plot_graph
from utils.models_utils import *
from utils.net_utils import *
from utils.log_utils import Logger
from collections import deque
import pickle as pkl
import os
import random
import time
import numpy as np
import tensorflow as tf


# MODEL CONSTANTS
VAR_NO = DQN_params['VAR_NO']  # number of Ws and bs (the variables), number of layers X 2

# Model constants
MAX_STEPS = DQN_params['MAX_STEPS']
NUM_OF_EPOCHS = DQN_params['NUM_OF_EPOCHS']
NUM_OF_GAMES_FOR_TEST = DQN_params['NUM_OF_GAMES_FOR_TEST']

# Load and save constants
WEIGHTS_FILE = DQN_params['WEIGHTS_DIR'] + DQN_params['WEIGHTS_FILE']
BEST_WEIGHTS = DQN_params['WEIGHTS_DIR'] + DQN_params['BEST_WEIGHTS']
DO_LOAD_WEIGHTS = DQN_params['DO_LOAD_WEIGHTS']
WEIGHTS_DIR = DQN_params['WEIGHTS_DIR']
WEIGHTS_TO_LOAD = DQN_params['WEIGHTS_TO_LOAD']

# Game constants:
BEGINING_SCORE = 10

# Initialize logger:
logger = Logger('DQN_test')

class Agent:
    # Agent's constants:
    # Net constants:
    LEARN_RATE = DQN_params['LEARN_RATE']

    # Variables sizes
    FRAMES_PER_OBSERVATION = DQN_params['FRAMES_PER_OBSERVATION']
    LAST_RAW_SCORES_SIZE = DQN_params['LAST_RAW_SCORES_SIZE']
    MEMORY_SIZE = DQN_params['MEMORY_SIZE']

    # Logic constants:
    MIN_MEMORY_SIZE_FOR_TRAINING = DQN_params['MIN_MEMORY_SIZE_FOR_TRAINING']
    MINI_BATCH_SIZE = DQN_params['MINI_BATCH_SIZE']
    FUTURE_REWARD_DISCOUNT = DQN_params['FUTURE_REWARD_DISCOUNT']

    # Action constants:
    INITIAL_RANDOM_ACTION_PROB = DQN_params['INITIAL_RANDOM_ACTION_PROB']  # starting chance of an action being random
    FINAL_RANDOM_ACTION_PROB = DQN_params['FINAL_RANDOM_ACTION_PROB']  # final chance of an action being random
    CONST_DECREASE_IN_EXPLORATION = \
        (INITIAL_RANDOM_ACTION_PROB-FINAL_RANDOM_ACTION_PROB)/(MAX_STEPS*NUM_OF_EPOCHS)

    # Indexes:
    OBS_LAST_STATE_INDEX, OBS_ACTION_INDEX, OBS_REWARD_INDEX, OBS_CURRENT_STATE_INDEX, OBS_TERMINAL_INDEX = range(5)

    # Do write to log?
    WRITE_TO_LOG_EVERY = DQN_params['WRITE_TO_LOG_EVERY']

    # Test or train mode
    TEST_MODE = DQN_params['TEST_MODE']
    if(TEST_MODE):
        print("Test mode!")
        logger.write_to_log("Test mode!")
    # Do learn from expert?
    LEARN_FROM_EXPERT = DQN_params['LEARN_FROM_EXPERT']
    if(LEARN_FROM_EXPERT):
        print("Learn from expert mode!")
        logger.write_to_log("Learn from expert mode!")

    def __init__(self):
        # Variables to train the net
        self.sess = tf.Session()
        self.input_layer, self.output_layer = create_CNN()
        self.actions = tf.placeholder(tf.float32, [None, OUTPUT_DIM])
        self.targets = tf.placeholder(tf.float32, [None])
        self.tvars = tf.trainable_variables()

        # Memory variables
        self.last_state = None      #each state will consist of 4 frames
        self.memory = deque()       #gets tuples of (Xt,At,Rt,X(t+1),terminal)

        # Action variables:
        self.probability_of_random_action = self.INITIAL_RANDOM_ACTION_PROB

        # Set the first action go up (arbitrary choice)
        self.last_action = np.zeros(OUTPUT_DIM)
        self.last_action[0] = 1

        # This part is to do the train step
        readout_action = tf.reduce_sum(tf.multiply(self.output_layer, self.actions), reduction_indices=1)
        cost = tf.reduce_mean(tf.square(self.targets - readout_action))
        self.train_operation = tf.train.AdamOptimizer(self.LEARN_RATE).minimize(cost)

        #initialize variables
        self.sess.run(tf.global_variables_initializer())

        #variables for evaluation:
        self.last_raw_scores = deque()
        self.last_raw_scores.append(BEGINING_SCORE)
        self.bonus = 0

        #time and evaluation variables:
        self.step_number = 0
        self.epoch_no = 0

        # Create folder for weights:
        if (not os.path.exists(WEIGHTS_DIR)):
            os.makedirs(WEIGHTS_DIR)

        # Check if file is not empty
        if (os.path.isfile(WEIGHTS_TO_LOAD) and DO_LOAD_WEIGHTS):
            self.load_weights(WEIGHTS_TO_LOAD)

        # Creates file if it doesn't exisits:
        if (not os.path.isfile(WEIGHTS_FILE)):
            open(WEIGHTS_FILE, 'a').close()

    def take_action(self, request_id):
        # Gradually decrease epsilon, in epsilon greedy policy
        if((self.probability_of_random_action > self.FINAL_RANDOM_ACTION_PROB)
           and (len(self.memory) > self.MIN_MEMORY_SIZE_FOR_TRAINING)):
            self.probability_of_random_action -= self.CONST_DECREASE_IN_EXPLORATION
            if (self.step_number % self.WRITE_TO_LOG_EVERY == 0):
                logger.write_to_log("probability_of_random_action: " + str(self.probability_of_random_action))

        # Select an action according to the Q function with epsilon greedy
        new_action = np.zeros([OUTPUT_DIM])

        if (random.random() <= self.probability_of_random_action)and (not self.TEST_MODE):
            # Choose an action randomly
            action_index = random.randrange(OUTPUT_DIM)
        else:
            # Choose an action given our last state
            readout_t = self.sess.run(self.output_layer, feed_dict={self.input_layer: [self.last_state]})#[0]
            if(self.step_number % self.WRITE_TO_LOG_EVERY == 0):
                logger.write_to_log("Action Q-Values are {}".format(readout_t))
            action_index = np.argmax(readout_t)

        new_action[action_index] = 1

        self.last_action = new_action

        # Write down the action
        send_action(action_index, request_id)

    # Take care of the data and store it in the memory
    def take_one_step(self):
        # Data processing
        frame, score, self.bonus, is_dead, request_id, default_obsrv, AI_action, AI_accel = get_observation()  # get observation

        # Handaling edge cases:
        # Connection problems:
        if(score == 0):
            score = self.last_raw_scores[-1]
        # If from some reason the frame we observed is wrong
        if(len(frame) != CNN_params['INPUT_DIM']):
            print("Warning: current frame doesn't have the right dim! skipping this step.")
            print("frame: " + str(frame))
            logger.write_to_log("Warning: current frame doesn't have the right dim! skipping this step.")
            logger.write_to_log("frame: " + str(frame))
            return

        # If the game began we stack the same frame FRAMES_PER_OBSERVATION times
        if self.last_state is None:
            self.last_state = np.stack(tuple(frame for i in range(self.FRAMES_PER_OBSERVATION)))
            return
        # Poping out the first frame and pushing the last one
        current_state = np.append(self.last_state[1:], [frame], axis = 0)

        # Adding score:
        self.last_raw_scores.append(score)
        if(len(self.last_raw_scores) > self.LAST_RAW_SCORES_SIZE):
            self.last_raw_scores.popleft()

        # Write to log and evaluate
        if(self.step_number % self.WRITE_TO_LOG_EVERY == 0):
            logger.write_to_log("Last raw scores: " + str(self.last_raw_scores))
            print("Avarage raw score for epoch %d step %d: %0.2f" % (self.epoch_no, self.step_number, np.average(self.last_raw_scores)))

        # Getting reward:
        reward = self.get_reward(self.last_raw_scores, is_dead)

        if(self.LEARN_FROM_EXPERT):
            self.last_action = make_one_hot(AI_action, AI_accel)

        else:
            self.take_action(request_id)

        # Do not train when testing the model
        if(not self.TEST_MODE):
            # Make St,At,St+1 invariant to oreintation
            SAS_list = \
                make_invariant_to_orientation(self.last_state, self.last_action, current_state[-1])

            # Adding observations to memory:
            for sas in SAS_list:
                self.memory.append((sas[0], sas[1], reward, sas[2], is_dead))
                # Pop out memory:
                if(len(self.memory) > self.MEMORY_SIZE):
                    self.memory.popleft()
            # If enough steps passed - train:
            if(len(self.memory) > self.MIN_MEMORY_SIZE_FOR_TRAINING):
                self.train()

        # If the bot died restart the observation and raw_score_counting
        if(is_dead):
            print("just died!")
            logger.write_to_log("just died!")
            self.last_state = None
            self.last_raw_scores.clear()
            self.last_raw_scores.append(BEGINING_SCORE)

        # Update last state seen
        self.last_state = current_state

        # Write to logger
        if(self.step_number % self.WRITE_TO_LOG_EVERY == 0):
            logger.write_spacer()

        # In the first epoch it runs to fast in relation to the game, so the agent can't really collect observations like this.
        if(len(self.memory) < self.MIN_MEMORY_SIZE_FOR_TRAINING):
            time.sleep(0.3)

        self.step_number += 1

        if(is_dead):
            wait_for_game_to_start()

    # For a mini_batch of 100 train takes about 0.25 seconds
    def train(self):
        start_time = time.time()
        # Sample a mini_batch to train on
        mini_batch = random.sample(self.memory, self.MINI_BATCH_SIZE)
        # Get the batch variables
        previous_states = [d[self.OBS_LAST_STATE_INDEX] for d in mini_batch]
        actions = [d[self.OBS_ACTION_INDEX] for d in mini_batch]
        rewards = [d[self.OBS_REWARD_INDEX] for d in mini_batch]
        rewards = normalize_rewards_by_max(rewards)
        current_states = [d[self.OBS_CURRENT_STATE_INDEX] for d in mini_batch]
        agents_expected_reward = []
        # This gives us the agents expected reward for each action we might
        agents_reward_per_action = self.sess.run(self.output_layer, feed_dict={self.input_layer: current_states})
        for i in range(len(mini_batch)):
            if mini_batch[i][self.OBS_TERMINAL_INDEX]:
                # This was a terminal frame so there is no future reward...
                agents_expected_reward.append(rewards[i])
            else:
                agents_expected_reward.append(
                    rewards[i] + self.FUTURE_REWARD_DISCOUNT * np.max(agents_reward_per_action[i]))

        if(self.step_number % self.WRITE_TO_LOG_EVERY == 0):
            logger.write_to_log("rewards: " + str(rewards))
            logger.write_to_log("agents_expected_reward: " + str(agents_expected_reward))

        # learn that these actions in these states lead to this reward
        self.sess.run(self.train_operation, feed_dict={
            self.input_layer: previous_states,
            self.actions: actions,
            self.targets: agents_expected_reward})

        #print("the training took {} time to run".format(time.time() - start_time))


    def get_reward(self, raw_scores, is_dead):
        death_punishment = -50
        no_gain_punishment = -1
        reward = raw_scores[-1] - raw_scores[-2]
        if(is_dead):
            reward = death_punishment
        elif(reward <= 0):
            reward += no_gain_punishment

        return reward + self.bonus


    def load_weights(self, file_name):
        with open(file_name, 'rb') as f:  # BEST_WEIGHTS
            for var, val in zip(self.tvars, pkl.load(f)):
                self.sess.run(tf.assign(var, val))
        print("successfully loaded " + file_name)

    def save_weights(self, file_name):
        with open(file_name, 'wb') as f:
            pkl.dump(self.sess.run(self.tvars), f, protocol=2)
        print("successfully saved " + file_name)


if __name__ == '__main__':
    # Initialize agent
    avg_scores_per_step = []
    avg_scores_per_epoch = []
    best_avg_per_step = 0
    agent = Agent()
    # The division of steps to epochs is for evaluation
    print("experiment started!")

    while(agent.epoch_no < NUM_OF_EPOCHS):
        # Nulify relevant properties
        agent.step_number = 0
        avg_scores_per_step = []
        # Loop over k steps
        while agent.step_number < MAX_STEPS:
            agent.take_one_step()
            #write to log and add to plot array:
            if (agent.step_number % agent.WRITE_TO_LOG_EVERY == 0):
                avg_scores_per_step.append(np.average(agent.last_raw_scores))
                logger.write_to_log("avg_scores_per_step" + str(avg_scores_per_step))

        # Save weights and best weights:
        #last loaded weights will be override on the first save
        if(not agent.TEST_MODE):
            agent.save_weights(WEIGHTS_FILE)
            if(avg_scores_per_step[-1] > best_avg_per_step):
                best_avg_per_step = avg_scores_per_step[-1]
                agent.save_weights(BEST_WEIGHTS)

        # Evaluation and plotting
        plot_graph(avg_scores_per_step, "Average Score Per 100 Steps", "DQN_avg_score_per_step_by_epoch_"+str(agent.epoch_no), "Step No.", "Average score")
        avg_scores_per_epoch.append(np.average(avg_scores_per_step))
        logger.write_to_log("avg_scores_per_epoch" + str(avg_scores_per_epoch))
        logger.write_spacer()
        agent.epoch_no += 1

    plot_graph(avg_scores_per_epoch, "Average Score Per Epoch", "DQN_avg_score_per_epoch_for_experiment", "Epoch No.", "Average score")
    print("finished experiement")
