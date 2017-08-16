from utils.models_utils import *
import pickle as pkl
import os

#TODO: I am not sure if there is a problem here with the Qt thing or not
import matplotlib
matplotlib.use('Qt4Agg')

#CNN constants
OUTPUT_DIM = 64
INPUT_DIM = 400
SQRT_INPUT_DIM  =20 #IN ORDER TO RESHAPE INTO TENSOR
PLN = 2                     #Pool Layers Number
CONV_WINDOW_SIZE = int(SQRT_INPUT_DIM / 2**PLN)
NUM_OF_CHANNELS_LAYER1 = 1
NUM_OF_CHANNELS_LAYER2 = 16     #TODO: Is that really what suppose to be here?
NUM_OF_CHANNELS_LAYER3 = 32
SIZE_OF_FULLY_CONNECTED_LAYER = 256
VAR_NO = 8      #number of Ws and bs (the variables)
KEEP_RATE = 0.8
keep_prob = tf.placeholder(tf.float32)      #TODO: do we use that?

#Model constants
MAX_GAMES = 100
BATCH_SIZE = 5

#Load and save constants
WEIGHTS_FILE = 'weights.pkl'
BEST_WEIGHTS = 'best_weights.pkl'
LOAD = True






def conv2d(x, W):
    return tf.nn.conv2d(x, W, strides=[1, 1, 1, 1], padding='SAME')


def maxpool2d(x):
    #                        size of window         movement of window
    return tf.nn.max_pool(x, ksize=[1, 2, 2, 1], strides=[1, 2, 2, 1], padding='SAME')

def InitializeVarXavier(var_name,var_shape):
    return tf.get_variable(name=var_name, shape=var_shape, dtype= tf.float32,
                    initializer=tf.contrib.layers.xavier_initializer())

initialize = InitializeVarXavier


observations = tf.placeholder(tf.float32, [None,INPUT_DIM])
#trainable variables
weights = {'W_conv1': initialize('wc1',[CONV_WINDOW_SIZE , CONV_WINDOW_SIZE , NUM_OF_CHANNELS_LAYER1 , NUM_OF_CHANNELS_LAYER2]),
           'W_conv2':  initialize('wc2',[CONV_WINDOW_SIZE , CONV_WINDOW_SIZE , NUM_OF_CHANNELS_LAYER2, NUM_OF_CHANNELS_LAYER3]),
           'W_fc': initialize('wfc',[CONV_WINDOW_SIZE  * CONV_WINDOW_SIZE  * NUM_OF_CHANNELS_LAYER3, SIZE_OF_FULLY_CONNECTED_LAYER]),
           'out': initialize('wo',[SIZE_OF_FULLY_CONNECTED_LAYER, OUTPUT_DIM])}

biases = {'b_conv1': initialize('bc1', [NUM_OF_CHANNELS_LAYER2]),
          'b_conv2': initialize('bc2', [NUM_OF_CHANNELS_LAYER3]),
          'b_fc': initialize('bfc', [SIZE_OF_FULLY_CONNECTED_LAYER]),
          'out': initialize('bo', [OUTPUT_DIM])}

#CNN:
x = tf.reshape(observations, shape=[-1, SQRT_INPUT_DIM, SQRT_INPUT_DIM, NUM_OF_CHANNELS_LAYER1])
#first layer: conv + pool
conv1 = tf.nn.relu(conv2d(x, weights['W_conv1']) + biases['b_conv1'])
pool1 = maxpool2d(conv1)
#second layer: conv + pool
conv2 = tf.nn.relu(conv2d(pool1, weights['W_conv2']) + biases['b_conv2'])
pool2 = maxpool2d(conv2)
#last layer - fully connected layer?
r_layer2 = tf.reshape(pool2, [-1, CONV_WINDOW_SIZE * CONV_WINDOW_SIZE * NUM_OF_CHANNELS_LAYER3])
fc = tf.nn.relu(tf.matmul(r_layer2, weights['W_fc']) + biases['b_fc'])
dropped_fc = tf.nn.dropout(fc, KEEP_RATE)

score = tf.matmul(dropped_fc, weights['out']) + biases['out']
actions_probs = tf.nn.softmax(score)

#HERE STARTS THE GRADIENT COMPUTATION
tvars = tf.trainable_variables()
# rewards sums from k=t to T:
rewards_arr = tf.placeholder(tf.float32, [1,None])
# actions - a mask matrix which filters ys result accordint to the actions that were chosen.
actions_mask = tf.placeholder(tf.bool, [None, OUTPUT_DIM])
# return a T size vector with correct (chosen) action values
filtered_actions = tf.boolean_mask(actions_probs, actions_mask)
pi = tf.log(filtered_actions)
#devide by T
#loss = tf.divide(tf.reduce_sum(tf.multiply(pi,rewards_arr)),tf.to_float(tf.size(pi)))
#don't devide by T
loss = tf.reduce_sum(tf.multiply(pi,rewards_arr))
Gradients = tf.gradients(-loss,tvars)

Gradients_holder = [tf.placeholder(tf.float32) for i in range(VAR_NO)]
# then train the network - for each of the parameters do the GD as described in the HW.
#learning_rate = tf.placeholder(tf.float32, shape=[])   #TODO: maybe use later for oprimization of the model
train_step = tf.train.AdamOptimizer(1e-2).apply_gradients(zip(Gradients_holder,tvars))


#agent starts here:
init = tf.global_variables_initializer()
init2 = tf.initialize_all_variables()
def main():
    rewards, states, actions_booleans = [], [], []
    episode_number = 0
    game_counter = 0

    #variables for debugging:
    manual_prob_use = 0

    with tf.Session() as sess:
        sess.run(init)
        sess.run(init2)

        # check if file is not empty
        if (os.path.isfile(WEIGHTS_FILE) and LOAD):
            # Load with shmickle
            f = open(WEIGHTS_FILE, 'rb')  # BEST_WEIGHTS
            for var, val in zip(tvars, pkl.load(f)):
                sess.run(tf.assign(var, val))
            f.close()
            print("loaded weights successfully!")

        # creates file if it doesn't exisits:
        if (not os.path.isfile(WEIGHTS_FILE)):
            open(WEIGHTS_FILE, 'a').close()
        if (not os.path.isfile(BEST_WEIGHTS)):
            open(BEST_WEIGHTS, 'a').close()
            print("created file sucessfully!")

        update_weights = False #if to much time passed, update the weights even if the game is not finished
        grads_sums = get_empty_grads_sums()  # initialize the gradients holder for the trainable variables

        while game_counter < MAX_GAMES:
            obsrv, reward, done = get_observation()  # get observation
            # append the relevant observation to folloeing action, to states
            states.append(obsrv)        #TODO: use np.concatinate?
            # Run the policy network and get a distribution over actions
            action_probs = sess.run(actions_probs, feed_dict={observations: [obsrv]})
            # np.random.multinomial cause problems
            try:
                m_actions = np.random.multinomial(1, action_probs[0])
            except:
                m_actions = pick_random_action_manually(action_probs[0])
                manual_prob_use += 1

            # Saves the selected action for a later use
            actions_booleans.append(m_actions)
            # index of the selected action
            action = np.argmax(actions_booleans[-1])
            print("action chosen: " + str(action))
            # step the environment and get new measurements
            send_action(action)
            # add reward to rewards for a later use in the training step
            rewards.append(reward)
            game_counter += 1  #TODO: this is for tests

            #TODO: temporary, change to something that make sense...
            if(game_counter % 5 ==0):
                update_weights = True

            #TODO: sleep here?

            if done or update_weights:
                #UPDATE MODEL:

                # create the rewards sums of the reversed rewards array
                rewards_sums = np.cumsum(rewards[::-1])
                # normalize prizes and reverse
                rewards_sums = decrese_rewards(rewards_sums[::-1])
                rewards_sums -= np.mean(rewards_sums)
                rewards_sums = np.divide(rewards_sums, np.std(rewards_sums))
                modified_rewards_sums = np.reshape(rewards_sums, [1, len(rewards_sums)])
                # modify actions_booleans to be an array of booleans
                actions_booleans = np.array(actions_booleans)
                actions_booleans = actions_booleans == 1
                # gradients for current episode
                grads = sess.run(Gradients, feed_dict={observations: states, actions_mask: actions_booleans,
                                                       rewards_arr: modified_rewards_sums})
                grads_sums += np.array(grads)

                episode_number += 1
                update_weights = False

                # Do the training step
                if (episode_number % BATCH_SIZE == 0):
                    grad_dict = {Gradients_holder[i]: grads_sums[i] for i in range(VAR_NO)}
                    #TODO choose learning rate?
                    # take the train step
                    sess.run(train_step, feed_dict=grad_dict)
                    #nullify grads_sum
                    grads_sums = get_empty_grads_sums()

                    #TODO: we don't want to save every time we update, this is for test and will be moved
                    # manual save
                    f = open(WEIGHTS_FILE, 'wb')
                    pkl.dump(sess.run(tvars), f, protocol=2)
                    f.close()
                    print('auto-saved weights successfully.')

                # nullify relevant vars and updates episode number.
                rewards, states, actions_booleans = [], [], []
                manual_prob_use = 0



main()




