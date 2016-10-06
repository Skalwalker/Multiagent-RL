#!/usr/bin/env python
#  -*- coding: utf-8 -*-

"""Define the agents.

Attributes:
    DEFAULT_NOISE: The default noise, 0.
    NOISE: The noise value, 0.
    GHOST_ACTIONS: List of ghost actions, [Directions.NORTH, Directions.SOUTH,
        Directions.EAST, Directions.WEST].
    PACMAN_ACTIONS: List of pacman actions, GHOST_ACTIONS + [Directions.STOP].
    PACMAN_INDEX: The pacman index. 0

To create a new Pacman agent just follow these steps:

    1) First create your new Pacman class and define your choose_action
    function in the agents.py archive. This is going to be how your
    pac-man behave.

    2) Then in the adapter.py archive in the Adapter class you need to add your
    new agent in the setup Pacman agent list to make it acceptable and add this
    name in the raise ValueError list of acceptable agents. Example:

    elif pacman_agent == 'your_pacman_agent_name':
        self.pacman_class = agents.Your_pacman_Class
    else:
        raise ValueError('Pac-Man agent must be ai, random,
        eater or your_pacman_agent_name.')

    3) To finish you need to change the Get_Adapter function in
    cliparser.py archive to accept your agent. Add 'your_pacman_agent_name'
    in choices of group.add_argument pacman-agent.

    4) Now you can run the simulator using your new agent. To do it you
    just need to inicialize the adapter.py using the -pacman-agent
    'your_pacman_agent_name' flag.
"""

import random

from berkeley.game import Agent as BerkeleyGameAgent, Directions

import behaviors
import features
import learning
import Queue

from communication import (ZMQMessengerBase, RequestGameStartMessage,
                           StateMessage)

__author__ = "Matheus Portela and Guilherme N. Ramos"
__credits__ = ["Matheus Portela", "Guilherme N. Ramos", "Renato Nobre",
               "Pedro Saman"]
__maintainer__ = "Guilherme N. Ramos"
__email__ = "gnramos@unb.br"

# Default settings
DEFAULT_NOISE = 0

# Global variable
NOISE = 0

GHOST_ACTIONS = [Directions.NORTH, Directions.SOUTH, Directions.EAST,
                 Directions.WEST]
PACMAN_ACTIONS = GHOST_ACTIONS + [Directions.STOP]
PACMAN_INDEX = 0

###############################################################################
#                                AdapterAgents                                #
###############################################################################


class AdapterAgent(object, BerkeleyGameAgent):
    """Communicating client for game adapter.

    Communicate client to the BerkeleyGameAgent for the gme adapter.

    Attributes:
        agent_id: The identifier of the agent.
        client: A client instance of ZMQMessengerBase.
        previous_action: Directions.STOP.
        test_mode: Test mode is set to 'False'.
    """

    def __init__(self, agent_id, client):
        """Constructor method for AdapterAgent Class.

        Initiate BerkeleyGameAgent

        Args:
            agent_id: The identifier of the agent.
            client: A client instance of ZMQMessengerBase
        Raises:
            ValueError: Invalid Client
        """
        BerkeleyGameAgent.__init__(self, agent_id)

        self.agent_id = agent_id

        if not isinstance(client, ZMQMessengerBase):
            raise ValueError('Invalid client')

        self.client = client

        self.previous_action = Directions.STOP

        self.test_mode = False

    def __noise_error__(self):
        """Return the noise from the noise interval.

        Return:
            Random noise.
        """
        return random.randrange(-NOISE, NOISE + 1)

    def calculate_reward(self, current_score):
        """Base calculate reward method.

        Should be overwrited by a calculate_reward method inside a AdapterAgent
        subclass

        Args:
            current_score: The current score from a state.
        Raise:
            NotImplementedError: Communicating agent must calculate score.
        """
        raise NotImplementedError('Communicating agent must calculate score')

    def communicate(self, msg):
        """Send a given message and return a message requested.

        Args:
            msg: A message for communication
        Returns:
            A message requested to ZMQMessengerBase.
        """
        self.client.send(msg)
        return self.client.receive()

    def create_state_message(self, state):
        """Create a message.

        Create a message that contains agent_id, agent_positions,
        food_positions fragile_agents, wall_positions, legal_actions, reward,
        executed_action and test_mode.

        Args:
            state: A state of the game.
        Returns:
            msg: A message containing agent_id, agent_positions, food_positions
                fragile_agents, wall_positions, legal_actions, reward,
                executed_action and test_mode.
        """
        agent_positions = {}

        agent_positions[PACMAN_INDEX] = state.getPacmanPosition()[::-1]

        for id_, pos in enumerate(state.getGhostPositions()):
            pos_y = pos[::-1][0] + self.__noise_error__()
            pos_x = pos[::-1][1] + self.__noise_error__()
            agent_positions[id_ + 1] = (pos_y, pos_x)

        food_positions = []
        for x, row in enumerate(state.getFood()):
            for y, is_food in enumerate(row):
                if is_food:
                    food_positions.append((y, x))

        fragile_agents = {}
        for id_, s in enumerate(state.data.agentStates):
            fragile_agents[id_] = 1.0 if s.scaredTimer > 0 else 0.0

        wall_positions = []
        for x, row in enumerate(state.getWalls()):
            for y, is_wall in enumerate(row):
                if is_wall:
                    wall_positions.append((y, x))

        reward = self.calculate_reward(state.getScore())
        self.previous_score = state.getScore()

        msg = StateMessage(agent_id=self.agent_id,
                           agent_positions=agent_positions,
                           food_positions=food_positions,
                           fragile_agents=fragile_agents,
                           wall_positions=wall_positions,
                           legal_actions=state.getLegalActions(self.agent_id),
                           reward=reward,
                           executed_action=self.previous_action,
                           test_mode=self.test_mode)

        return msg

    def enable_learn_mode(self):
        """Enable Learn Mode."""
        self.test_mode = False

    def enable_test_mode(self):
        """Enable Test Mode."""
        self.test_mode = True

    def getAction(self, state):
        """Get an action from directions.

        Args:
            state: A state of the game.
        Returns:
            An action from Directions.
        """
        msg = self.create_state_message(state)
        reply_msg = self.communicate(msg)

        self.previous_action = reply_msg.action

        if reply_msg.action not in state.getLegalActions(self.agent_id):
            self.invalid_action = True
            return self.act_when_invalid(state)
        else:
            self.invalid_action = False
            return reply_msg.action

    def start_game(self, layout):
        """Set the start settings for the game agent.

        Args:
            layout: A game layout.
        """
        self.previous_score = 0
        self.previous_action = Directions.STOP
        msg = RequestGameStartMessage(agent_id=self.agent_id,
                                      map_width=layout.width,
                                      map_height=layout.height)
        self.communicate(msg)

    def update(self, state):
        """Create a state message from the current state.

        Create a state message from the current state and communicate.

        Args:
            state: A state of the game.
        """
        msg = self.create_state_message(state)
        self.communicate(msg)


class PacmanAdapterAgent(AdapterAgent):
    """The AdapterAgent for the Pacman Classes."""

    def __init__(self, client):
        """Extend the Constructor method from the AdapterAgent superclass.

        Args:
            client: A client instance of ZMQMessengerBase
        """
        super(PacmanAdapterAgent, self).__init__(agent_id=PACMAN_INDEX,
                                                 client=client)

    """Todo:
            Is this ever used?
    """
    def act_when_invalid(self, state):
        """Action when there are no other valid actions.

        Args:
            state: The current state.
        Returns:
            Directions.STOP: The pacman stand still.
        """
        return Directions.STOP

    def calculate_reward(self, current_score):
        """Calculate the reward.

        Args:
            current_score: The current score of the agent.
        Returns:
            The curent_score - previous_score.
        """
        return current_score - self.previous_score


class GhostAdapterAgent(AdapterAgent):
    """The AdapterAgent for the Ghosts Classes.

    Attributes:
        previous_action: The previous action, defaul is Directions.NORTH.
    """

    def __init__(self, agent_id, client):
        """Extend the Constructor method from the AdapterAgent superclass.

        Args:
            agent_id: The identifier of the agent.
            client: A client instance of ZMQMessengerBase.
        """
        super(GhostAdapterAgent, self).__init__(agent_id, client)

        self.previous_action = Directions.NORTH
        # self.actions = GHOST_ACTIONS

    """Todo:
        Is this ever used?
    """
    # def act_when_invalid(self, state):
    #     return random.choice(state.getLegalActions(self.agent_id))

    def calculate_reward(self, current_score):
        """Calculate the reward.

        Args:
            current_score: The current score of the agent.
        Returns:
            The previous_score - current_score.
        """
        return self.previous_score - current_score

###############################################################################
#                                                                             #
###############################################################################

###############################################################################
#                              ControllerAgents                               #
###############################################################################


class ControllerAgent(object):
    """Autonomous agent for game controller.

    Attributes:
        agent_id: The identifier of the agent.
    """

    def __init__(self, agent_id):
        """Contructor method for the ControllerAgent.

        Args:
            agent_id: The identifier of the agent.
        """
        self.agent_id = agent_id

    def choose_action(self, state, action, reward, legal_actions, explore):
        """Select an action to be executed by the agent.

        This is a base choose_action function and should be overwrited in your
        agent subclass. When implement should return a Direction for the agent
        to follow (NORTH, SOUTH, EAST, WEST or STOP).

        Args:
            state: Current game state.
            action: Last executed action.
            reward: Reward for the previous action.
            legal_actions: List of currently allowed actions.
            explore: Boolean whether agent is allowed to explore.

        Raises:
            NotImplementedError: Agent must implement choose_action
        """
        raise NotImplementedError('Agent must implement choose_action.')


class PacmanAgent(ControllerAgent):
    """A Base PacmanAgent.

    Attributes:
        actions: List of pacman actions.
    """

    def __init__(self, agent_id, ally_ids, enemy_ids):
        """Extend the Constructor from the ControllerAgent superclass.

        Args:
            agent_id: The agent identifier.
            ally_ids: The identifier of the allies.
            enemy_ids: The identifier of the enemies.
        """
        super(PacmanAgent, self).__init__(agent_id)
        self.actions = PACMAN_ACTIONS


class GhostAgent(ControllerAgent):
    """A Base GhostAgent.

    Attributes:
        actions: List of ghosts actions.
    """

    def __init__(self, agent_id, ally_ids, enemy_ids):
        """Extend the Constructor from the ControllerAgent superclass.

        Args:
            agent_id: The agent identifier.
            ally_ids: The identifier of the allies.
            enemy_ids: The identifier of the enemies.
        """
        super(GhostAgent, self).__init__(agent_id)
        self.actions = GHOST_ACTIONS


class RandomPacmanAgent(PacmanAgent):
    """Agent that randomly selects an action."""

    def choose_action(self, state, action, reward, legal_actions, explore):
        """Choose a random action.

        If there is a legal action choose a random action

        Args:
            state: Current game state.
            action: Last executed action.
            reward: Reward for the previous action.
            legal_actions: List of currently allowed actions.
            explore: Boolean whether agent is allowed to explore.
        Returns:
            Random action
        """
        if len(legal_actions) > 0:
            return random.choice(legal_actions)


class RandomPacmanAgentTwo(PacmanAgent):
    """Random kind of PacmanAgent.

    This is not a complete random agent, it follows a set of rules. Those rules
    are well detailed in the procedure of choose the action.
    """

    def choose_action(self, state, action, reward, legal_actions, explore):
        """Choose a random action.

        Choose a random action and does the same until it reaches a wall or
        have more than three possible moves. If the more than three
        possiblities is True the agent have twice the cange of continue to
        follow the same direction.

        Args:
            state: Current game state.
            action: Last executed action.
            reward: Reward for the previous action.
            legal_actions: List of currently allowed actions.
            explore: Boolean whether agent is allowed to explore.
        Returns:
            Random action
        """
        if action == 'Stop' or action not in legal_actions:
            if 'Stop' in legal_actions:
                legal_actions.remove('Stop')
            if len(legal_actions) > 0:
                return random.choice(legal_actions)
        else:
            if len(legal_actions) > 3:
                if len(legal_actions) == 4:
                    number = random.choice([1, 2, 3, 4, 5])
                else:
                    number = random.choice([1, 2, 3, 4, 5, 6])
                if number == 1 or number == 2:
                    return action
                else:
                    aux = 3
                    legal_actions.remove(action)
                    for possible_action in legal_actions:
                        if number == aux:
                            return possible_action
                        else:
                            aux += 1
                    else:
                        return random.choice(legal_actions)
            else:
                return action


class BFS_PacmanAgent(PacmanAgent):
    """Agent that search for the shortest food using BFS algorithm."""

    def choose_action(self, state, action, reward, legal_actions, explore):

        q = Queue.Queue()
        visited = []

        Initial_Position = state.get_position()
        new_position = Initial_Position

        food_map = state.food_map

        agent_map = state.get_map()

        q.put(Initial_Position)
        visited.append(Initial_Position)

        closest_food = None
        while (not q.empty()):
            Current_Position = q.get()
            for i in range(-1, 2):
                for j in range(-1, 2):
                    new_position = (Current_Position[0]+i,
                                    Current_Position[1]+j)
                    if(agent_map._is_valid_position(new_position) and
                       (new_position not in visited)):
                        q.put(new_position)
                        visited.append(new_position)
                    if(food_map[new_position[0]][new_position[1]] == 1 and
                       closest_food is None):
                        closest_food = new_position
        best_action = None
        min_dist = None

        if closest_food is None:
            return Directions.STOP
        if len(legal_actions) > 0:
            for action in legal_actions:
                new_dist = state.calculate_distance(Initial_Position,
                                                    closest_food)
                if new_dist < min_dist:
                    min_dist = new_dist
                    best_action = action
            return best_action
        else:
            return Directions.STOP


class RandomGhostAgent(GhostAgent):
    """GhostAgent that randomly selects an action."""

    def choose_action(self, state, action, reward, legal_actions, explore):
        """Choose a random action.

        If there is a legal action choose a random action

        Args:
            state: Current game state.
            action: Last executed action.
            reward: Reward for the previous action.
            legal_actions: List of currently allowed actions.
            explore: Boolean whether agent is allowed to explore.
        Returns:
            Random action
        """
        if len(legal_actions) > 0:
            return random.choice(legal_actions)


class EaterPacmanAgent(PacmanAgent):
    """Greedy Pacman Agent.

    Args:
        eat_behavior: Implement the eat behavior.
    """

    def __init__(self, agent_id, ally_ids, enemy_ids):
        """Extend the constructor from the PacmanAgent superclass.

        Args:
            agent_id: The identifier of an agent.
            ally_ids: The identifier of all allies agents.
            enemy_ids: The identifier of all enemies agents.
        """
        super(EaterPacmanAgent, self).__init__(agent_id, ally_ids, enemy_ids)
        self.eat_behavior = behaviors.EatBehavior()

    def choose_action(self, state, action, reward, legal_actions, test):
        """Choose a suggested action.

        Choose a suggested action from the eat behavior in legal actions, or
        if there is not a legal action stay still, or in last case select a
        random action from legal actions.

        Args:
            state: Current game state.
            action: Last executed action.
            reward: Reward for the previous action.
            legal_actions: List of currently allowed actions.
            explore: Boolean whether agent is allowed to explore.
        Returns:
            Suggested Action.
        """
        suggested_action = self.eat_behavior(state, legal_actions)

        if suggested_action in legal_actions:
            return suggested_action
        elif legal_actions == []:
            return Directions.STOP
        else:
            return random.choice(legal_actions)


class BehaviorLearningPacmanAgent(PacmanAgent):
    """Behavior Learning Pacman Agent.

    Attributes:
        features: features the Pacman can use.
        behaviors: list of Pacman possible behaviors.
        K: learning rate.
        exploration_rate: rate of exploration.
        learning: instance of QLearningWithApproximation.
        previous_behavior: The previous behavior used.
        behavior_count: The count of how much a behavior is used.
        reset_behavior_count: Call reset_behavior_count.
        test_mode: Set test mode to 'False'.
    """

    def __init__(self, agent_id, ally_ids, enemy_ids):
        """Constructor for the BehaviorLearningPacmanAgent.

        Extend the PacmanAgent constructor.

        Setup the features the pacman will use, the behaviors, the explotation
        and exploration rate, initialize a QLearningWithApproximation object
        initialize behavior count and set test mode to 'False'.

        Args:
            agent_id: The identifier of the agent.
            ally_ids: The identifiers of all the allies.
            enemy_ids: The identifiers of all the enemies.
        """
        super(BehaviorLearningPacmanAgent, self).__init__(agent_id, ally_ids,
                                                          enemy_ids)
        self.features = [features.FoodDistanceFeature()]
        for enemy_id in enemy_ids:
            self.features.append(features.EnemyDistanceFeature(enemy_id))
        for id_ in [agent_id] + ally_ids + enemy_ids:
            self.features.append(features.FragileAgentFeature(id_))

        self.behaviors = [behaviors.EatBehavior(),
                          behaviors.FleeBehavior(),
                          behaviors.SeekBehavior(),
                          behaviors.PursueBehavior()]

        self.K = 1.0  # Learning rate
        self.exploration_rate = 0.1

        QLearning = learning.QLearningWithApproximation
        self.learning = QLearning(learning_rate=0.1, discount_factor=0.9,
                                  actions=self.behaviors,
                                  features=self.features,
                                  exploration_rate=self.exploration_rate)
        self.previous_behavior = self.behaviors[0]
        self.behavior_count = {}
        self.reset_behavior_count()

        self.test_mode = False

    def reset_behavior_count(self):
        """Reset the behavior count for each behavior."""
        for behavior in self.behaviors:
            self.behavior_count[str(behavior)] = 0

    def get_policy(self):
        """Get the policy for the agent.

        Return:
            The agent weights.
        """
        return self.learning.get_weights()

    def set_policy(self, weights):
        """Set the policy for the agent.

        Set the learning agent weights.

        Args:
            weights: The weights of a feature.
        """
        self.learning.set_weights(weights)

    def choose_action(self, state, action, reward, legal_actions, test):
        """Choose an suggested action.

        Choose an suggested action, suggested by the QLearningWithApproximation
        class, or if not in legal actions, it chooses de Directions.STOP action
        or in the last case it is set to random.

        Args:
            state: Current game state.
            action: Last executed action.
            reward: Reward for the previous action.
            legal_actions: List of currently allowed actions.
            test: enable or disable test mode.
        Returns:
            A suggested action from the QLearningWithApproximation
        """
        if test:
            self.enable_test_mode()
        else:
            self.enable_learn_mode()

        if not self.test_mode:
            self.learning.learning_rate = self.K / (self.K + state.iteration)
            self.learning.learn(state, self.previous_behavior, reward)

        behavior = self.learning.act(state)
        self.previous_behavior = behavior
        suggested_action = behavior(state, legal_actions)

        self.behavior_count[str(behavior)] += 1

        if suggested_action in legal_actions:
            return suggested_action
        elif legal_actions == []:
            return Directions.STOP
        else:
            return random.choice(legal_actions)

    def enable_learn_mode(self):
        """Enable Learn Mode.

        Set the exploration rate of learning to the class exploration rate.
        """
        self.test_mode = False
        self.learning.exploration_rate = self.exploration_rate

    def enable_test_mode(self):
        """Enable Test Mode."""
        self.test_mode = True
        self.learning.exploration_rate = 0


class BehaviorLearningGhostAgent(GhostAgent):
    """Behavior Learning Ghosts Agent.

    Attributes:
        features: features the Pacman can use.
        behaviors: list of Pacman possible behaviors.
        K: learning rate.
        exploration_rate: rate of exploration.
        learning: instance of QLearningWithApproximation.
        previous_behavior: The previous behavior used.
        behavior_count: The count of how much a behavior is used.
        reset_behavior_count: Call reset_behavior_count.
        test_mode: Set test mode to 'False'.
    """

    def __init__(self, agent_id, ally_ids, enemy_ids):
        """Constructor for the BehaviorLearningGhostAgent.

        Extend the GhostAgent constructor.

        Setup the features the ghosts will use, the behaviors, the explotation
        and exploration rate, initialize a QLearningWithApproximation object
        initialize behavior count and set test mode to 'False'.
        Args:
            agent_id: The identifier of the agent.
            ally_ids: The identifiers of all the allies.
            enemy_ids: The identifiers of all the enemies.
        """
        super(BehaviorLearningGhostAgent, self).__init__(agent_id, ally_ids,
                                                         enemy_ids)
        self.features = [features.FoodDistanceFeature()]
        for enemy_id in enemy_ids:
            self.features.append(features.EnemyDistanceFeature(enemy_id))
        for id_ in [agent_id] + ally_ids + enemy_ids:
            self.features.append(features.FragileAgentFeature(id_))

        self.behaviors = [behaviors.FleeBehavior(),
                          behaviors.SeekBehavior(),
                          behaviors.PursueBehavior()]

        self.K = 1.0  # Learning rate
        self.exploration_rate = 0.1
        QLearning = learning.QLearningWithApproximation
        self.learning = QLearning(learning_rate=0.1, discount_factor=0.9,
                                  actions=self.behaviors,
                                  features=self.features,
                                  exploration_rate=self.exploration_rate)
        self.previous_behavior = self.behaviors[0]
        self.behavior_count = {}
        self.reset_behavior_count()

        self.test_mode = False

    def reset_behavior_count(self):
        """Reset behavior count for each behavior."""
        for behavior in self.behaviors:
            self.behavior_count[str(behavior)] = 0

    def get_policy(self):
        """Get the policy for the agent.

        Return:
            The agent weights.
        """
        return self.learning.get_weights()

    def set_policy(self, weights):
        """Set the policy for the agent.

        Set the learning agent weights.

        Args:
            weights:
        """
        self.learning.set_weights(weights)

    def choose_action(self, state, action, reward, legal_actions, test):
        """Choose an suggested action.

        Choose an suggested action, suggested by the QLearningWithApproximation
        class, or if not in legal actions, it chooses de Directions.STOP action
        or in the last case it is set to random.

        Args:
            state: Current game state.
            action: Last executed action.
            reward: Reward for the previous action.
            legal_actions: List of currently allowed actions.
            test: enable or disable test mode.
        Returns:
            A suggested action from the QLearningWithApproximation
        """
        if test:
            self.enable_test_mode()
        else:
            self.enable_learn_mode()

        if not self.test_mode:
            self.learning.learning_rate = self.K / (self.K + state.iteration)
            self.learning.learn(state, self.previous_behavior, reward)

        behavior = self.learning.act(state)
        self.previous_behavior = behavior
        suggested_action = behavior(state, legal_actions)

        self.behavior_count[str(behavior)] += 1

        if suggested_action in legal_actions:
            return suggested_action
        elif legal_actions == []:
            return Directions.STOP
        else:
            return random.choice(legal_actions)

    def enable_learn_mode(self):
        """Enable Learn Mode.

        Set the exploration rate of learning to the class exploration rate.
        """
        self.test_mode = False
        self.learning.exploration_rate = self.exploration_rate

    def enable_test_mode(self):
        """Enable Test Mode."""
        self.test_mode = True
        self.learning.exploration_rate = 0
